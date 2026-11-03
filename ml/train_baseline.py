"""Train one checkout-time logistic baseline; tune the threshold on validation."""

import argparse
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import platform
import sys
import uuid
import warnings

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.exceptions import ConvergenceWarning
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score, average_precision_score, brier_score_loss, confusion_matrix,
    f1_score, precision_recall_curve, precision_score, recall_score, roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from ml.build_dataset import CATEGORICAL_FEATURES, FEATURES, NUMERIC_FEATURES, SPLIT_DATES


SEED = 42
PARAMETERS = {"C": 1.0, "solver": "lbfgs", "max_iter": 2000, "class_weight": None, "random_state": SEED}


def digest(path):
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def feature_matrix(frame):
    missing = set(FEATURES) - set(frame.columns)
    if missing:
        raise ValueError(f"Missing predictor columns: {sorted(missing)}")
    output = frame[FEATURES].copy()
    for field in NUMERIC_FEATURES:
        output[field] = pd.to_numeric(output[field], errors="raise").astype(float)
    if np.isinf(output[NUMERIC_FEATURES].to_numpy()).any():
        raise ValueError("Infinite numeric predictors are not allowed")
    for field in CATEGORICAL_FEATURES:
        output[field] = output[field].astype(object).where(output[field].notna(), np.nan)
    return output


def make_pipeline():
    numeric = Pipeline([
        ("impute", SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True)),
        ("scale", StandardScaler()),
    ])
    categorical = Pipeline([
        ("impute", SimpleImputer(strategy="constant", fill_value="__missing__", keep_empty_features=True)),
        ("encode", OneHotEncoder(handle_unknown="ignore", sparse_output=True)),
    ])
    preprocessing = ColumnTransformer([
        ("numeric", numeric, NUMERIC_FEATURES), ("categorical", categorical, CATEGORICAL_FEATURES),
    ], remainder="drop", sparse_threshold=1.0)
    return Pipeline([("preprocess", preprocessing), ("classifier", LogisticRegression(**PARAMETERS))])


def select_threshold(target, probability):
    precision, recall, thresholds = precision_recall_curve(target, probability)
    numerator = 2 * precision[:-1] * recall[:-1]
    denominator = precision[:-1] + recall[:-1]
    scores = np.divide(numerator, denominator, out=np.zeros_like(numerator), where=denominator > 0)
    best = np.flatnonzero(np.isclose(scores, scores.max(), rtol=0, atol=1e-12))
    # Prefer fewer alerts when validation F1 is tied.
    index = best[np.argmax(thresholds[best])]
    return float(thresholds[index]), float(scores[index])


def metrics(target, probability, threshold):
    predicted = np.asarray(probability) >= threshold
    return {
        "rows": len(target), "positive_orders": int(np.sum(target)), "prevalence": float(np.mean(target)),
        "average_precision": float(average_precision_score(target, probability)),
        "roc_auc": float(roc_auc_score(target, probability)), "brier_score": float(brier_score_loss(target, probability)),
        "threshold": float(threshold), "precision": float(precision_score(target, predicted, zero_division=0)),
        "recall": float(recall_score(target, predicted, zero_division=0)), "f1": float(f1_score(target, predicted, zero_division=0)),
        "accuracy": float(accuracy_score(target, predicted)), "predicted_late_orders": int(predicted.sum()),
        "confusion_matrix": confusion_matrix(target, predicted, labels=[0, 1]).tolist(),
    }


def fit_baseline(train, validation):
    estimator = make_pipeline()
    with warnings.catch_warnings():
        warnings.simplefilter("error", ConvergenceWarning)
        estimator.fit(feature_matrix(train), train["late_delivery"].to_numpy(dtype=int))
    validation_probability = estimator.predict_proba(feature_matrix(validation))[:, 1]
    threshold, score = select_threshold(validation["late_delivery"], validation_probability)
    return estimator, threshold, score, validation_probability


def load_split(directory, name, manifest):
    frame = pd.read_csv(directory / f"{name}.csv", keep_default_na=False, na_values=[""], dtype={field: "string" for field in CATEGORICAL_FEATURES + ["order_id"]})
    expected_columns = ["order_id", "prediction_at"] + FEATURES + ["late_delivery", "label_available_at"]
    if list(frame.columns) != expected_columns:
        raise ValueError(f"{name}: unexpected input schema")
    expected = manifest["splits"][name]
    if len(frame) != expected["rows"] or int(frame["late_delivery"].sum()) != expected["late_orders"]:
        raise ValueError(f"{name}: row counts or labels differ from the dataset manifest")
    if not frame["order_id"].is_unique or frame["order_id"].isna().any() or set(frame["late_delivery"].unique()) != {0, 1}:
        raise ValueError(f"{name}: invalid order keys or target classes")
    prediction = pd.to_datetime(frame["prediction_at"], errors="raise")
    available = pd.to_datetime(frame["label_available_at"], errors="raise")
    dates = manifest["split_boundaries"]
    lower = {"train": None, "validation": dates["train_end"], "test": dates["validation_end"]}[name]
    upper = {"train": dates["train_end"], "validation": dates["validation_end"], "test": dates["test_end"]}[name]
    cutoff = {"train": dates["train_end"], "validation": dates["validation_end"], "test": dates["observation_end"]}[name]
    if not prediction.lt(pd.Timestamp(upper)).all() or (lower and not prediction.ge(pd.Timestamp(lower)).all()):
        raise ValueError(f"{name}: purchase timestamps violate chronological split")
    if not (available.lt(pd.Timestamp(cutoff)) & available.ge(prediction)).all():
        raise ValueError(f"{name}: labels are not available within the allowed time window")
    return frame


def write_model_card(report, destination):
    chosen = report["evaluation"]["test"]["selected_threshold"]
    validation = report["evaluation"]["validation"]["selected_threshold"]
    card = f"""# Delivery-delay logistic regression baseline

This is an experimental historical benchmark, not a production decision system.
It predicts late delivery at checkout, conditional on eventual delivery.

## Protocol

The model uses 21 checkout candidate inputs with numeric median imputation and
standardization, constant categorical missing-value handling, and one-hot
encoding. All preprocessing and classifier parameters are fitted on training
rows only. Unseen validation/test categories are ignored by the encoder.
The fixed model is unweighted L2 logistic regression, C=1, lbfgs, max_iter=2000.
There is no hyperparameter search or refit on validation/test data.

The operating threshold **{report['threshold']:.6f}** maximizes validation F1,
with ties favoring the higher threshold. F1 is a demonstration objective; no
business cost matrix or production alert budget has been defined.

| Metric | Validation | Held-out test |
| --- | ---: | ---: |
| Late prevalence | {validation['prevalence']:.4f} | {chosen['prevalence']:.4f} |
| Average precision | {validation['average_precision']:.4f} | {chosen['average_precision']:.4f} |
| ROC-AUC | {validation['roc_auc']:.4f} | {chosen['roc_auc']:.4f} |
| Precision | {validation['precision']:.4f} | {chosen['precision']:.4f} |
| Recall | {validation['recall']:.4f} | {chosen['recall']:.4f} |
| F1 | {validation['f1']:.4f} | {chosen['f1']:.4f} |

Average precision is the non-interpolated precision-recall summary from
scikit-learn, not trapezoidal PR area. A constant-score no-skill ranking has AP
equal to the evaluated split's prevalence. The report also includes default
0.5-threshold metrics, a training-prior dummy classifier, Brier score, accuracy,
and confusion matrices ordered [[TN, FP], [FN, TP]].

## Limitations and provenance

Catalogue/cart availability at checkout is an assumption in the unversioned
Olist snapshot. Final delivered-order selection excludes cancellations and
unresolved deliveries. Label maturity exclusions change the sample near split
boundaries. The markedly different class rates across periods indicate drift.
This baseline does not establish calibrated probabilities, business utility,
causal effects, or performance for current live orders. Coefficients are not
causal feature effects. The test set has now been evaluated; later comparisons
must disclose reuse and avoid tuning choices to these test results.

Dataset run: `{report['dataset_run_id']}`.
Source snapshot: `{report['source_fingerprint']}`.
Training code SHA-256: `{report['training_code_sha256']}`.
Runtime versions and input/output file digests are recorded in metrics.json.
The local joblib bundle contains the fitted preprocessing, classifier,
validation-selected threshold, feature allowlist, and dummy baseline. Load only
trusted bundles in a compatible runtime; joblib loading can execute Python code.
"""
    destination.write_text(card, encoding="utf-8")


def train(dataset_root, output_root):
    pointer = json.loads((dataset_root / "LATEST.json").read_text())
    directory = (dataset_root / pointer["run_id"]).resolve()
    if not directory.is_relative_to(dataset_root.resolve()):
        raise ValueError("Dataset generation must stay within the dataset root")
    manifest = json.loads((directory / "manifest.json").read_text())
    if manifest["numeric_features"] != NUMERIC_FEATURES or manifest["categorical_features"] != CATEGORICAL_FEATURES or manifest["split_boundaries"] != SPLIT_DATES:
        raise ValueError("Dataset contract differs from the registered baseline protocol")
    print("Loading training and validation splits...", file=sys.stderr, flush=True)
    training = load_split(directory, "train", manifest)
    validation = load_split(directory, "validation", manifest)
    if set(training["order_id"]) & set(validation["order_id"]):
        raise ValueError("Training and validation orders overlap")
    print("Fitting training-only preprocessing and logistic regression...", file=sys.stderr, flush=True)
    estimator, threshold, validation_f1, validation_probability = fit_baseline(training, validation)
    dummy = DummyClassifier(strategy="prior")
    dummy.fit(np.zeros((len(training), 1)), training["late_delivery"])
    # No test rows or labels are loaded before model fit and threshold selection.
    print("Threshold frozen; loading held-out test data for evaluation...", file=sys.stderr, flush=True)
    testing = load_split(directory, "test", manifest)
    if set(testing["order_id"]) & (set(training["order_id"]) | set(validation["order_id"])):
        raise ValueError("Test orders overlap an earlier split")
    test_probability = estimator.predict_proba(feature_matrix(testing))[:, 1]
    evaluation = {}
    for name, frame, probability in (("validation", validation, validation_probability), ("test", testing, test_probability)):
        target = frame["late_delivery"].to_numpy(dtype=int)
        dummy_probability = dummy.predict_proba(np.zeros((len(frame), 1)))[:, 1]
        evaluation[name] = {
            "selected_threshold": metrics(target, probability, threshold),
            "default_threshold": metrics(target, probability, 0.5),
            "training_prior_dummy": metrics(target, dummy_probability, 0.5),
        }
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    generation = output_root / run_id
    generation.mkdir(parents=True, exist_ok=False)
    bundle = {"pipeline": estimator, "dummy": dummy, "threshold": threshold, "feature_columns": FEATURES, "dataset_run_id": manifest["run_id"]}
    model_path = generation / "model.joblib"
    joblib.dump(bundle, model_path, compress=3)
    restored = joblib.load(model_path)
    restored_probability = restored["pipeline"].predict_proba(feature_matrix(testing.iloc[:100]))[:, 1]
    np.testing.assert_allclose(restored_probability, test_probability[:100], rtol=1e-12, atol=1e-12)
    for name, frame, probability in (("validation", validation, validation_probability), ("test", testing, test_probability)):
        pd.DataFrame({"order_id": frame["order_id"], "late_delivery": frame["late_delivery"], "probability": probability, "predicted_late": (probability >= threshold).astype(int)}).to_csv(generation / f"{name}_predictions.csv", index=False)
    preprocessing = estimator.named_steps["preprocess"]
    coefficients = pd.DataFrame({"transformed_feature": preprocessing.get_feature_names_out(), "coefficient": estimator.named_steps["classifier"].coef_[0]})
    coefficients.loc[coefficients["coefficient"].abs().sort_values(ascending=False).index].to_csv(generation / "coefficients.csv", index=False)
    report = {
        "model_version": 1, "run_id": run_id, "dataset_run_id": manifest["run_id"], "source_fingerprint": manifest["source_fingerprint"],
        "training_code_sha256": digest(Path(__file__)), "dataset_manifest_sha256": digest(directory / "manifest.json"),
        "input_sha256": {name: digest(directory / f"{name}.csv") for name in ("train", "validation", "test")},
        "feature_columns": FEATURES, "threshold": threshold, "threshold_objective": "maximum validation F1; higher threshold breaks ties",
        "validation_f1_at_selection": validation_f1, "parameters": PARAMETERS,
        "training_rows": len(training), "expanded_feature_count": len(preprocessing.get_feature_names_out()),
        "solver_iterations": estimator.named_steps["classifier"].n_iter_.tolist(), "evaluation": evaluation,
        "versions": {"python": platform.python_version(), **{name: version(name) for name in ("scikit-learn", "pandas", "numpy", "scipy", "joblib")}},
        "model_sha256": digest(model_path), "roundtrip_predictions_match": True,
    }
    write_model_card(report, generation / "MODEL_CARD.md")
    (generation / "metrics.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    temporary = output_root / f".LATEST-{run_id}.json"
    temporary.write_text(json.dumps({"run_id": run_id, "metrics": f"{run_id}/metrics.json"}) + "\n", encoding="utf-8")
    temporary.replace(output_root / "LATEST.json")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, default=Path("data/processed/delivery_delay"))
    parser.add_argument("--output-root", type=Path, default=Path("data/processed/delivery_delay_models"))
    args = parser.parse_args()
    print(json.dumps(train(args.dataset_root, args.output_root), indent=2))


if __name__ == "__main__":
    main()

"""Compare fixed candidates on historical folds inside the original training split."""

import argparse
from datetime import datetime, timezone
from importlib.metadata import version
import json
from pathlib import Path
import sys
import uuid
import warnings

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.exceptions import ConvergenceWarning
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder, OrdinalEncoder, StandardScaler

from ml.build_dataset import CATEGORICAL_FEATURES, NUMERIC_FEATURES
from ml.train_baseline import PARAMETERS, digest, feature_matrix, load_split, make_pipeline


# Fixed before running the comparison; no hyperparameter or threshold search.
ORIGINS = ("2017-07-01", "2017-09-01", "2017-10-01")
MATURITY_DAYS = 60
TREE_PARAMETERS = dict(max_iter=150, learning_rate=0.05, max_leaf_nodes=15,
                       min_samples_leaf=50, l2_regularization=10.0,
                       early_stopping=False, random_state=42)
CANDIDATES = ("training_prior", "linear_logistic", "cyclic_month_logistic", "hist_gradient_boosting")


def cyclic_month(matrix):
    output = matrix.copy()
    angle = 2 * np.pi * (output.pop("purchase_month") - 1) / 12
    output["month_sin"] = np.sin(angle)
    output["month_cos"] = np.cos(angle)
    return output


def make_candidate(name):
    if name == "linear_logistic":
        return make_pipeline()
    if name == "cyclic_month_logistic":
        numeric_fields = [field for field in NUMERIC_FEATURES if field != "purchase_month"] + ["month_sin", "month_cos"]
        numeric = Pipeline([("impute", SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True)),
                            ("scale", StandardScaler())])
        categorical = Pipeline([("impute", SimpleImputer(strategy="constant", fill_value="__missing__", keep_empty_features=True)),
                                ("encode", OneHotEncoder(handle_unknown="ignore"))])
        preprocessing = ColumnTransformer([("numeric", numeric, numeric_fields),
                                           ("categorical", categorical, CATEGORICAL_FEATURES)], sparse_threshold=1.0)
        return Pipeline([("calendar", FunctionTransformer(cyclic_month)), ("preprocess", preprocessing),
                         ("classifier", LogisticRegression(**PARAMETERS))])
    if name == "hist_gradient_boosting":
        # Known categories are learned within each fold; unseen categories become NaN.
        categorical = Pipeline([("impute", SimpleImputer(strategy="constant", fill_value="__missing__", keep_empty_features=True)),
                                ("encode", OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=np.nan))])
        preprocessing = ColumnTransformer([("numeric", "passthrough", NUMERIC_FEATURES),
                                           ("categorical", categorical, CATEGORICAL_FEATURES)])
        categorical_mask = [False] * len(NUMERIC_FEATURES) + [True] * len(CATEGORICAL_FEATURES)
        return Pipeline([("preprocess", preprocessing),
                         ("classifier", HistGradientBoostingClassifier(categorical_features=categorical_mask, **TREE_PARAMETERS))])
    raise ValueError(f"Unknown candidate: {name}")


def historical_fold(frame, origin, maturity_days=MATURITY_DAYS):
    origin = pd.Timestamp(origin)
    end = origin + pd.DateOffset(months=1)
    cutoff = end + pd.Timedelta(days=maturity_days)
    purchase = pd.to_datetime(frame["prediction_at"], errors="raise")
    available = pd.to_datetime(frame["label_available_at"], errors="raise")
    if not available.ge(purchase).all():
        raise ValueError("Outcome availability precedes purchase")
    train_mask = purchase.lt(origin - pd.Timedelta(days=maturity_days)) & available.lt(origin)
    evaluation_candidates = purchase.ge(origin) & purchase.lt(end)
    evaluation_mask = evaluation_candidates & available.lt(cutoff)
    train, evaluation = frame.loc[train_mask].copy(), frame.loc[evaluation_mask].copy()
    if set(train.order_id) & set(evaluation.order_id):
        raise ValueError("Fold training and evaluation orders overlap")
    for part in (train, evaluation):
        if not part.order_id.is_unique or set(part.late_delivery.unique()) != {0, 1}:
            raise ValueError("Each fold needs unique orders and both target classes")
    details = {"origin": origin.isoformat(), "purchase_end": end.isoformat(), "label_cutoff": cutoff.isoformat(),
               "training_purchase_end": (origin - pd.Timedelta(days=maturity_days)).isoformat(),
               "training_rows": len(train), "training_late_rate": float(train.late_delivery.mean()),
               "evaluation_rows": len(evaluation), "evaluation_late_orders": int(evaluation.late_delivery.sum()),
               "evaluation_candidates_in_original_train": int(evaluation_candidates.sum()),
               "excluded_by_fold_maturity_in_original_train": int((evaluation_candidates & ~evaluation_mask).sum())}
    return train, evaluation, details


def probability_metrics(target, probability):
    target = np.asarray(target)
    probability = np.asarray(probability)
    if len(target) != len(probability) or set(np.unique(target)) != {0, 1}:
        raise ValueError("Evaluation needs aligned binary outcomes with both classes")
    if not np.isfinite(probability).all() or ((probability < 0) | (probability > 1)).any():
        raise ValueError("Invalid probabilities")
    prevalence = float(target.mean())
    ap = float(average_precision_score(target, probability))
    return {"prevalence": prevalence, "average_precision": ap, "ap_lift": ap / prevalence,
            "roc_auc": float(roc_auc_score(target, probability)),
            "brier_score": float(brier_score_loss(target, probability)),
            "mean_probability": float(probability.mean()), "calibration_gap": float(probability.mean() - prevalence)}


def load_training_only(dataset_root, model_root):
    baseline = json.loads((model_root / "metrics.json").read_text())
    generation = (dataset_root / baseline["dataset_run_id"]).resolve()
    if not generation.is_relative_to(dataset_root.resolve()):
        raise ValueError("Dataset generation escapes its root")
    manifest_path = generation / "manifest.json"
    if digest(manifest_path) != baseline["dataset_manifest_sha256"]:
        raise ValueError("Dataset manifest checksum differs")
    if digest(generation / "train.csv") != baseline["input_sha256"]["train"]:
        raise ValueError("Training CSV checksum differs")
    manifest = json.loads(manifest_path.read_text())
    # Every fold's evaluation cutoff precedes the original training label cutoff.
    last_cutoff = max(pd.Timestamp(origin) + pd.DateOffset(months=1) + pd.Timedelta(days=MATURITY_DAYS) for origin in ORIGINS)
    if last_cutoff >= pd.Timestamp(manifest["split_boundaries"]["train_end"]):
        raise ValueError("Historical evaluation extends past the original training label cutoff")
    return baseline, load_split(generation, "train", manifest)


def compare(dataset_root, model_root, output_root):
    baseline, frame = load_training_only(dataset_root, model_root)
    results, folds = [], []
    for origin in ORIGINS:
        train, evaluation, details = historical_fold(frame, origin)
        folds.append(details)
        x_train, x_evaluation = feature_matrix(train), feature_matrix(evaluation)
        y_train, y_evaluation = train.late_delivery.to_numpy(dtype=int), evaluation.late_delivery.to_numpy(dtype=int)
        for name in CANDIDATES:
            print(f"{origin}: {name} ({len(train)} training, {len(evaluation)} evaluation rows)", file=sys.stderr, flush=True)
            if name == "training_prior":
                probability = np.full(len(evaluation), y_train.mean())
            else:
                candidate = make_candidate(name)
                with warnings.catch_warnings():
                    warnings.simplefilter("error", ConvergenceWarning)
                    candidate.fit(x_train, y_train)
                probability = candidate.predict_proba(x_evaluation)[:, 1]
            results.append({"origin": origin, "candidate": name, "rows": len(evaluation),
                            **probability_metrics(y_evaluation, probability)})
    table = pd.DataFrame(results)
    # Equal-fold summaries preserve the visibility of temporal variability.
    summary = table.groupby("candidate", sort=False).agg(
        mean_ap=("average_precision", "mean"), min_ap=("average_precision", "min"), max_ap=("average_precision", "max"),
        mean_ap_lift=("ap_lift", "mean"), mean_brier=("brier_score", "mean"),
        mean_calibration_gap=("calibration_gap", "mean")).reset_index()
    paired = table.pivot(index="origin", columns="candidate", values="average_precision")
    summary["folds_ap_above_linear"] = summary.candidate.map({name: int((paired[name] > paired.linear_logistic).sum()) for name in CANDIDATES})
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    output = output_root / run_id
    output.mkdir(parents=True, exist_ok=False)
    table.to_csv(output / "fold_metrics.csv", index=False)
    summary.to_csv(output / "summary.csv", index=False)
    pd.DataFrame(folds).to_csv(output / "folds.csv", index=False)
    report = {"run_id": run_id, "dataset_run_id": baseline["dataset_run_id"],
              "source_fingerprint": baseline["source_fingerprint"], "input_train_sha256": baseline["input_sha256"]["train"],
              "comparison_code_sha256": digest(Path(__file__)), "baseline_code_sha256": digest(Path(__file__).with_name("train_baseline.py")),
              "splits_read": ["train"], "test_rows_read": False, "original_model_changed": False,
              "threshold_selected": False, "model_promoted": False,
              "protocol": {"origins": list(ORIGINS), "evaluation_months": 1, "training_gap_days": MATURITY_DAYS,
                           "evaluation_label_grace_days": MATURITY_DAYS, "logistic_parameters": PARAMETERS,
                           "tree_parameters": TREE_PARAMETERS, "seed": 42,
                           "selection_metric": "descriptive equal-fold mean average precision; no final acceptance"},
              "folds": folds, "summary": json.loads(summary.to_json(orient="records")),
              "versions": {name: version(name) for name in ("scikit-learn", "pandas", "numpy")}}
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    pointer = output_root / f".LATEST-{run_id}.json"
    pointer.write_text(json.dumps({"run_id": run_id}) + "\n", encoding="utf-8")
    pointer.replace(output_root / "LATEST.json")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, default=Path("data/processed/delivery_delay"))
    parser.add_argument("--model-root", type=Path, default=Path("models/delivery_delay_baseline"))
    parser.add_argument("--output-root", type=Path, default=Path("data/processed/model_comparison"))
    args = parser.parse_args()
    print(json.dumps(compare(args.dataset_root, args.model_root, args.output_root), indent=2))


if __name__ == "__main__":
    main()

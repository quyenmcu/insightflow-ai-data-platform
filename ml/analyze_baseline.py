"""Inspect a frozen baseline on train/validation data without reading test rows."""

import argparse
from datetime import datetime, timezone
from importlib.metadata import version
import json
from pathlib import Path
import sys
import uuid

import joblib
import numpy as np
import pandas as pd
from sklearn.inspection import permutation_importance
from sklearn.metrics import average_precision_score, roc_auc_score

from ml.build_dataset import CATEGORICAL_FEATURES, FEATURES, NUMERIC_FEATURES
from ml.train_baseline import digest, feature_matrix, load_split


ANALYSIS_SPLITS = ("train", "validation")


def wilson_interval(positives, count):
    if count == 0:
        return None, None
    z = 1.959963984540054
    p = positives / count
    denominator = 1 + z * z / count
    center = (p + z * z / (2 * count)) / denominator
    radius = z * np.sqrt(p * (1 - p) / count + z * z / (4 * count * count)) / denominator
    return max(0.0, float(center - radius)), min(1.0, float(center + radius))


def summarize(target, probability, threshold):
    target = np.asarray(target, dtype=int)
    probability = np.asarray(probability, dtype=float)
    if len(target) != len(probability) or not len(target) or not set(np.unique(target)) <= {0, 1}:
        raise ValueError("Expected aligned nonempty binary outcomes and probabilities")
    if not np.isfinite(probability).all() or ((probability < 0) | (probability > 1)).any():
        raise ValueError("Probabilities must be finite and within [0, 1]")
    predicted = probability >= threshold
    tp = int(((target == 1) & predicted).sum())
    fp = int(((target == 0) & predicted).sum())
    fn = int(((target == 1) & ~predicted).sum())
    tn = int(((target == 0) & ~predicted).sum())
    classes = len(np.unique(target)) == 2
    return {
        "rows": len(target), "late_orders": int(target.sum()), "late_rate": float(target.mean()),
        "mean_probability": float(probability.mean()), "calibration_gap": float(probability.mean() - target.mean()),
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
        "false_positive_rate": fp / (fp + tn) if fp + tn else None,
        "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.0,
        "average_precision": float(average_precision_score(target, probability)) if classes else None,
        "roc_auc": float(roc_auc_score(target, probability)) if classes else None,
        "brier_score": float(np.mean((probability - target) ** 2)),
    }


def segments(frame, probability, threshold, column, *, min_rows=200, min_positives=20):
    data = frame.reset_index(drop=True).copy()
    if len(data) != len(probability):
        raise ValueError("Prediction rows must align with segment rows")
    data["_probability"] = np.asarray(probability)
    rows = []
    for name, group in data.groupby(column, dropna=False, sort=True):
        if len(group) < min_rows or group["late_delivery"].sum() < min_positives:
            continue
        rows.append({"dimension": column, "segment": str(name), **summarize(group["late_delivery"], group["_probability"], threshold)})
    return pd.DataFrame(rows)


def calibration_bins(target, probability, bins=10):
    target = np.asarray(target, dtype=int)
    probability = np.asarray(probability, dtype=float)
    summarize(target, probability, 0.5)  # validate alignment and probability bounds
    # Equal-score observations stay together, including constant-score baselines.
    if np.unique(probability).size == 1:
        bucket = np.zeros(len(probability), dtype=int)
    else:
        bucket = pd.qcut(probability, q=bins, labels=False, duplicates="drop")
    frame = pd.DataFrame({"bucket": bucket, "target": target, "probability": probability})
    rows = []
    for name, group in frame.groupby("bucket", sort=True):
        lower, upper = wilson_interval(int(group.target.sum()), len(group))
        rows.append({"bucket": int(name), "rows": len(group), "mean_probability": float(group.probability.mean()), "late_rate": float(group.target.mean()), "lower_95": lower, "upper_95": upper})
    return pd.DataFrame(rows)


def feature_drift(training, validation):
    numeric, categorical = [], []
    for name in NUMERIC_FEATURES:
        a = pd.to_numeric(training[name], errors="raise")
        b = pd.to_numeric(validation[name], errors="raise")
        spread = float(a.std(ddof=0))
        delta = float(b.mean() - a.mean())
        shift = delta / spread if spread > 0 else (0.0 if delta == 0 else None)
        numeric.append({"feature": name, "train_mean": float(a.mean()), "validation_mean": float(b.mean()),
                        "standardized_mean_shift": shift, "train_median": float(a.median()), "validation_median": float(b.median()),
                        "train_missing_fraction": float(a.isna().mean()), "validation_missing_fraction": float(b.isna().mean()),
                        "validation_outside_train_range": float(((b < a.min()) | (b > a.max())).mean())})
    for name in CATEGORICAL_FEATURES:
        a = training[name].fillna("__missing__")
        b = validation[name].fillna("__missing__")
        frequencies_a = a.value_counts(normalize=True)
        frequencies_b = b.value_counts(normalize=True)
        keys = frequencies_a.index.union(frequencies_b.index)
        distance = 0.5 * np.abs(frequencies_a.reindex(keys, fill_value=0) - frequencies_b.reindex(keys, fill_value=0)).sum()
        categorical.append({"feature": name, "total_variation_distance": float(distance),
                            "unseen_validation_fraction": float((~b.isin(a.unique())).mean()),
                            "train_categories": int(a.nunique()), "validation_categories": int(b.nunique())})
    return pd.DataFrame(numeric), pd.DataFrame(categorical)


def load_analysis_data(dataset_root, model_root):
    metrics = json.loads((model_root / "metrics.json").read_text())
    model_path = model_root / "model.joblib"
    if digest(model_path) != metrics["model_sha256"]:
        raise ValueError("Frozen baseline model checksum differs")
    generation = (dataset_root / metrics["dataset_run_id"]).resolve()
    if not generation.is_relative_to(dataset_root.resolve()):
        raise ValueError("Dataset generation is outside the dataset root")
    if digest(generation / "manifest.json") != metrics["dataset_manifest_sha256"]:
        raise ValueError("Dataset manifest differs from the baseline input")
    manifest = json.loads((generation / "manifest.json").read_text())
    frames = {}
    for name in ANALYSIS_SPLITS:
        if digest(generation / f"{name}.csv") != metrics["input_sha256"][name]:
            raise ValueError(f"{name}: input checksum differs from the evaluated baseline")
        frames[name] = load_split(generation, name, manifest)
    return metrics, joblib.load(model_path), frames


def plot_diagnostics(monthly, calibration, importance, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import PercentFormatter

    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
    figure, axes = plt.subplots(1, 3, figsize=(15, 4.4), layout="constrained")
    axes[0].plot(monthly.segment, monthly.late_rate, "o-", label="Observed late rate", color="#b45309")
    axes[0].plot(monthly.segment, monthly.mean_probability, "o-", label="Mean predicted risk", color="#2563eb")
    axes[0].yaxis.set_major_formatter(PercentFormatter(1))
    axes[0].set_ylim(bottom=0)
    axes[0].set(title="Validation by purchase month", ylabel="Rate", xlabel="Source calendar month")
    axes[0].tick_params(axis="x", rotation=30)
    axes[0].legend(frameon=False, fontsize=8)
    high = max(float(calibration.upper_95.max()), float(calibration.mean_probability.max())) * 1.12
    axes[1].plot([0, high], [0, high], "--", color="#6b7280", label="Perfect calibration")
    axes[1].errorbar(calibration.mean_probability, calibration.late_rate,
                     yerr=[calibration.late_rate - calibration.lower_95, calibration.upper_95 - calibration.late_rate], fmt="o-", capsize=3, color="#2563eb")
    axes[1].xaxis.set_major_formatter(PercentFormatter(1))
    axes[1].yaxis.set_major_formatter(PercentFormatter(1))
    axes[1].set(title="Validation calibration", xlabel="Mean predicted risk", ylabel="Observed late rate", xlim=(0, high), ylim=(0, high))
    axes[1].legend(frameon=False, fontsize=8)
    best = importance.sort_values("ap_drop_mean", ascending=False).head(7).iloc[::-1]
    axes[2].barh(best.feature, best.ap_drop_mean, xerr=best.ap_drop_std, color="#2563eb", capsize=3)
    axes[2].axvline(0, color="#6b7280", linewidth=0.8)
    axes[2].set(title="Frozen-model reliance", xlabel="Validation AP drop after permutation")
    figure.suptitle("Baseline diagnostics: training + validation only; model and threshold unchanged", fontsize=13)
    figure.savefig(path, dpi=170)
    plt.close(figure)


def analyze(dataset_root, model_root, output_root):
    baseline, bundle, frames = load_analysis_data(dataset_root, model_root)
    training, validation = frames["train"], frames["validation"]
    threshold = float(bundle["threshold"])
    estimator = bundle["pipeline"]
    print("Scoring validation rows with the frozen baseline...", file=sys.stderr, flush=True)
    matrix = feature_matrix(validation)
    probability = estimator.predict_proba(matrix)[:, 1]
    overall = summarize(validation["late_delivery"], probability, threshold)
    if not np.isclose(overall["average_precision"], baseline["evaluation"]["validation"]["selected_threshold"]["average_precision"], atol=1e-12, rtol=0):
        raise ValueError("Validation predictions differ from the frozen baseline")
    frame = validation.copy()
    frame["purchase_period"] = pd.to_datetime(frame["prediction_at"]).dt.strftime("%Y-%m")
    frame["cart_value_band"] = pd.cut(frame["items_value_brl"], [-np.inf, 100, 300, np.inf], labels=["up to R$100", "R$100-300", "over R$300"]).astype("string")
    interstate = frame["interstate_item_fraction"].gt(0).fillna(False).to_numpy(dtype=bool)
    frame["shipping_route"] = np.where(frame["interstate_item_fraction"].isna(), "unknown", np.where(interstate, "interstate items", "same-state items"))
    monthly = segments(frame, probability, threshold, "purchase_period", min_rows=1, min_positives=0)
    slices = pd.concat([segments(frame, probability, threshold, column) for column in ("customer_state", "primary_seller_state", "primary_product_category", "cart_value_band", "shipping_route")], ignore_index=True)
    calibration = calibration_bins(validation["late_delivery"], probability)
    numeric, categorical = feature_drift(training, validation)
    print("Measuring validation permutation importance (3 repeats)...", file=sys.stderr, flush=True)
    shuffled = permutation_importance(estimator, matrix, validation["late_delivery"].to_numpy(dtype=int), scoring="average_precision", n_repeats=3, random_state=42, n_jobs=1)
    importance = pd.DataFrame({"feature": FEATURES, "ap_drop_mean": shuffled.importances_mean, "ap_drop_std": shuffled.importances_std}).sort_values("ap_drop_mean", ascending=False)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    output = output_root / run_id
    output.mkdir(parents=True, exist_ok=False)
    tables = {"monthly": monthly, "segments": slices, "calibration": calibration, "numeric_drift": numeric, "category_drift": categorical, "permutation_importance": importance}
    for name, table in tables.items():
        table.to_csv(output / f"{name}.csv", index=False)
    predicted = probability >= threshold
    errors = validation.loc[predicted != validation["late_delivery"].to_numpy(dtype=bool)].copy()
    errors["probability"] = probability[predicted != validation["late_delivery"].to_numpy(dtype=bool)]
    errors["error_type"] = np.where(errors["late_delivery"].eq(1), "false_negative", "false_positive")
    errors.to_csv(output / "validation_errors.csv", index=False)
    plot_diagnostics(monthly, calibration, importance, output / "diagnostics.png")
    if digest(model_root / "model.joblib") != baseline["model_sha256"]:
        raise ValueError("Baseline model changed during analysis")
    report = {
        "run_id": run_id, "baseline_run_id": baseline["run_id"], "source_fingerprint": baseline["source_fingerprint"],
        "analysis_code_sha256": digest(Path(__file__)), "model_sha256": baseline["model_sha256"],
        "splits_read": list(frames), "test_rows_read": False, "model_refitted": False, "threshold_changed": False,
        "threshold": threshold, "train_late_rate": float(training["late_delivery"].mean()), "validation": overall,
        "validation_score_quantiles": {str(q): float(value) for q, value in pd.Series(probability).quantile([0, 0.01, 0.05, 0.5, 0.95, 0.99, 1]).items()},
        "group_support": {"min_rows": 200, "min_positive_orders": 20},
        "monthly": json.loads(monthly.to_json(orient="records")), "category_drift": json.loads(categorical.to_json(orient="records")),
        "permutation_top": json.loads(importance.head(10).to_json(orient="records")),
        "versions": {name: version(name) for name in ("scikit-learn", "pandas", "matplotlib")},
    }
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    temporary = output_root / f".LATEST-{run_id}.json"
    temporary.write_text(json.dumps({"run_id": run_id}) + "\n", encoding="utf-8")
    temporary.replace(output_root / "LATEST.json")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, default=Path("data/processed/delivery_delay"))
    parser.add_argument("--model-root", type=Path, default=Path("models/delivery_delay_baseline"))
    parser.add_argument("--output-root", type=Path, default=Path("data/processed/baseline_analysis"))
    args = parser.parse_args()
    print(json.dumps(analyze(args.dataset_root, args.model_root, args.output_root), indent=2))


if __name__ == "__main__":
    main()

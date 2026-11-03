import json

import pandas as pd
import pytest

from ml import analyze_baseline as analysis
from ml.build_dataset import CATEGORICAL_FEATURES, NUMERIC_FEATURES


def test_error_counts_and_calibration_gap():
    report = analysis.summarize([0, 0, 1, 1], [0.1, 0.8, 0.2, 0.9], 0.5)
    assert (report["tn"], report["fp"], report["fn"], report["tp"]) == (1, 1, 1, 1)
    assert report["precision"] == report["recall"] == 0.5
    assert report["calibration_gap"] == pytest.approx(0)


def test_probabilities_and_alignment_are_checked():
    with pytest.raises(ValueError, match="align"):
        analysis.summarize([0, 1], [0.2], 0.5)
    with pytest.raises(ValueError, match="finite"):
        analysis.summarize([0, 1], [0.2, float("inf")], 0.5)


def test_constant_probabilities_preserve_all_calibration_rows():
    bins = analysis.calibration_bins([0, 0, 0, 1], [0.1] * 4)
    assert len(bins) == 1
    assert bins.iloc[0]["rows"] == 4
    assert bins.iloc[0]["late_rate"] == 0.25
    assert bins.iloc[0]["lower_95"] < 0.25 < bins.iloc[0]["upper_95"]


def test_small_or_few_positive_segments_are_suppressed():
    frame = pd.DataFrame({"state": ["A"] * 3 + ["B"] * 3, "late_delivery": [0, 0, 0, 0, 1, 1]})
    report = analysis.segments(frame, [0.1] * 6, 0.5, "state", min_rows=3, min_positives=2)
    assert report.segment.tolist() == ["B"]
    assert report.iloc[0]["rows"] == 3


def test_drift_uses_training_spread_and_counts_unseen_categories():
    train = pd.DataFrame({field: [0.0, 2.0] for field in NUMERIC_FEATURES})
    validation = pd.DataFrame({field: [2.0, 4.0] for field in NUMERIC_FEATURES})
    for field in CATEGORICAL_FEATURES:
        train[field] = ["known", "known"]
        validation[field] = ["known", "new"]
    numeric, categorical = analysis.feature_drift(train, validation)
    assert numeric.iloc[0]["standardized_mean_shift"] == 2
    assert categorical.iloc[0]["unseen_validation_fraction"] == 0.5
    assert categorical.iloc[0]["total_variation_distance"] == 0.5


def test_loader_never_reads_test_inputs(tmp_path, monkeypatch):
    dataset_root = tmp_path / "datasets"
    generation = dataset_root / "frozen"
    generation.mkdir(parents=True)
    model_root = tmp_path / "model"
    model_root.mkdir()
    model_path = model_root / "model.joblib"
    model_path.write_bytes(b"owned fixture")
    manifest_path = generation / "manifest.json"
    manifest_path.write_text("{}")
    for name in ("train", "validation"):
        (generation / f"{name}.csv").write_text(name)
    report = {"dataset_run_id": "frozen", "model_sha256": analysis.digest(model_path),
              "dataset_manifest_sha256": analysis.digest(manifest_path),
              "input_sha256": {name: analysis.digest(generation / f"{name}.csv") for name in ("train", "validation")}}
    (model_root / "metrics.json").write_text(json.dumps(report))
    original_digest = analysis.digest
    accessed = []

    def guarded_digest(path):
        assert path.name != "test.csv"
        return original_digest(path)

    def guarded_split(directory, name, manifest):
        assert name in ("train", "validation")
        accessed.append(name)
        return pd.DataFrame({"order_id": [name]})

    monkeypatch.setattr(analysis, "digest", guarded_digest)
    monkeypatch.setattr(analysis, "load_split", guarded_split)
    monkeypatch.setattr(analysis.joblib, "load", lambda _: {"threshold": 0.5})
    _, _, frames = analysis.load_analysis_data(dataset_root, model_root)
    assert accessed == ["train", "validation"]
    assert list(frames) == ["train", "validation"]

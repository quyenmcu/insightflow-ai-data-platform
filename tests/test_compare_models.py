import json

import numpy as np
import pandas as pd
import pytest

from ml import compare_models as comparison
from ml.build_dataset import CATEGORICAL_FEATURES, NUMERIC_FEATURES
from ml.train_baseline import feature_matrix


def test_folds_enforce_gap_and_label_availability():
    frame = pd.DataFrame({"order_id": list("abcdefghi"), "prediction_at": ["2017-03-01"] * 3 + ["2017-06-01"] + ["2017-07-01"] * 4 + ["2017-08-01"],
                          "label_available_at": ["2017-03-20", "2017-04-01", "2017-07-01", "2017-06-15", "2017-08-01", "2017-09-01", "2017-09-30", "2017-10-01", "2017-08-20"],
                          "late_delivery": [0, 1, 1, 0, 0, 1, 1, 1, 0]})
    train, evaluation, details = comparison.historical_fold(frame, "2017-07-01")
    assert train.order_id.tolist() == ["a", "b"]
    assert evaluation.order_id.tolist() == ["e", "f"]  # Sep 30 equals cutoff, so excluded
    assert details["excluded_by_fold_maturity_in_original_train"] == 2


def test_cyclic_month_wraps_calendar_and_excludes_original_month():
    result = comparison.cyclic_month(pd.DataFrame({"purchase_month": [1, 12], "other": [3, 4]}))
    assert "purchase_month" not in result
    assert result.month_sin.iloc[0] == pytest.approx(0)
    assert result.month_cos.iloc[0] == pytest.approx(1)
    assert result.other.tolist() == [3, 4]


@pytest.mark.parametrize("name", comparison.CANDIDATES[1:])
def test_candidates_fit_with_missing_and_unseen_categories(name):
    frame = pd.DataFrame({field: [1., 2., np.nan, 4.] * 30 for field in NUMERIC_FEATURES})
    frame["purchase_month"] = [1., 2., 3., 4.] * 30
    for field in CATEGORICAL_FEATURES:
        frame[field] = ["known", "known", None, "other"] * 30
    matrix = feature_matrix(frame)
    model = comparison.make_candidate(name).fit(matrix, [0, 0, 1, 1] * 30)
    evaluation = matrix.iloc[:3].copy()
    for field in CATEGORICAL_FEATURES:
        evaluation[field] = "unseen"
    probability = model.predict_proba(evaluation)[:, 1]
    assert np.isfinite(probability).all()
    assert ((probability >= 0) & (probability <= 1)).all()
    if name == "hist_gradient_boosting":
        assert model.named_steps["classifier"].early_stopping is False


def test_training_loader_does_not_read_other_splits(tmp_path, monkeypatch):
    root = tmp_path / "datasets"
    generation = root / "frozen"
    generation.mkdir(parents=True)
    model_root = tmp_path / "models"
    model_root.mkdir()
    manifest = generation / "manifest.json"
    manifest.write_text(json.dumps({"split_boundaries": {"train_end": "2018-01-01"}}))
    (generation / "train.csv").write_text("owned fixture")
    baseline = {"dataset_run_id": "frozen", "dataset_manifest_sha256": comparison.digest(manifest),
                "input_sha256": {"train": comparison.digest(generation / "train.csv")}}
    (model_root / "metrics.json").write_text(json.dumps(baseline))
    accessed = []

    def guarded_load(directory, name, manifest):
        assert name == "train"
        accessed.append(name)
        return pd.DataFrame()

    monkeypatch.setattr(comparison, "load_split", guarded_load)
    comparison.load_training_only(root, model_root)
    assert accessed == ["train"]


def test_probability_metrics_reject_invalid_predictions():
    with pytest.raises(ValueError, match="Invalid probabilities"):
        comparison.probability_metrics([0, 1], [0.1, np.nan])
    metrics = comparison.probability_metrics([0, 0, 0, 1], [0.25] * 4)
    assert metrics["ap_lift"] == 1
    assert metrics["calibration_gap"] == 0

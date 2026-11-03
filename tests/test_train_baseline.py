import joblib
import numpy as np
import pandas as pd
import pytest

from ml.build_dataset import CATEGORICAL_FEATURES, FEATURES, NUMERIC_FEATURES
from ml.train_baseline import feature_matrix, fit_baseline, metrics, select_threshold


def rows(values):
    frame = pd.DataFrame({field: list(values) for field in NUMERIC_FEATURES})
    for field in CATEGORICAL_FEATURES:
        frame[field] = ["known"] * len(values)
    frame["late_delivery"] = [0, 0, 1, 1]
    return frame


def test_preprocessing_learns_only_training_statistics():
    train = rows([1.0, 3.0, np.nan, 5.0])
    validation = rows([10000.0, 20000.0, 30000.0, 40000.0])
    for field in CATEGORICAL_FEATURES:
        validation[field] = "unseen"
    model, _, _, probability = fit_baseline(train, validation)
    preprocessing = model.named_steps["preprocess"]
    imputer = preprocessing.named_transformers_["numeric"].named_steps["impute"]
    assert imputer.statistics_[0] == 3.0
    encoder = preprocessing.named_transformers_["categorical"].named_steps["encode"]
    assert all("unseen" not in categories for categories in encoder.categories_)
    assert np.isfinite(probability).all()


def test_metadata_and_target_do_not_enter_feature_matrix():
    frame = rows([1.0, 2.0, 3.0, 4.0])
    expected = feature_matrix(frame)
    frame["order_id"] = "id"
    frame["prediction_at"] = "2099-01-01"
    frame["label_available_at"] = "2099-01-02"
    frame["late_delivery"] = 1 - frame["late_delivery"]
    frame["actual_delivery_date"] = "2099-01-03"
    pd.testing.assert_frame_equal(expected, feature_matrix(frame))
    assert list(expected.columns) == FEATURES


def test_threshold_uses_validation_f1():
    threshold, score = select_threshold(np.array([0, 1, 1, 0]), np.array([0.1, 0.9, 0.8, 0.2]))
    assert threshold == 0.8
    assert score == 1.0


def test_metrics_show_no_skill_and_confusion_order():
    report = metrics(np.array([0, 0, 0, 1]), np.full(4, 0.1), 0.5)
    assert report["average_precision"] == 0.25
    assert report["roc_auc"] == 0.5
    assert report["confusion_matrix"] == [[3, 0], [1, 0]]
    assert report["recall"] == 0


def test_serialized_pipeline_preserves_predictions(tmp_path):
    train = rows([1.0, 2.0, 3.0, 4.0])
    validation = rows([1.5, 2.5, 3.5, 4.5])
    model, threshold, _, probability = fit_baseline(train, validation)
    path = tmp_path / "model.joblib"
    joblib.dump({"pipeline": model, "threshold": threshold}, path)
    restored = joblib.load(path)
    np.testing.assert_allclose(restored["pipeline"].predict_proba(feature_matrix(validation))[:, 1], probability)
    assert restored["threshold"] == threshold


def test_invalid_numeric_input_is_rejected():
    frame = rows([1.0, 2.0, 3.0, 4.0])
    frame.loc[0, NUMERIC_FEATURES[0]] = np.inf
    with pytest.raises(ValueError, match="Infinite"):
        feature_matrix(frame)

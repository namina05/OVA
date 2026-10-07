import numpy as np
import pytest

from ml.models.model_store import ModelNotFoundError, load_bundle, save_bundle
from ml.preprocessing.cleaning import clean_sessions
from ml.preprocessing.features import build_training_frame
from ml.training.train import InsufficientDataError, TrainingParams, split_by_user


def test_split_keeps_each_user_in_one_set(synthetic_sessions, bundle):
    _, _, groups = build_training_frame(bundle.spec, clean_sessions(synthetic_sessions))
    train, val, test = split_by_user(groups, TrainingParams())
    sets = [set(groups[train]), set(groups[val]), set(groups[test])]
    assert all(sets)
    assert not (sets[0] & sets[1]) and not (sets[0] & sets[2]) and not (sets[1] & sets[2])
    assert len(train) + len(val) + len(test) == len(groups)


def test_split_needs_several_users():
    with pytest.raises(InsufficientDataError):
        split_by_user(np.array(["a", "a", "b"]), TrainingParams())


def test_metrics_are_reported_and_beat_the_mean_baseline(training_result):
    m = training_result.metrics
    for key in ("mae", "rmse", "r2"):
        assert np.isfinite(m["test"][key])
    assert m["test"]["mae"] < m["test_baseline_mean"]["mae"]
    assert m["test"]["rmse"] < m["test_baseline_mean"]["rmse"]


def test_save_and_load_give_identical_predictions(bundle, synthetic_sessions, tmp_path):
    X, _, _ = build_training_frame(bundle.spec, clean_sessions(synthetic_sessions.head(50)))
    save_bundle(bundle, tmp_path)
    loaded = load_bundle(tmp_path)
    assert loaded.spec == bundle.spec
    assert loaded.version == bundle.version
    np.testing.assert_allclose(loaded.model.predict(X), bundle.model.predict(X), rtol=1e-6)


def test_loading_missing_model_raises(tmp_path):
    with pytest.raises(ModelNotFoundError):
        load_bundle(tmp_path)

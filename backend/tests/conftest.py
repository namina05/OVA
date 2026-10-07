import pandas as pd
import pytest

from ml.cycle.synthetic import generate_synthetic_cycles
from ml.cycle.train import train_cycle_models
from ml.models.model_store import ModelBundle
from ml.training.synthetic import generate_synthetic_sessions
from ml.training.train import TrainingParams, train_model
from safety.limits import SafetyLimits

FAST_PARAMS = TrainingParams(n_estimators=200, learning_rate=0.1, early_stopping_rounds=20)


@pytest.fixture(scope="session")
def limits() -> SafetyLimits:
    return SafetyLimits()


@pytest.fixture(scope="session")
def synthetic_sessions(limits) -> pd.DataFrame:
    return generate_synthetic_sessions(n_users=120, limits=limits, seed=11)


@pytest.fixture(scope="session")
def training_result(synthetic_sessions, limits):
    return train_model(synthetic_sessions, limits, FAST_PARAMS)


@pytest.fixture(scope="session")
def bundle(training_result) -> ModelBundle:
    return training_result.bundle


@pytest.fixture(scope="session")
def cycle_data():
    return generate_synthetic_cycles(n_users=150, seed=5)


@pytest.fixture(scope="session")
def cycle_bundle(cycle_data):
    params = TrainingParams(n_estimators=150, learning_rate=0.1, early_stopping_rounds=20)
    return train_cycle_models(cycle_data.periods, cycle_data.daily_logs, cycle_data.profiles, params)

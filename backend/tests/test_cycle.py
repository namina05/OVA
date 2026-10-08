from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from ml.cycle import data as cd
from ml.cycle.datasets import build_datasets
from ml.cycle.model_store import load_cycle_bundle, save_cycle_bundle
from ml.cycle.predictor import CyclePredictor, NoPeriodDataError, estimate_ovulation
from ml.cycle.train import conformal_quantile
from ml.models.model_store import ModelNotFoundError
from ml.recommendation.personalization import PersonalizationLevel

TODAY = date(2026, 10, 1)


@pytest.fixture(scope="module")
def predictor(cycle_bundle):
    return CyclePredictor(cycle_bundle, min_cycles_for_model=2)


def periods_every(lengths: list[int], first: date = date(2026, 1, 5), period_days: int = 5) -> pd.DataFrame:
    starts = [first]
    for n in lengths:
        starts.append(starts[-1] + timedelta(days=n))
    return pd.DataFrame({
        cd.USER_ID: "u1", cd.START: starts, cd.END: [s + timedelta(days=period_days - 1) for s in starts],
    })


def test_cycles_ignore_implausible_gaps():
    cycles = cd.UserCycles.from_periods(cd.clean_periods(periods_every([28, 75, 30])))
    assert cycles.raw_cycle_lengths == [28, 75, 30]
    assert cycles.cycle_lengths == [28, None, 30]
    assert cycles.period_lengths == [5, 5, 5, 5]


def test_clean_periods_drops_duplicates_and_bad_end_dates():
    df = cd.clean_periods(pd.DataFrame({
        cd.USER_ID: ["u", "u", "u"],
        cd.START: ["2026-01-01", "2026-01-01", "2026-02-01"],
        cd.END: ["2026-01-05", "2026-01-05", "2026-01-20"],
    }))
    assert len(df) == 2
    assert df[cd.END].iloc[1] is None or pd.isna(df[cd.END].iloc[1])


def test_training_rows_only_use_earlier_cycles():
    periods = periods_every([20, 30, 40])
    data = build_datasets(periods, pd.DataFrame(), pd.DataFrame())["cycle_length"]
    assert list(data.target) == [20, 30, 40]
    assert list(data.features["n_prior_cycles"]) == [0, 1, 2]
    assert data.features["last_cycle"].iloc[2] == 30
    assert data.features["mean_last3"].iloc[2] == 25  # (20 + 30) / 2, never its own 40
    assert np.isnan(data.features["last_cycle"].iloc[0])
    assert not any("user" in c for c in data.features.columns)


def test_conformal_quantile():
    scores = np.arange(1, 11, dtype=float)
    assert conformal_quantile(scores, 0.8) == 9.0
    with pytest.raises(ValueError):
        conformal_quantile(np.array([]), 0.8)


def test_models_beat_baselines_and_ranges_are_calibrated(cycle_bundle):
    metrics = cycle_bundle.metadata["metrics"]
    assert metrics["cycle_length"]["test"]["mae"] < metrics["cycle_length"]["test_fixed_28_days"]["mae"]
    assert metrics["pain"]["test"]["mae"] < metrics["pain"]["test_baseline"]["mae"]
    for task in ("cycle_length", "period_length", "pain"):
        assert 0.65 <= metrics[task]["interval_coverage"] <= 0.95


def test_bundle_round_trip(cycle_bundle, tmp_path):
    save_cycle_bundle(cycle_bundle, tmp_path)
    loaded = load_cycle_bundle(tmp_path)
    assert loaded.interval_quantiles == cycle_bundle.interval_quantiles
    with pytest.raises(ModelNotFoundError):
        load_cycle_bundle(tmp_path / "missing")


def test_no_periods_means_no_prediction(predictor):
    with pytest.raises(NoPeriodDataError):
        predictor.predict(pd.DataFrame(columns=[cd.USER_ID, cd.START, cd.END]), pd.DataFrame(), cd.Profile(), TODAY)


def test_first_period_uses_onboarding_length(predictor):
    f = predictor.predict(periods_every([]), pd.DataFrame(), cd.Profile(typical_cycle_length=31), TODAY)
    assert f.method == "onboarding_default"
    assert f.predicted_start == date(2026, 1, 5) + timedelta(days=31)
    assert f.personalization_level is PersonalizationLevel.NONE
    assert "No complete cycle" in f.explanation


def test_one_cycle_uses_recent_average(predictor):
    f = predictor.predict(periods_every([30]), pd.DataFrame(), cd.Profile(), TODAY)
    assert f.method == "recent_average"
    assert f.predicted_cycle_length == 30
    assert f.personalization_level is PersonalizationLevel.LIMITED


def test_regular_history_uses_model_close_to_the_pattern(predictor):
    periods = periods_every([30, 30, 31, 30, 30, 29])
    f = predictor.predict(periods, pd.DataFrame(), cd.Profile(), TODAY)
    assert f.method == "model"
    assert abs(f.predicted_cycle_length - 30) <= 2.5
    assert f.predicted_start == periods[cd.START].iloc[-1] + timedelta(days=round(f.predicted_cycle_length))
    assert 1 <= f.range_days <= 6
    assert f.personalization_level is PersonalizationLevel.PERSONALIZED


def test_pain_forecast_follows_logged_pain(predictor):
    periods = periods_every([28, 28, 28, 28])
    logs = pd.DataFrame([
        {cd.USER_ID: "u1", cd.LOG_DATE: s + timedelta(days=d), cd.PAIN: pain}
        for s in periods[cd.START] for d, pain in {0: 9, 1: 8, 2: 4, 3: 1}.items()
    ])
    f = predictor.predict(periods, logs, cd.Profile(), TODAY)
    by_day = {p.day: p for p in f.pain_forecast}
    assert by_day[0].expected_pain > by_day[3].expected_pain + 2
    assert all(0 <= p.low <= p.expected_pain <= p.high <= 10 for p in f.pain_forecast)
    assert by_day[0].date == f.predicted_start
    assert "most painful day" in f.explanation


def test_late_period_is_flagged(predictor):
    f = predictor.predict(periods_every([28, 28, 28]), pd.DataFrame(), cd.Profile(), date(2026, 6, 1))
    assert f.is_late and f.days_until_start < 0


@pytest.mark.parametrize("length", [21, 35])
def test_very_regular_short_or_long_cycles_are_trusted_over_signup_value(predictor, length):
    # Found in the live demo: 21-day cycles were predicted at ~27 days because the
    # sign-up value (28) pulled the model. The user's own regular history must win.
    f = predictor.predict(periods_every([length] * 5), pd.DataFrame(), cd.Profile(typical_cycle_length=28), TODAY)
    assert f.method == "model"
    assert abs(f.predicted_cycle_length - length) <= f.range_days
    assert abs(f.predicted_cycle_length - length) <= 1.5


def test_ovulation_is_estimated_two_weeks_before_the_predicted_period(predictor):
    f = predictor.predict(periods_every([28] * 6), pd.DataFrame(), cd.Profile(), TODAY)
    assert f.ovulation_date == f.predicted_start - timedelta(days=14)
    assert f.fertile_start == f.ovulation_date - timedelta(days=5)
    assert f.fertile_end == f.ovulation_date + timedelta(days=1)
    assert f.last_period_start < f.fertile_start


def test_ovulation_is_not_estimated_inside_the_last_period():
    last = date(2026, 9, 1)
    assert estimate_ovulation(last, last + timedelta(days=14)) is None
    ovulation, fertile_start, _ = estimate_ovulation(last, last + timedelta(days=17))
    assert ovulation == last + timedelta(days=3)
    assert fertile_start == last

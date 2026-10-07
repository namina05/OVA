import math

import numpy as np
import pandas as pd
import pytest

from ml import schema
from ml.preprocessing.cleaning import DataSchemaError, clean_sessions, cycle_phase_from_day
from ml.preprocessing.features import (
    FeatureSpec,
    TherapyContext,
    build_feature_row,
    build_training_frame,
)
from ml.preprocessing.history import UserHistory
from safety.limits import SafetyLimits
from safety.setting import TherapySetting

LIMITS = SafetyLimits()
SPEC = FeatureSpec(zones=LIMITS.allowed_zones, modes=LIMITS.allowed_modes)


def session(user="u1", day=1, zone="lower_abdomen", temp=40.0, dur=20.0, before=8, after=4, **extra):
    return {
        schema.USER_ID: user,
        schema.STARTED_AT: pd.Timestamp("2026-01-01", tz="UTC") + pd.Timedelta(days=day),
        schema.ZONE: zone,
        schema.TEMPERATURE: temp,
        schema.DURATION: dur,
        schema.MODE: "continuous",
        schema.PAIN_ZONE: zone,
        schema.PAIN_BEFORE: before,
        schema.PAIN_AFTER: after,
        schema.CYCLE_DAY: 2,
        **extra,
    }


def test_pain_reduction_and_phase_are_derived():
    df = clean_sessions(pd.DataFrame([session(before=7, after=2)]))
    assert df.loc[0, schema.PAIN_REDUCTION] == 5
    assert df.loc[0, schema.CYCLE_PHASE] == "menstrual"


@pytest.mark.parametrize("day, phase", [(None, "unknown"), (3, "menstrual"), (10, "follicular"), (15, "ovulatory"), (25, "luteal")])
def test_cycle_phase_from_day(day, phase):
    assert cycle_phase_from_day(day) == phase


def test_invalid_rows_are_dropped():
    rows = [
        session(day=1),
        session(day=2, temp=None),
        session(day=3, after=14),
        session(day=4, end_reason="fault"),
        session(day=5, dur=0),
    ]
    assert len(clean_sessions(pd.DataFrame(rows))) == 1


def test_missing_required_column_raises():
    with pytest.raises(DataSchemaError):
        clean_sessions(pd.DataFrame([session()]).drop(columns=[schema.PAIN_AFTER]))


def test_user_id_is_not_a_feature():
    assert not any("user" in c for c in SPEC.feature_columns)


def test_history_features_reflect_matching_sessions():
    df = clean_sessions(pd.DataFrame([
        session(day=1, zone="lower_back", temp=40, before=8, after=2),
        session(day=2, zone="lower_back", temp=38, before=8, after=4),
        session(day=3, zone="lower_abdomen", temp=40, before=8, after=7),
    ]))
    history = UserHistory.from_sessions(df)
    row = build_feature_row(
        SPEC, TherapyContext(pain_before=8), TherapySetting("lower_back", 40, 20, "continuous"), history
    )
    assert row["hist_n_sessions"] == 3
    assert row["hist_zone_n"] == 2 and row["hist_zone_mean_reduction"] == 5
    # within ±1°C of 40 → the two sessions at 40°C
    assert row["hist_temperature_n"] == 2 and row["hist_temperature_mean_reduction"] == 3.5
    assert row["zone_matches_pain"] == 0.0  # context has no pain zone


def test_cold_start_history_features_are_missing_not_zero():
    row = build_feature_row(
        SPEC, TherapyContext(pain_before=6), TherapySetting("lower_back", 40, 20, "continuous"), UserHistory.empty()
    )
    assert row["hist_n_sessions"] == 0
    assert math.isnan(row["hist_mean_reduction"])
    assert math.isnan(row["hist_zone_mean_reduction"])


def test_training_frame_uses_only_earlier_sessions():
    df = clean_sessions(pd.DataFrame([
        session(day=3, before=8, after=0),   # reduction 8, latest
        session(day=1, before=8, after=6),   # reduction 2, first
        session(day=2, before=8, after=4),   # reduction 4
    ]))
    X, y, groups = build_training_frame(SPEC, df)
    assert list(y) == [2, 4, 8]
    assert list(X["hist_n_sessions"]) == [0, 1, 2]
    assert math.isnan(X.loc[0, "hist_mean_reduction"])
    assert X.loc[1, "hist_mean_reduction"] == 2
    assert X.loc[2, "hist_mean_reduction"] == 3  # mean of 2 and 4; never its own 8
    assert set(groups) == {"u1"}
    assert list(X.columns) == SPEC.feature_columns


def test_feature_spec_round_trips():
    assert FeatureSpec.from_dict(SPEC.to_dict()) == SPEC

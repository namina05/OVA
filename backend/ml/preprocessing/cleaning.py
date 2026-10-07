"""Validates raw therapy-session rows and derives pain_reduction and cycle_phase."""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from ml import schema

logger = logging.getLogger(__name__)


class DataSchemaError(ValueError):
    """Raised when session data is missing required columns."""


def cycle_phase_from_day(cycle_day: float | None) -> str:
    """Approximate phase from the day of the cycle (assumes a ~28-day cycle)."""
    if cycle_day is None or pd.isna(cycle_day) or cycle_day < 1:
        return "unknown"
    if cycle_day <= 5:
        return "menstrual"
    if cycle_day <= 13:
        return "follicular"
    if cycle_day <= 16:
        return "ovulatory"
    return "luteal"


def normalize_cycle_phase(phase: object, cycle_day: float | None) -> str:
    if isinstance(phase, str) and phase in schema.CYCLE_PHASES and phase != "unknown":
        return phase
    return cycle_phase_from_day(cycle_day)


def clean_sessions(raw: pd.DataFrame) -> pd.DataFrame:
    """Return usable sessions sorted by user and time, with pain_reduction added.

    Rows with missing or out-of-range values, or that ended because of a fault,
    are dropped rather than guessed.
    """
    missing = [c for c in schema.REQUIRED_COLUMNS if c not in raw.columns]
    if missing:
        raise DataSchemaError(f"therapy session data is missing columns: {missing}")

    df = raw.copy()
    for col in schema.OPTIONAL_COLUMNS:
        if col not in df.columns:
            df[col] = None

    df[schema.USER_ID] = df[schema.USER_ID].astype("string")
    df[schema.STARTED_AT] = pd.to_datetime(df[schema.STARTED_AT], utc=True, errors="coerce")
    for col in (schema.TEMPERATURE, schema.DURATION, schema.PAIN_BEFORE, schema.PAIN_AFTER, schema.CYCLE_DAY):
        df[col] = pd.to_numeric(df[col], errors="coerce")

    usable = (
        df[schema.USER_ID].notna()
        & df[schema.STARTED_AT].notna()
        & df[schema.ZONE].notna()
        & df[schema.MODE].notna()
        & df[schema.TEMPERATURE].notna()
        & (df[schema.DURATION] > 0)
        & df[schema.PAIN_BEFORE].between(schema.PAIN_MIN, schema.PAIN_MAX)
        & df[schema.PAIN_AFTER].between(schema.PAIN_MIN, schema.PAIN_MAX)
        & ~df[schema.END_REASON].isin(schema.EXCLUDED_END_REASONS)
    )
    dropped = int((~usable).sum())
    if dropped:
        logger.info("dropped %d of %d therapy sessions with missing or invalid values", dropped, len(df))
    df = df[usable].copy()

    df[schema.ZONE] = df[schema.ZONE].astype(str)
    df[schema.MODE] = df[schema.MODE].astype(str)
    df[schema.PAIN_ZONE] = df[schema.PAIN_ZONE].where(df[schema.PAIN_ZONE].notna(), None)
    df[schema.PAIN_REDUCTION] = df[schema.PAIN_BEFORE] - df[schema.PAIN_AFTER]
    df[schema.CYCLE_PHASE] = [
        normalize_cycle_phase(phase, day)
        for phase, day in zip(df[schema.CYCLE_PHASE], df[schema.CYCLE_DAY].astype(float).replace({np.nan: None}))
    ]
    return df.sort_values([schema.USER_ID, schema.STARTED_AT], kind="stable").reset_index(drop=True)

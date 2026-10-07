"""Cleaning period, daily-log and profile rows, and turning periods into cycles.

Reads the existing tables (periods, daily_logs, profiles); nothing is copied.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np
import pandas as pd

USER_ID = "user_id"
START = "start_date"
END = "end_date"
LOG_DATE = "log_date"
PAIN = "pain"
SYMPTOMS = "symptoms"
DATE_OF_BIRTH = "date_of_birth"
TYPICAL_CYCLE = "typical_cycle_length"
TYPICAL_PERIOD = "typical_period_length"

# Same bounds as the database checks on profiles. A gap outside them is almost
# always a missed log, so it is not used to learn or predict cycle length.
MIN_CYCLE_DAYS, MAX_CYCLE_DAYS = 15, 60
MIN_PERIOD_DAYS, MAX_PERIOD_DAYS = 1, 15


class CycleDataError(ValueError):
    pass


@dataclass(frozen=True)
class Profile:
    date_of_birth: date | None = None
    typical_cycle_length: float | None = None
    typical_period_length: float | None = None

    def age_on(self, day: date) -> float | None:
        if self.date_of_birth is None:
            return None
        return (day - self.date_of_birth).days / 365.25

    @classmethod
    def from_row(cls, row: pd.Series | dict | None) -> "Profile":
        if row is None:
            return cls()
        get = row.get

        def _num(v):
            return None if v is None or pd.isna(v) else float(v)

        dob = get(DATE_OF_BIRTH)
        return cls(
            date_of_birth=None if dob is None or pd.isna(dob) else pd.Timestamp(dob).date(),
            typical_cycle_length=_num(get(TYPICAL_CYCLE)),
            typical_period_length=_num(get(TYPICAL_PERIOD)),
        )


def _to_date(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce").dt.date


def clean_periods(raw: pd.DataFrame) -> pd.DataFrame:
    missing = [c for c in (USER_ID, START) if c not in raw.columns]
    if missing:
        raise CycleDataError(f"period data is missing columns: {missing}")
    df = raw.copy()
    if END not in df.columns:
        df[END] = None
    df[USER_ID] = df[USER_ID].astype(str)
    df[START] = _to_date(df[START])
    df[END] = _to_date(df[END])
    df = df[df[START].notna()]
    bad_end = df[END].notna() & (pd.to_datetime(df[END]) < pd.to_datetime(df[START]))
    df.loc[bad_end, END] = None
    df = df.drop_duplicates([USER_ID, START]).sort_values([USER_ID, START], kind="stable")
    return df[[USER_ID, START, END]].reset_index(drop=True)


def clean_daily_logs(raw: pd.DataFrame) -> pd.DataFrame:
    missing = [c for c in (USER_ID, LOG_DATE) if c not in raw.columns]
    if missing:
        raise CycleDataError(f"daily log data is missing columns: {missing}")
    df = raw.copy()
    for col in (PAIN, SYMPTOMS):
        if col not in df.columns:
            df[col] = None
    df[USER_ID] = df[USER_ID].astype(str)
    df[LOG_DATE] = _to_date(df[LOG_DATE])
    df[PAIN] = pd.to_numeric(df[PAIN], errors="coerce")
    df.loc[~df[PAIN].between(0, 10), PAIN] = np.nan
    df[SYMPTOMS] = [list(s) if isinstance(s, (list, tuple, np.ndarray)) else [] for s in df[SYMPTOMS]]
    df = df[df[LOG_DATE].notna()].drop_duplicates([USER_ID, LOG_DATE], keep="last")
    return df[[USER_ID, LOG_DATE, PAIN, SYMPTOMS]].sort_values([USER_ID, LOG_DATE]).reset_index(drop=True)


@dataclass
class UserCycles:
    """One user's periods, oldest first."""

    starts: list[date]
    period_lengths: list[int | None]  # None while ongoing or implausible
    raw_cycle_lengths: list[int] = field(default_factory=list)  # gaps between starts, unfiltered

    @property
    def cycle_lengths(self) -> list[int | None]:
        """Gaps usable for learning; implausible ones (likely missed logs) become None."""
        return [c if MIN_CYCLE_DAYS <= c <= MAX_CYCLE_DAYS else None for c in self.raw_cycle_lengths]

    @classmethod
    def from_periods(cls, periods: pd.DataFrame) -> "UserCycles":
        """From cleaned periods of a single user."""
        starts = list(periods[START])
        lengths: list[int | None] = []
        for start, end in zip(periods[START], periods[END]):
            if end is None or pd.isna(end):
                lengths.append(None)
                continue
            length = (end - start).days + 1
            lengths.append(length if MIN_PERIOD_DAYS <= length <= MAX_PERIOD_DAYS else None)
        gaps = [(b - a).days for a, b in zip(starts, starts[1:])]
        return cls(starts, lengths, gaps)


def pain_by_offset(logs: pd.DataFrame, start: date, offsets: range) -> dict[int, float]:
    """Logged pain on each day relative to a period start (one user's cleaned logs)."""
    if logs.empty:
        return {}
    by_date = dict(zip(logs[LOG_DATE], logs[PAIN]))
    result: dict[int, float] = {}
    for d in offsets:
        value = by_date.get(start + timedelta(days=d))
        if value is not None and not pd.isna(value):
            result[d] = float(value)
    return result

"""Loaders for cycle datasets with one row per cycle.

Two formats are recognised by their columns:
  - spreadsheet format: User ID, Age, Cycle Start Date, Cycle Length, Period Length,
    Next Cycle Start Date (e.g. the "menstrual cycle data with factors" spreadsheet)
  - FedCycleData (Fehring, Marquette University): ClientID, CycleNumber,
    LengthofCycle, LengthofMenses, Age. It has no dates, so start dates are
    rebuilt from the cycle order; a gap in CycleNumber is treated as a missed log.
Other columns (BMI, stress, diet, ...) are not used: the app does not collect them.

Rows become the same tables the app stores (periods, profiles), so the
dataset trains exactly the features used in production.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from ml.cycle import data as cd

REQUIRED = ("User ID", "Age", "Cycle Start Date", "Cycle Length", "Period Length", "Next Cycle Start Date")


class DatasetError(ValueError):
    pass


@dataclass(frozen=True)
class CycleDataset:
    periods: pd.DataFrame
    profiles: pd.DataFrame
    daily_logs: pd.DataFrame  # the dataset has no daily pain logs


FEDCYCLE_COLUMNS = ("ClientID", "CycleNumber", "LengthofCycle", "LengthofMenses")
FEDCYCLE_ANCHOR = date(2012, 1, 1)  # rebuilt dates start here; only differences between dates matter


def _from_fedcycle(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw[[*FEDCYCLE_COLUMNS, "Age"]].copy()
    for col in ("CycleNumber", "LengthofCycle", "LengthofMenses", "Age"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["CycleNumber", "LengthofCycle"]).sort_values(["ClientID", "CycleNumber"])
    df["Age"] = df.groupby("ClientID")["Age"].transform(lambda a: a.ffill().bfill())
    rows = []
    for user_number, (client, cycles) in enumerate(df.groupby("ClientID", sort=True), start=1):
        start, previous_number = FEDCYCLE_ANCHOR, None
        for number, length, menses, age in zip(
            cycles["CycleNumber"], cycles["LengthofCycle"], cycles["LengthofMenses"], cycles["Age"]
        ):
            if previous_number is not None and number != previous_number + 1:
                start += timedelta(days=100)  # unknown missing cycles: a gap the models ignore
            rows.append({
                "User ID": user_number, "Client": client, "Age": age,
                "Cycle Start Date": start, "Cycle Length": int(length),
                "Period Length": menses, "Next Cycle Start Date": start + timedelta(days=int(length)),
            })
            start, previous_number = start + timedelta(days=int(length)), number
    return pd.DataFrame(rows)


def read_cycle_dataset(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    if path.suffix.lower() in (".xlsx", ".xls"):
        raw = pd.read_excel(path)
    else:
        raw = pd.read_csv(path, encoding="utf-8-sig", na_values=[" ", ""], low_memory=False)
    if all(c in raw.columns for c in FEDCYCLE_COLUMNS):
        return _from_fedcycle(raw)
    missing = [c for c in REQUIRED if c not in raw.columns]
    if missing:
        raise DatasetError(f"{path.name} is missing columns: {missing}")
    raw = raw.copy()
    for col in ("Cycle Start Date", "Next Cycle Start Date"):
        raw[col] = pd.to_datetime(raw[col]).dt.date
    gaps = [(n - s).days for s, n in zip(raw["Cycle Start Date"], raw["Next Cycle Start Date"])]
    if not np.array_equal(gaps, raw["Cycle Length"].to_numpy()):
        raise DatasetError("Cycle Length does not match Next Cycle Start Date - Cycle Start Date")
    return raw.sort_values(["User ID", "Cycle Start Date"]).reset_index(drop=True)


def split_users(raw: pd.DataFrame, holdout_fraction: float = 0.2, seed: int = 42) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split by user so no held-out user's cycles are seen in training."""
    users = np.array(sorted(raw["User ID"].unique()))
    rng = np.random.default_rng(seed)
    holdout = set(rng.choice(users, size=int(round(len(users) * holdout_fraction)), replace=False).tolist())
    is_holdout = raw["User ID"].isin(holdout)
    return raw[~is_holdout].reset_index(drop=True), raw[is_holdout].reset_index(drop=True)


def to_app_tables(raw: pd.DataFrame) -> CycleDataset:
    periods, profiles = [], []
    for user, rows in raw.groupby("User ID", sort=True):
        user_id = f"dataset-user-{int(user):04d}"
        starts = list(rows["Cycle Start Date"])
        for i, (start, length, next_start) in enumerate(
            zip(starts, rows["Period Length"], rows["Next Cycle Start Date"])
        ):
            known = length is not None and not pd.isna(length)
            periods.append({cd.USER_ID: user_id, cd.START: start,
                            cd.END: start + timedelta(days=int(length) - 1) if known else None})
            # A next start that isn't the following row's start (last row, or a missed log) is a
            # logged period start too, with unknown length.
            if i == len(starts) - 1 or starts[i + 1] != next_start:
                periods.append({cd.USER_ID: user_id, cd.START: next_start, cd.END: None})
        first, age = rows["Cycle Start Date"].iloc[0], rows["Age"].iloc[0]
        profiles.append({
            cd.USER_ID: user_id,
            cd.DATE_OF_BIRTH: None if pd.isna(age) else first - timedelta(days=int(age * 365.25)),
            cd.TYPICAL_CYCLE: None,  # not in the dataset: like users who skip it at sign-up
            cd.TYPICAL_PERIOD: None,
        })
    return CycleDataset(
        pd.DataFrame(periods), pd.DataFrame(profiles),
        pd.DataFrame(columns=[cd.USER_ID, cd.LOG_DATE, cd.PAIN, cd.SYMPTOMS]),
    )

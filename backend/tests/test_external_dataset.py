from datetime import date, timedelta

import pandas as pd
import pytest

from ml.cycle import data as cd
from ml.cycle.external_dataset import DatasetError, read_cycle_dataset, split_users, to_app_tables


def dataset_rows(users: int = 10, cycles: int = 3) -> pd.DataFrame:
    rows = []
    for u in range(1, users + 1):
        start = date(2025, 1, 1) + timedelta(days=u)
        for _ in range(cycles):
            rows.append({"User ID": u, "Age": 30, "BMI": 22.0, "Stress Level": 3, "Cycle Start Date": start,
                         "Cycle Length": 28, "Period Length": 5, "Next Cycle Start Date": start + timedelta(days=28),
                         "Symptoms": "Cramps"})
            start += timedelta(days=28)
    return pd.DataFrame(rows)


def test_reads_and_converts_to_app_tables(tmp_path):
    path = tmp_path / "cycles.csv"
    dataset_rows(users=2).to_csv(path, index=False)
    raw = read_cycle_dataset(path)
    tables = to_app_tables(raw)
    user_periods = tables.periods[tables.periods[cd.USER_ID] == "dataset-user-0001"]
    assert len(user_periods) == 4  # 3 cycles + the final next start
    assert user_periods[cd.END].iloc[0] == user_periods[cd.START].iloc[0] + timedelta(days=4)
    assert user_periods[cd.END].iloc[-1] is None
    assert cd.UserCycles.from_periods(cd.clean_periods(user_periods)).cycle_lengths == [28, 28, 28]
    assert tables.profiles[cd.TYPICAL_CYCLE].isna().all()


def test_inconsistent_cycle_length_is_rejected(tmp_path):
    df = dataset_rows(users=1)
    df.loc[0, "Cycle Length"] = 30
    df.to_csv(tmp_path / "bad.csv", index=False)
    with pytest.raises(DatasetError):
        read_cycle_dataset(tmp_path / "bad.csv")


def test_split_is_by_user_reproducible_and_80_20():
    raw = dataset_rows(users=10)
    train, holdout = split_users(raw, 0.2, seed=42)
    assert set(train["User ID"]).isdisjoint(holdout["User ID"])
    assert holdout["User ID"].nunique() == 2 and train["User ID"].nunique() == 8
    again_train, again_holdout = split_users(raw, 0.2, seed=42)
    assert set(again_holdout["User ID"]) == set(holdout["User ID"])


def test_fedcycle_format_rebuilds_dates_and_handles_missing_cycles(tmp_path):
    rows = [
        ("nfp1", 1, 28, 5, 30), ("nfp1", 2, 30, 4, None), ("nfp1", 4, 29, 5, None),  # cycle 3 missing
        ("nfp2", 1, 26, " ", 25),
    ]
    pd.DataFrame(rows, columns=["ClientID", "CycleNumber", "LengthofCycle", "LengthofMenses", "Age"]).to_csv(
        tmp_path / "fed.csv", index=False)
    raw = read_cycle_dataset(tmp_path / "fed.csv")
    assert list(raw["Age"][raw["Client"] == "nfp1"]) == [30, 30, 30]
    tables = to_app_tables(raw)
    p1 = cd.clean_periods(tables.periods[tables.periods[cd.USER_ID] == "dataset-user-0001"])
    cycles = cd.UserCycles.from_periods(p1)
    # 28, 30, then the missing cycle 3 (unknown) is skipped, then 29
    assert [c for c in cycles.cycle_lengths if c is not None] == [28, 30, 29]
    assert None in cycles.cycle_lengths
    p2 = tables.periods[tables.periods[cd.USER_ID] == "dataset-user-0002"]
    assert p2[cd.END].iloc[0] is None  # period length missing

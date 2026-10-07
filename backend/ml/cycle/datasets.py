"""Training rows for the three cycle models, built without looking ahead."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ml.cycle import data as cd
from ml.cycle.features import (
    CYCLE_FEATURES,
    PAIN_FEATURES,
    PAIN_OFFSETS,
    PERIOD_FEATURES,
    PainHistory,
    cycle_baseline,
    cycle_features,
    pain_features,
    period_baseline,
    period_features,
)

FALLBACK_CYCLE_SCALE = 3.0  # days; used for the range until a user has 2+ cycles


def cycle_scale(std_last6: float) -> float:
    """How spread out this user's cycles are, used to size the prediction range."""
    return FALLBACK_CYCLE_SCALE if math.isnan(std_last6) else float(np.clip(std_last6, 1.0, 10.0))


def cap_cycle_adjustment(adjustment: np.ndarray | float, std_last6: np.ndarray | float):
    """Limit the model's correction to the user's own cycle-to-cycle variation (at least 1 day).

    A very regular history is better evidence than population patterns or a stale
    sign-up value, so the model may refine the recent average but not override it.
    """
    std = np.nan_to_num(np.asarray(std_last6, dtype=float), nan=FALLBACK_CYCLE_SCALE)
    limit = np.maximum(1.0, std)
    return np.clip(adjustment, -limit, limit)


@dataclass
class TaskData:
    features: pd.DataFrame
    target: np.ndarray  # the actual value
    baseline: np.ndarray  # the model learns target - baseline
    scale: np.ndarray  # spread used to size the prediction range
    groups: np.ndarray  # user ids, for splitting only
    extra: dict[str, np.ndarray] = field(default_factory=dict)

    @property
    def residual(self) -> np.ndarray:
        return self.target - self.baseline


def _task(columns: tuple[str, ...], rows: list[dict], target, baseline, scale, groups, **extra) -> TaskData:
    return TaskData(
        pd.DataFrame(rows, columns=list(columns), dtype=float),
        np.asarray(target, dtype=float), np.asarray(baseline, dtype=float),
        np.asarray(scale, dtype=float), np.asarray(groups), {k: np.asarray(v) for k, v in extra.items()},
    )


def build_datasets(
    periods: pd.DataFrame, daily_logs: pd.DataFrame, profiles: pd.DataFrame
) -> dict[str, TaskData]:
    periods = cd.clean_periods(periods)
    logs = cd.clean_daily_logs(daily_logs) if not daily_logs.empty else cd.clean_daily_logs(
        pd.DataFrame(columns=[cd.USER_ID, cd.LOG_DATE])
    )
    profile_by_user = {
        str(r[cd.USER_ID]): cd.Profile.from_row(r) for _, r in profiles.iterrows()
    } if not profiles.empty else {}
    logs_by_user = {u: g for u, g in logs.groupby(cd.USER_ID)}

    cyc = {"rows": [], "target": [], "baseline": [], "scale": [], "groups": [], "n_prior": []}
    per = {"rows": [], "target": [], "baseline": [], "scale": [], "groups": []}
    pain = {"rows": [], "target": [], "baseline": [], "scale": [], "groups": [], "n_prior": []}

    for user_id, user_periods in periods.groupby(cd.USER_ID, sort=False):
        profile = profile_by_user.get(str(user_id), cd.Profile())
        cycles = cd.UserCycles.from_periods(user_periods)
        cycle_lengths = cycles.cycle_lengths
        user_logs = logs_by_user.get(user_id, logs.iloc[0:0])
        pain_per_period = [cd.pain_by_offset(user_logs, s, PAIN_OFFSETS) for s in cycles.starts]

        for k, start in enumerate(cycles.starts):
            age = profile.age_on(start)
            prior_cycles = [float(c) for c in cycle_lengths[:k] if c is not None]
            prior_periods = [float(p) for p in cycles.period_lengths[:k] if p is not None]

            if k < len(cycle_lengths) and cycle_lengths[k] is not None:
                f = cycle_features(prior_cycles, prior_periods, profile, age)
                cyc["rows"].append(f)
                cyc["target"].append(cycle_lengths[k])
                cyc["baseline"].append(f["baseline"])
                cyc["scale"].append(cycle_scale(f["std_last6"]))
                cyc["groups"].append(user_id)
                cyc["n_prior"].append(len(prior_cycles))

            if cycles.period_lengths[k] is not None:
                f = period_features(prior_periods, prior_cycles, profile, age)
                per["rows"].append(f)
                per["target"].append(cycles.period_lengths[k])
                per["baseline"].append(f["baseline"])
                per["scale"].append(1.0)
                per["groups"].append(user_id)

            history = PainHistory(pain_per_period[:k])
            expected = period_baseline(prior_periods, profile).value
            for day, value in pain_per_period[k].items():
                pain["rows"].append(pain_features(day, history, expected, age))
                pain["target"].append(value)
                pain["baseline"].append(0.0)
                pain["scale"].append(1.0)
                pain["groups"].append(user_id)
                pain["n_prior"].append(history.n_with_data)

    return {
        "cycle_length": _task(CYCLE_FEATURES, cyc["rows"], cyc["target"], cyc["baseline"], cyc["scale"],
                              cyc["groups"], n_prior=cyc["n_prior"]),
        "period_length": _task(PERIOD_FEATURES, per["rows"], per["target"], per["baseline"], per["scale"],
                               per["groups"]),
        "pain": _task(PAIN_FEATURES, pain["rows"], pain["target"], pain["baseline"], pain["scale"],
                      pain["groups"], n_prior=pain["n_prior"]),
    }

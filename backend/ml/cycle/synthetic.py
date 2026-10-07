"""Synthetic periods, daily pain logs and profiles for development and tests.

NOT clinical data: the cycle and pain patterns below are invented so the
pipeline can run before real users exist. Never deploy a model trained on it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd

from ml.cycle import data as cd

# Pain shape around a period start, as a fraction of the user's peak pain.
_PAIN_SHAPE = {-2: 0.25, -1: 0.55, 0: 1.0, 1: 0.9, 2: 0.6, 3: 0.35, 4: 0.2, 5: 0.15, 6: 0.1, 7: 0.1, 8: 0.1, 9: 0.1}


@dataclass(frozen=True)
class SyntheticCycleData:
    periods: pd.DataFrame
    daily_logs: pd.DataFrame
    profiles: pd.DataFrame


def _signup_cycle_length(rng: np.random.Generator, base_cycle: float) -> int | None:
    """What a user types at sign-up: often close, often just 28, sometimes skipped."""
    r = rng.random()
    if r < 0.5:
        return int(round(base_cycle + rng.normal(0, 1.5)))
    if r < 0.8:
        return 28
    return None


def generate_synthetic_cycles(
    n_users: int = 300,
    cycles_per_user: tuple[int, int] = (2, 14),
    end: date = date(2026, 10, 1),
    seed: int = 3,
) -> SyntheticCycleData:
    rng = np.random.default_rng(seed)
    periods, logs, profiles = [], [], []
    for u in range(n_users):
        user_id = f"synthetic-user-{u:04d}"
        age = float(rng.uniform(16, 45))
        irregular = rng.random() < 0.1
        # Most users near 28 days, some with naturally short or long cycles.
        base_cycle = float(np.clip(rng.normal(28.5, 2.5), 22, 36) if rng.random() < 0.85 else rng.uniform(19, 45))
        cycle_sd = float(rng.uniform(4, 8) if irregular else rng.uniform(0.7, 3.0))
        drift = float(rng.normal(0, 0.15))  # slow trend in cycle length
        base_period = float(np.clip(rng.normal(5.0, 1.0), 3, 8))
        peak_pain = float(rng.uniform(2, 9))
        log_rate = float(rng.uniform(0.4, 0.95))

        n = int(rng.integers(cycles_per_user[0], cycles_per_user[1] + 1))
        lengths = [
            int(round(np.clip(base_cycle + drift * i + rng.normal(0, cycle_sd), 18, 50))) for i in range(n)
        ]
        start = end - timedelta(days=sum(lengths) + int(rng.integers(0, 20)))
        for i in range(n + 1):
            period_len = int(np.clip(round(base_period + rng.normal(0, 0.8)), 2, 10))
            ongoing = i == n and rng.random() < 0.5
            periods.append({
                cd.USER_ID: user_id, cd.START: start,
                cd.END: None if ongoing else start + timedelta(days=period_len - 1),
            })
            cycle_peak = peak_pain * float(np.clip(rng.normal(1, 0.15), 0.6, 1.4))
            for d, share in _PAIN_SHAPE.items():
                if rng.random() < log_rate and start + timedelta(days=d) <= end:
                    shape = share if d < period_len else 0.08
                    pain = int(np.clip(round(cycle_peak * shape + rng.normal(0, 0.8)), 0, 10))
                    logs.append({cd.USER_ID: user_id, cd.LOG_DATE: start + timedelta(days=d),
                                 cd.PAIN: pain, cd.SYMPTOMS: []})
            if i < n:
                start = start + timedelta(days=lengths[i])

        profiles.append({
            cd.USER_ID: user_id,
            cd.DATE_OF_BIRTH: end - timedelta(days=int(age * 365.25)),
            cd.TYPICAL_CYCLE: _signup_cycle_length(rng, base_cycle),
            cd.TYPICAL_PERIOD: int(round(base_period)) if rng.random() < 0.8 else None,
        })
    return SyntheticCycleData(pd.DataFrame(periods), pd.DataFrame(logs), pd.DataFrame(profiles))

"""Synthetic therapy sessions for development and tests.

NOT clinical data. The response curve below is made up so the pipeline can be
exercised before real sessions exist. Never ship a model trained on it.

Each simulated user has a preferred zone, an optimal temperature, a preferred
duration and an overall responsiveness, so the data has the per-user structure
the personalization features are meant to pick up.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ml import schema
from safety.limits import SafetyLimits


def generate_synthetic_sessions(
    n_users: int = 200,
    sessions_per_user: tuple[int, int] = (3, 30),
    limits: SafetyLimits | None = None,
    seed: int = 7,
) -> pd.DataFrame:
    limits = limits or SafetyLimits()
    rng = np.random.default_rng(seed)
    zones = list(limits.allowed_zones)
    modes = list(limits.allowed_modes)
    temps = np.arange(limits.min_temperature_c, limits.max_temperature_c + 1e-9, limits.temperature_step_c)
    durations = np.arange(limits.min_duration_min, limits.max_duration_min + 1e-9, limits.duration_step_min)
    pain_zone_weights = np.array([0.5, 0.3, 0.1, 0.1][: len(zones)] + [0.1] * max(0, len(zones) - 4))
    pain_zone_weights /= pain_zone_weights.sum()
    phase_effect = {"menstrual": 1.0, "follicular": 0.85, "ovulatory": 0.85, "luteal": 0.95}

    records: list[dict] = []
    start = pd.Timestamp("2026-01-01", tz="UTC")
    for u in range(n_users):
        user_id = f"synthetic-user-{u:04d}"
        preferred_zone = rng.choice(zones)
        optimal_temp = rng.uniform(38.5, 41.5)
        preferred_duration = rng.uniform(15, 25)
        responsiveness = float(np.clip(rng.normal(1.0, 0.25), 0.4, 1.6))
        preferred_mode = rng.choice(modes)
        n_sessions = int(rng.integers(sessions_per_user[0], sessions_per_user[1] + 1))
        for s in range(n_sessions):
            cycle_day = int(rng.integers(1, 6)) if rng.random() < 0.7 else int(rng.integers(6, 29))
            phase = schema.CYCLE_PHASES[0] if cycle_day <= 5 else (
                "follicular" if cycle_day <= 13 else "ovulatory" if cycle_day <= 16 else "luteal"
            )
            pain_zone = rng.choice(zones, p=pain_zone_weights)
            zone = pain_zone if rng.random() < 0.6 else rng.choice(zones)
            temperature = float(rng.choice(temps))
            duration = float(rng.choice(durations))
            if temperature >= limits.high_temperature_threshold_c:
                duration = min(duration, limits.max_duration_at_high_temperature_min)
            mode = rng.choice(modes)
            pain_before = int(rng.integers(3, 11))

            temp_factor = np.exp(-(((temperature - optimal_temp) / 2.0) ** 2))
            duration_factor = 0.4 + 0.6 * min(duration, preferred_duration) / preferred_duration
            zone_factor = 0.5 + 0.3 * (zone == pain_zone) + 0.3 * (zone == preferred_zone)
            mode_factor = 1.0 if mode == preferred_mode else 0.9
            expected = (
                0.55 * pain_before * responsiveness * temp_factor * duration_factor
                * zone_factor * mode_factor * phase_effect[phase]
            )
            pain_after = int(np.clip(round(pain_before - expected + rng.normal(0, 0.7)), 0, 10))
            records.append(
                {
                    schema.SESSION_ID: f"{user_id}-s{s:03d}",
                    schema.USER_ID: user_id,
                    schema.STARTED_AT: start + pd.Timedelta(days=int(s * 9 + rng.integers(0, 4))),
                    schema.ZONE: zone,
                    schema.TEMPERATURE: temperature,
                    schema.DURATION: duration,
                    schema.MODE: mode,
                    schema.PAIN_ZONE: pain_zone,
                    schema.PAIN_BEFORE: pain_before,
                    schema.PAIN_AFTER: pain_after,
                    schema.CYCLE_DAY: cycle_day,
                    schema.END_REASON: "completed",
                }
            )
    return pd.DataFrame.from_records(records)

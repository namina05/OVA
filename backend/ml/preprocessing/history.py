"""A user's past therapy outcomes, summarised for one candidate setting.

This is the personalization input: the same general XGBoost model receives
these per-user statistics as features, so a user's own history changes the
prediction without retraining the model after every session.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ml import schema


@dataclass(frozen=True)
class HistoryStat:
    """Number of matching past sessions and their mean pain reduction (None if none)."""

    n: int
    mean_reduction: float | None


@dataclass(frozen=True)
class HistoryParams:
    temperature_tolerance_c: float = 1.0
    duration_tolerance_min: float = 5.0
    recent_window: int = 3


class UserHistory:
    """Sessions of one user, oldest first, held as arrays for fast lookups."""

    def __init__(
        self,
        zones: np.ndarray,
        temperatures: np.ndarray,
        durations: np.ndarray,
        reductions: np.ndarray,
    ) -> None:
        self.zones = zones
        self.temperatures = temperatures
        self.durations = durations
        self.reductions = reductions

    @classmethod
    def empty(cls) -> "UserHistory":
        return cls(np.array([], dtype=object), np.array([]), np.array([]), np.array([]))

    @classmethod
    def from_sessions(cls, sessions: pd.DataFrame) -> "UserHistory":
        """Build from cleaned sessions (see clean_sessions) of a single user."""
        if sessions.empty:
            return cls.empty()
        ordered = sessions.sort_values(schema.STARTED_AT, kind="stable")
        return cls(
            ordered[schema.ZONE].to_numpy(dtype=object),
            ordered[schema.TEMPERATURE].to_numpy(dtype=float),
            ordered[schema.DURATION].to_numpy(dtype=float),
            ordered[schema.PAIN_REDUCTION].to_numpy(dtype=float),
        )

    def prefix(self, n: int) -> "UserHistory":
        """The first n sessions: what was known before session n."""
        return UserHistory(self.zones[:n], self.temperatures[:n], self.durations[:n], self.reductions[:n])

    @property
    def n_sessions(self) -> int:
        return len(self.reductions)

    def _stat(self, mask: np.ndarray) -> HistoryStat:
        n = int(mask.sum())
        return HistoryStat(n, float(self.reductions[mask].mean()) if n else None)

    def overall(self) -> HistoryStat:
        return self._stat(np.ones(self.n_sessions, dtype=bool))

    def recent(self, params: HistoryParams) -> HistoryStat:
        mask = np.zeros(self.n_sessions, dtype=bool)
        mask[-params.recent_window:] = True
        return self._stat(mask)

    def for_zone(self, zone: str) -> HistoryStat:
        return self._stat(self.zones == zone)

    def for_temperature(self, temperature_c: float, params: HistoryParams) -> HistoryStat:
        return self._stat(np.abs(self.temperatures - temperature_c) <= params.temperature_tolerance_c)

    def for_duration(self, duration_min: float, params: HistoryParams) -> HistoryStat:
        return self._stat(np.abs(self.durations - duration_min) <= params.duration_tolerance_min)

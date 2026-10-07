"""Features for the cycle-length, period-length and pain models.

Every feature for period k is computed from that user's history BEFORE period
k started, the same way at training and at prediction time. Each model learns
a correction to a personal baseline rather than the raw value.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from ml.cycle.data import Profile

DEFAULT_CYCLE_LENGTH = 28.0
DEFAULT_PERIOD_LENGTH = 5.0
PAIN_OFFSETS = range(-2, 10)  # days relative to the period start; pain can start 1-2 days before

CYCLE_FEATURES: tuple[str, ...] = (
    "n_prior_cycles", "last_cycle", "mean_last3", "median_prior", "std_last6",
    "min_last6", "max_last6", "trend", "typical_cycle_length", "age", "mean_period_length", "baseline",
)
PERIOD_FEATURES: tuple[str, ...] = (
    "n_prior_periods", "last_period", "mean_last3_period", "std_period",
    "typical_period_length", "age", "mean_cycle", "baseline",
)
PAIN_FEATURES: tuple[str, ...] = (
    "day", "within_expected_period", "prior_mean_pain_day", "last_pain_day", "prior_mean_pain_period",
    "prior_peak_pain_mean", "n_prior_pain_periods", "expected_period_length", "age",
)


def _nan(value: float | None) -> float:
    return math.nan if value is None else float(value)


def _mean(values: list[float]) -> float | None:
    return float(np.mean(values)) if values else None


@dataclass(frozen=True)
class Baseline:
    value: float
    description: str


def cycle_baseline(prior_cycles: list[float], profile: Profile) -> Baseline:
    recent = prior_cycles[-3:]
    if recent:
        n = len(recent)
        return Baseline(float(np.mean(recent)), f"your last {n} cycles" if n > 1 else "your last cycle")
    if profile.typical_cycle_length:
        return Baseline(profile.typical_cycle_length, "the cycle length you entered at sign-up")
    return Baseline(DEFAULT_CYCLE_LENGTH, "a typical 28-day cycle")


def period_baseline(prior_periods: list[float], profile: Profile) -> Baseline:
    recent = prior_periods[-3:]
    if recent:
        n = len(recent)
        return Baseline(float(np.mean(recent)), f"your last {n} periods" if n > 1 else "your last period")
    if profile.typical_period_length:
        return Baseline(profile.typical_period_length, "the period length you entered at sign-up")
    return Baseline(DEFAULT_PERIOD_LENGTH, "a typical 5-day period")


def cycle_features(
    prior_cycles: list[float], prior_periods: list[float], profile: Profile, age: float | None
) -> dict[str, float]:
    last6 = prior_cycles[-6:]
    mean3 = _mean(prior_cycles[-3:])
    return {
        "n_prior_cycles": float(len(prior_cycles)),
        "last_cycle": _nan(prior_cycles[-1] if prior_cycles else None),
        "mean_last3": _nan(mean3),
        "median_prior": _nan(float(np.median(prior_cycles)) if prior_cycles else None),
        "std_last6": _nan(float(np.std(last6, ddof=1)) if len(last6) >= 2 else None),
        "min_last6": _nan(min(last6) if last6 else None),
        "max_last6": _nan(max(last6) if last6 else None),
        "trend": _nan(prior_cycles[-1] - mean3 if prior_cycles else None),
        "typical_cycle_length": _nan(profile.typical_cycle_length),
        "age": _nan(age),
        "mean_period_length": _nan(_mean(prior_periods[-3:])),
        "baseline": cycle_baseline(prior_cycles, profile).value,
    }


def period_features(
    prior_periods: list[float], prior_cycles: list[float], profile: Profile, age: float | None
) -> dict[str, float]:
    return {
        "n_prior_periods": float(len(prior_periods)),
        "last_period": _nan(prior_periods[-1] if prior_periods else None),
        "mean_last3_period": _nan(_mean(prior_periods[-3:])),
        "std_period": _nan(float(np.std(prior_periods[-6:], ddof=1)) if len(prior_periods[-6:]) >= 2 else None),
        "typical_period_length": _nan(profile.typical_period_length),
        "age": _nan(age),
        "mean_cycle": _nan(_mean(prior_cycles[-3:])),
        "baseline": period_baseline(prior_periods, profile).value,
    }


@dataclass(frozen=True)
class PainHistory:
    """Pain logged around each earlier period: one {offset: pain} dict per period."""

    periods: list[dict[int, float]]

    def mean_on_day(self, day: int) -> float | None:
        return _mean([p[day] for p in self.periods if day in p])

    def last_on_day(self, day: int) -> float | None:
        for p in reversed(self.periods):
            if day in p:
                return p[day]
        return None

    def mean_period_pain(self) -> float | None:
        return _mean([v for p in self.periods for d, v in p.items() if 0 <= d <= 2])

    def mean_peak(self) -> float | None:
        return _mean([max(p.values()) for p in self.periods if p])

    @property
    def n_with_data(self) -> int:
        return sum(1 for p in self.periods if p)


def pain_features(
    day: int, history: PainHistory, expected_period_length: float, age: float | None
) -> dict[str, float]:
    return {
        "day": float(day),
        "within_expected_period": float(0 <= day < expected_period_length),
        "prior_mean_pain_day": _nan(history.mean_on_day(day)),
        "last_pain_day": _nan(history.last_on_day(day)),
        "prior_mean_pain_period": _nan(history.mean_period_pain()),
        "prior_peak_pain_mean": _nan(history.mean_peak()),
        "n_prior_pain_periods": float(history.n_with_data),
        "expected_period_length": float(expected_period_length),
        "age": _nan(age),
    }

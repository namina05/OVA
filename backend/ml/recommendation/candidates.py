"""The fixed grid of settings the recommender may choose from.

The model only ranks these; it never produces a temperature or duration of its
own. Every candidate is built from SafetyLimits and must pass the
SafetyValidator before it is even scored.
"""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np

from safety.limits import SafetyLimits
from safety.setting import TherapySetting
from safety.validator import SafetyValidator


def _grid(low: float, high: float, step: float) -> list[float]:
    count = int(np.floor((high - low) / step + 1e-9)) + 1
    return [round(low + i * step, 2) for i in range(count)]


def generate_candidates(
    limits: SafetyLimits,
    validator: SafetyValidator,
    zones: Iterable[str] | None = None,
    modes: Iterable[str] | None = None,
) -> list[TherapySetting]:
    zones = list(zones) if zones is not None else list(limits.allowed_zones)
    modes = list(modes) if modes is not None else list(limits.allowed_modes)
    candidates = [
        TherapySetting(zone, temperature, duration, mode)
        for zone in zones
        for mode in modes
        for temperature in _grid(limits.min_temperature_c, limits.max_temperature_c, limits.temperature_step_c)
        for duration in _grid(limits.min_duration_min, limits.max_duration_min, limits.duration_step_min)
    ]
    return [c for c in candidates if validator.validate(c).approved]

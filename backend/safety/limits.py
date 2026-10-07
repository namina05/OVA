"""Configurable safety limits for heating settings.

These limits are the single source of truth for what the software layer may
recommend. They live here and nowhere else: the candidate generator, the
SafetyValidator and the API all read from a SafetyLimits instance.

They are NOT a replacement for the device's own protections. The ESP32
firmware, hardware over-temperature cut-off, current limiting and automatic
shut-off remain the final, independent safety layer.

Configuration, in order of precedence:
  1. Environment variables (OVA_SAFETY_MIN_TEMPERATURE_C, ...; see ENV_FIELDS)
  2. A JSON file whose path is in OVA_SAFETY_CONFIG
  3. The defaults below
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path
from typing import Any, Mapping

# Zone names in the order of the zone numbers (1..4) stored in session_zones.
# Confirm these against the belt's hardware layout before release.
DEFAULT_ZONES: tuple[str, ...] = ("lower_abdomen", "lower_back", "left_abdomen", "right_abdomen")
DEFAULT_MODES: tuple[str, ...] = ("continuous", "pulse")

# Hard sanity ceilings: configuration above these is refused at load time, so a
# typo such as 400 instead of 40 can never become a recommendation limit.
ABSOLUTE_MAX_TEMPERATURE_C = 45.0
ABSOLUTE_MIN_TEMPERATURE_C = 30.0
ABSOLUTE_MAX_DURATION_MIN = 60.0

ENV_PREFIX = "OVA_SAFETY_"
CONFIG_PATH_ENV = "OVA_SAFETY_CONFIG"


class SafetyConfigError(ValueError):
    """Raised when the safety configuration itself is invalid."""


@dataclass(frozen=True)
class SafetyLimits:
    min_temperature_c: float = 37.0
    max_temperature_c: float = 42.0
    temperature_step_c: float = 1.0
    min_duration_min: float = 10.0
    max_duration_min: float = 30.0
    duration_step_min: float = 5.0
    allowed_zones: tuple[str, ...] = DEFAULT_ZONES
    allowed_modes: tuple[str, ...] = DEFAULT_MODES
    # Longer sessions are only allowed at milder temperatures.
    high_temperature_threshold_c: float = 41.0
    max_duration_at_high_temperature_min: float = 20.0

    def __post_init__(self) -> None:
        numbers = {
            f.name: getattr(self, f.name)
            for f in fields(self)
            if f.name not in ("allowed_zones", "allowed_modes")
        }
        for name, value in numbers.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise SafetyConfigError(f"{name} must be a finite number, got {value!r}")
        if not ABSOLUTE_MIN_TEMPERATURE_C <= self.min_temperature_c < self.max_temperature_c <= ABSOLUTE_MAX_TEMPERATURE_C:
            raise SafetyConfigError(
                "temperature limits must satisfy "
                f"{ABSOLUTE_MIN_TEMPERATURE_C} <= min < max <= {ABSOLUTE_MAX_TEMPERATURE_C}"
            )
        if not 0 < self.min_duration_min < self.max_duration_min <= ABSOLUTE_MAX_DURATION_MIN:
            raise SafetyConfigError(f"duration limits must satisfy 0 < min < max <= {ABSOLUTE_MAX_DURATION_MIN}")
        if self.temperature_step_c <= 0 or self.duration_step_min <= 0:
            raise SafetyConfigError("step sizes must be positive")
        if not self.min_duration_min <= self.max_duration_at_high_temperature_min <= self.max_duration_min:
            raise SafetyConfigError("max_duration_at_high_temperature_min must lie within the duration limits")
        if not self.allowed_zones or not self.allowed_modes:
            raise SafetyConfigError("allowed_zones and allowed_modes must not be empty")
        if any(not isinstance(z, str) or not z for z in (*self.allowed_zones, *self.allowed_modes)):
            raise SafetyConfigError("zone and mode names must be non-empty strings")

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["allowed_zones"] = list(self.allowed_zones)
        data["allowed_modes"] = list(self.allowed_modes)
        return data

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "SafetyLimits":
        known = {f.name for f in fields(cls)}
        unknown = set(data) - known
        if unknown:
            raise SafetyConfigError(f"unknown safety settings: {sorted(unknown)}")
        values = dict(data)
        for key in ("allowed_zones", "allowed_modes"):
            if key in values:
                values[key] = tuple(values[key])
        return cls(**values)


def _parse_env_value(name: str, raw: str) -> Any:
    if name in ("allowed_zones", "allowed_modes"):
        return tuple(part.strip() for part in raw.split(",") if part.strip())
    try:
        return float(raw)
    except ValueError as exc:
        raise SafetyConfigError(f"{ENV_PREFIX}{name.upper()} must be a number, got {raw!r}") from exc


def load_safety_limits(environ: Mapping[str, str] | None = None) -> SafetyLimits:
    """Build SafetyLimits from defaults, an optional JSON file and env overrides."""
    env = os.environ if environ is None else environ
    limits = SafetyLimits()

    config_path = env.get(CONFIG_PATH_ENV)
    if config_path:
        try:
            data = json.loads(Path(config_path).read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise SafetyConfigError(f"cannot read safety config {config_path}: {exc}") from exc
        limits = SafetyLimits.from_mapping({**limits.to_dict(), **data})

    overrides = {
        f.name: _parse_env_value(f.name, env[f"{ENV_PREFIX}{f.name.upper()}"])
        for f in fields(SafetyLimits)
        if f"{ENV_PREFIX}{f.name.upper()}" in env
    }
    return replace(limits, **overrides) if overrides else limits

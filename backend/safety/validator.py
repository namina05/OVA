"""Rule-based SafetyValidator.

Every setting is checked here before the user sees it and again before a
device command is built. The validator never adjusts a setting: an unsafe
value is rejected, so nothing reaches the user that the rules did not approve
exactly as shown.

The ML model never talks to the heater. The flow is:
    ML recommendation -> SafetyValidator -> user confirmation -> device command
and the ESP32 firmware still enforces its own limits after that.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping

from safety.limits import SafetyLimits
from safety.setting import TherapySetting


class SafetyStatus(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass(frozen=True)
class ValidationResult:
    status: SafetyStatus
    violations: tuple[str, ...] = ()

    @property
    def approved(self) -> bool:
        return self.status is SafetyStatus.APPROVED


def _as_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


class SafetyValidator:
    def __init__(self, limits: SafetyLimits) -> None:
        self.limits = limits

    def validate(self, setting: TherapySetting | Mapping[str, Any]) -> ValidationResult:
        data = setting.to_dict() if isinstance(setting, TherapySetting) else dict(setting)
        limits = self.limits
        violations: list[str] = []

        zone = data.get("zone")
        if not isinstance(zone, str) or not zone:
            violations.append("zone is missing")
        elif zone not in limits.allowed_zones:
            violations.append(f"zone '{zone}' is not a valid heating zone")

        mode = data.get("therapy_mode")
        if not isinstance(mode, str) or not mode:
            violations.append("therapy_mode is missing")
        elif mode not in limits.allowed_modes:
            violations.append(f"therapy_mode '{mode}' is not allowed")

        temperature = _as_number(data.get("temperature_c"))
        if temperature is None:
            violations.append("temperature_c is missing or not a number")
        elif not limits.min_temperature_c <= temperature <= limits.max_temperature_c:
            violations.append(
                f"temperature {temperature:g}°C is outside "
                f"{limits.min_temperature_c:g}-{limits.max_temperature_c:g}°C"
            )

        duration = _as_number(data.get("duration_min"))
        if duration is None:
            violations.append("duration_min is missing or not a number")
        elif not limits.min_duration_min <= duration <= limits.max_duration_min:
            violations.append(
                f"duration {duration:g} min is outside "
                f"{limits.min_duration_min:g}-{limits.max_duration_min:g} min"
            )

        if (
            temperature is not None
            and duration is not None
            and temperature >= limits.high_temperature_threshold_c
            and duration > limits.max_duration_at_high_temperature_min
        ):
            violations.append(
                f"the maximum duration at {limits.high_temperature_threshold_c:g}°C or hotter is "
                f"{limits.max_duration_at_high_temperature_min:g} min (requested {temperature:g}°C for {duration:g} min)"
            )

        if violations:
            return ValidationResult(SafetyStatus.REJECTED, tuple(violations))
        return ValidationResult(SafetyStatus.APPROVED)

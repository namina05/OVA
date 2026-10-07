"""Turns a confirmed, validated setting into a command payload for the app.

The mobile app sends this payload to the belt over BLE. It is only built when
the user has confirmed the setting AND the SafetyValidator approves it again
(the user may have edited the recommendation). The ESP32 still applies its own
temperature, current and auto-shutoff limits regardless of what it receives.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from safety.setting import TherapySetting
from safety.validator import SafetyValidator, ValidationResult


class DeviceCommandRefused(Exception):
    def __init__(self, reasons: tuple[str, ...]) -> None:
        super().__init__("; ".join(reasons))
        self.reasons = reasons


@dataclass(frozen=True)
class DeviceCommand:
    zone: str
    target_temperature_c: float
    duration_s: int
    therapy_mode: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "zone": self.zone,
            "target_temperature_c": self.target_temperature_c,
            "duration_s": self.duration_s,
            "therapy_mode": self.therapy_mode,
        }


def prepare_device_command(
    setting: Mapping[str, Any],
    user_confirmed: bool,
    validator: SafetyValidator,
) -> DeviceCommand:
    if user_confirmed is not True:
        raise DeviceCommandRefused(("the user has not confirmed this setting",))
    result: ValidationResult = validator.validate(setting)
    if not result.approved:
        raise DeviceCommandRefused(result.violations)
    checked = TherapySetting(
        zone=setting["zone"],
        temperature_c=float(setting["temperature_c"]),
        duration_min=float(setting["duration_min"]),
        therapy_mode=setting["therapy_mode"],
    )
    return DeviceCommand(
        zone=checked.zone,
        target_temperature_c=checked.temperature_c,
        duration_s=int(round(checked.duration_min * 60)),
        therapy_mode=checked.therapy_mode,
    )

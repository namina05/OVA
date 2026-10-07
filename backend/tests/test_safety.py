import json
import math

import pytest

from safety.device_command import DeviceCommandRefused, prepare_device_command
from safety.limits import SafetyConfigError, SafetyLimits, load_safety_limits
from safety.setting import TherapySetting
from safety.validator import SafetyStatus, SafetyValidator

VALID = {"zone": "lower_abdomen", "temperature_c": 40, "duration_min": 20, "therapy_mode": "continuous"}


@pytest.fixture
def validator() -> SafetyValidator:
    return SafetyValidator(SafetyLimits())


def test_valid_setting_is_approved(validator):
    result = validator.validate(TherapySetting("lower_abdomen", 40.0, 20.0, "continuous"))
    assert result.status is SafetyStatus.APPROVED
    assert result.violations == ()


@pytest.mark.parametrize(
    "change, expected",
    [
        ({"temperature_c": 43}, "temperature"),
        ({"temperature_c": 30}, "temperature"),
        ({"duration_min": 45}, "duration"),
        ({"duration_min": 0}, "duration"),
        ({"zone": "neck"}, "zone"),
        ({"therapy_mode": "turbo"}, "therapy_mode"),
        ({"temperature_c": None}, "temperature_c is missing"),
        ({"temperature_c": math.nan}, "temperature_c is missing"),
        ({"temperature_c": "40"}, "temperature_c is missing"),
        ({"duration_min": True}, "duration_min is missing"),
        ({"zone": None}, "zone is missing"),
        ({"temperature_c": 41, "duration_min": 25}, "maximum duration"),
    ],
)
def test_unsafe_or_invalid_settings_are_rejected(validator, change, expected):
    result = validator.validate({**VALID, **change})
    assert result.status is SafetyStatus.REJECTED
    assert any(expected in v for v in result.violations)


def test_missing_key_is_rejected(validator):
    data = dict(VALID)
    del data["duration_min"]
    assert not validator.validate(data).approved


def test_limits_reject_values_beyond_absolute_ceiling():
    with pytest.raises(SafetyConfigError):
        SafetyLimits(max_temperature_c=400)
    with pytest.raises(SafetyConfigError):
        SafetyLimits(min_temperature_c=42, max_temperature_c=40)
    with pytest.raises(SafetyConfigError):
        SafetyLimits(max_duration_min=90)


def test_limits_load_from_json_file_and_env(tmp_path):
    path = tmp_path / "safety.json"
    path.write_text(json.dumps({"max_temperature_c": 41, "allowed_modes": ["continuous"]}))
    limits = load_safety_limits(
        {"OVA_SAFETY_CONFIG": str(path), "OVA_SAFETY_MAX_DURATION_MIN": "25"}
    )
    assert limits.max_temperature_c == 41
    assert limits.allowed_modes == ("continuous",)
    assert limits.max_duration_min == 25


def test_limits_reject_unknown_keys_in_file(tmp_path):
    path = tmp_path / "safety.json"
    path.write_text(json.dumps({"max_temp": 41}))
    with pytest.raises(SafetyConfigError):
        load_safety_limits({"OVA_SAFETY_CONFIG": str(path)})


def test_device_command_requires_confirmation(validator):
    with pytest.raises(DeviceCommandRefused, match="not confirmed"):
        prepare_device_command(VALID, user_confirmed=False, validator=validator)


def test_device_command_revalidates_edited_setting(validator):
    with pytest.raises(DeviceCommandRefused, match="temperature"):
        prepare_device_command({**VALID, "temperature_c": 44}, user_confirmed=True, validator=validator)


def test_device_command_for_confirmed_safe_setting(validator):
    command = prepare_device_command(VALID, user_confirmed=True, validator=validator)
    assert command.to_dict() == {
        "zone": "lower_abdomen",
        "target_temperature_c": 40.0,
        "duration_s": 1200,
        "therapy_mode": "continuous",
    }

import numpy as np
import pandas as pd
import pytest

from ml import schema
from ml.preprocessing.features import TherapyContext
from ml.recommendation.candidates import generate_candidates
from ml.recommendation.personalization import PersonalizationLevel
from ml.recommendation.service import NoSafeRecommendationError, RecommendationService
from safety.limits import SafetyLimits
from safety.validator import SafetyStatus, SafetyValidator, ValidationResult

CONTEXT = TherapyContext(pain_before=7, pain_zone=None, cycle_day=2, cycle_phase="menstrual")


def history(rows: list[tuple[str, float, float, int, int]]) -> pd.DataFrame:
    """rows of (zone, temperature, duration, pain_before, pain_after), one per day."""
    return pd.DataFrame([
        {
            schema.USER_ID: "u1",
            schema.STARTED_AT: pd.Timestamp("2026-03-01", tz="UTC") + pd.Timedelta(days=i),
            schema.ZONE: zone, schema.TEMPERATURE: temp, schema.DURATION: dur,
            schema.MODE: "continuous", schema.PAIN_ZONE: None,
            schema.PAIN_BEFORE: before, schema.PAIN_AFTER: after, schema.CYCLE_DAY: 2,
        }
        for i, (zone, temp, dur, before, after) in enumerate(rows)
    ])


@pytest.fixture(scope="module")
def service(bundle, limits) -> RecommendationService:
    return RecommendationService(bundle, limits, personalization_min_sessions=5)


def test_every_candidate_is_within_safety_limits(limits):
    validator = SafetyValidator(limits)
    candidates = generate_candidates(limits, validator)
    assert candidates
    temps = {c.temperature_c for c in candidates}
    assert min(temps) >= limits.min_temperature_c and max(temps) <= limits.max_temperature_c
    assert all(c.duration_min <= limits.max_duration_min for c in candidates)
    # the thermal-dose rule removes long sessions at high temperatures
    assert not any(c.temperature_c >= 41 and c.duration_min > 20 for c in candidates)


def test_cold_start_recommendation_is_safe_and_not_called_personalized(service, limits):
    rec = service.recommend(pd.DataFrame(), CONTEXT)
    assert rec.safety.status is SafetyStatus.APPROVED
    assert SafetyValidator(limits).validate(rec.setting).approved
    assert rec.personalization.level is PersonalizationLevel.NONE
    assert "not personalized" in rec.personalization.note
    assert 0 <= rec.predicted_pain_reduction <= CONTEXT.pain_before


def test_few_sessions_give_limited_personalization(service):
    rec = service.recommend(history([("lower_back", 40, 20, 7, 3)] * 2), CONTEXT)
    assert rec.personalization.level is PersonalizationLevel.LIMITED
    assert rec.personalization.sessions_used == 2


def test_history_steers_the_recommendation(service):
    # This user got strong relief on the lower back and little on the lower abdomen.
    rows = [("lower_back", 40, 20, 8, 1)] * 8 + [("lower_abdomen", 40, 20, 8, 7)] * 8
    rec = service.recommend(history(rows), CONTEXT)
    assert rec.personalization.level is PersonalizationLevel.PERSONALIZED
    assert rec.setting.zone == "lower_back"
    names = {f.name for f in rec.explanation.factors}
    assert names & {"history_zone", "history_temperature", "history_duration", "history_overall"}


def test_model_cannot_produce_values_outside_the_grid(service, limits):
    rec = service.recommend(pd.DataFrame(), CONTEXT)
    assert rec.setting in service.candidates
    assert rec.candidates_evaluated == len(service.candidates)


class RejectFirst(SafetyValidator):
    """Approves the grid, then rejects the first setting the service tries to return."""

    def __init__(self, limits):
        super().__init__(limits)
        self.calls_after_init = 0
        self.ready = False

    def validate(self, setting):
        if self.ready:
            self.calls_after_init += 1
            if self.calls_after_init == 1:
                return ValidationResult(SafetyStatus.REJECTED, ("forced",))
        return super().validate(setting)


def test_rejected_best_candidate_falls_back_to_next(bundle, limits):
    validator = RejectFirst(limits)
    svc = RecommendationService(bundle, limits, validator=validator)
    best = RecommendationService(bundle, limits).recommend(pd.DataFrame(), CONTEXT).setting
    validator.ready = True
    rec = svc.recommend(pd.DataFrame(), CONTEXT)
    assert rec.setting != best
    assert rec.safety.approved


class RejectAll(SafetyValidator):
    ready = False

    def validate(self, setting):
        if self.ready:
            return ValidationResult(SafetyStatus.REJECTED, ("forced",))
        return super().validate(setting)


def test_no_recommendation_when_everything_is_rejected(bundle, limits):
    validator = RejectAll(limits)
    svc = RecommendationService(bundle, limits, validator=validator)
    validator.ready = True
    with pytest.raises(NoSafeRecommendationError):
        svc.recommend(pd.DataFrame(), CONTEXT)


def test_tighter_limits_shrink_the_choices(bundle):
    narrow = SafetyLimits(min_temperature_c=38, max_temperature_c=39, allowed_modes=("continuous",))
    rec = RecommendationService(bundle, narrow).recommend(pd.DataFrame(), CONTEXT)
    assert 38 <= rec.setting.temperature_c <= 39
    assert rec.setting.therapy_mode == "continuous"


def test_pain_location_wins_over_history_and_history_is_offered(service):
    # Lower back worked much better for this user, but today the pain is in the lower abdomen.
    rows = [("lower_back", 40, 20, 8, 1)] * 8 + [("lower_abdomen", 40, 20, 8, 7)] * 8
    context = TherapyContext(pain_before=7, pain_zone="lower_abdomen", cycle_day=2, cycle_phase="menstrual")
    rec = service.recommend(history(rows), context)
    assert rec.setting.zone == "lower_abdomen"
    assert rec.alternative is not None and rec.alternative.setting.zone == "lower_back"
    assert "8 previous sessions on the lower back averaged 7.0" in rec.alternative.reason
    assert "compared with 1.0 over 8 on the lower abdomen" in rec.alternative.reason


def test_no_alternative_without_history_support(service):
    context = TherapyContext(pain_before=7, pain_zone="lower_abdomen", cycle_day=2, cycle_phase="menstrual")
    rec = service.recommend(pd.DataFrame(), context)
    assert rec.setting.zone == "lower_abdomen"
    assert rec.alternative is None


def test_unknown_pain_location_uses_all_zones(service):
    context = TherapyContext(pain_before=7, pain_zone="thighs", cycle_day=2, cycle_phase="menstrual")
    rec = service.recommend(pd.DataFrame(), context)
    assert rec.setting.zone in service.limits.allowed_zones

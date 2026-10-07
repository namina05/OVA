"""Recommendation service.

history -> features for every safe candidate -> XGBoost predicted pain
reduction -> pick the best -> SafetyValidator -> SHAP explanation.

The result is a recommendation for the user to confirm. It is never sent to
the device from here.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from ml.explainability.shap_explainer import Explanation, ShapExplainer
from ml.models.model_store import ModelBundle
from ml.preprocessing.features import TherapyContext, build_feature_row, to_frame
from ml.recommendation.candidates import generate_candidates
from ml.recommendation.personalization import (
    PersonalizationInfo,
    assess_personalization,
    build_user_history,
)
from safety.limits import SafetyLimits
from safety.setting import TherapySetting
from safety.validator import SafetyValidator, ValidationResult

logger = logging.getLogger(__name__)


# History must favour another zone by at least this much (pain points) to be offered as an alternative.
ALTERNATIVE_MIN_GAIN = 0.5
ALTERNATIVE_MIN_SESSIONS = 2


class NoSafeRecommendationError(RuntimeError):
    """No candidate passed the safety rules; nothing is recommended."""


@dataclass(frozen=True)
class Alternative:
    """A setting on another zone that the user's own history favours."""

    setting: TherapySetting
    predicted_pain_reduction: float
    reason: str


@dataclass(frozen=True)
class Recommendation:
    setting: TherapySetting
    predicted_pain_reduction: float
    explanation: Explanation
    personalization: PersonalizationInfo
    safety: ValidationResult
    model_version: str
    candidates_evaluated: int
    alternative: Alternative | None = None


class RecommendationService:
    def __init__(
        self,
        bundle: ModelBundle,
        limits: SafetyLimits,
        *,
        personalization_min_sessions: int = 5,
        tie_tolerance: float = 0.1,
        validator: SafetyValidator | None = None,
        explainer: ShapExplainer | None = None,
    ) -> None:
        self.bundle = bundle
        self.limits = limits
        self.validator = validator or SafetyValidator(limits)
        self.explainer = explainer or ShapExplainer(bundle)
        self.personalization_min_sessions = personalization_min_sessions
        self.tie_tolerance = tie_tolerance

        # Only recommend zones and modes that are both allowed now and known to the model.
        zones = [z for z in limits.allowed_zones if z in bundle.spec.zones]
        modes = [m for m in limits.allowed_modes if m in bundle.spec.modes]
        unseen = (set(limits.allowed_zones) - set(zones)) | (set(limits.allowed_modes) - set(modes))
        if unseen:
            logger.warning("not recommending %s: the model was not trained on them", sorted(unseen))
        self.candidates = generate_candidates(limits, self.validator, zones=zones, modes=modes)
        if not self.candidates:
            raise NoSafeRecommendationError("the safety limits and the model leave no candidate settings")

    def _ranking(self, predictions: np.ndarray, indices: list[int]) -> list[int]:
        """Best first among `indices`. Among near-equal predictions, prefer the gentler setting."""
        best = max(predictions[i] for i in indices)
        near = [i for i in indices if predictions[i] >= best - self.tie_tolerance]
        near.sort(key=lambda i: (self.candidates[i].temperature_c, self.candidates[i].duration_min, -predictions[i]))
        rest = sorted(set(indices) - set(near), key=lambda i: -predictions[i])
        return near + rest

    def _alternative(
        self, predictions: np.ndarray, chosen: int, other_zones: list[int], history
    ) -> Alternative | None:
        """Offer another zone when the user's own rated sessions show clearly more relief there."""
        if not other_zones:
            return None
        chosen_setting = self.candidates[chosen]
        here = history.for_zone(chosen_setting.zone)
        best_zone, best_stat = None, None
        for zone in {self.candidates[i].zone for i in other_zones}:
            stat = history.for_zone(zone)
            if stat.n >= ALTERNATIVE_MIN_SESSIONS and (best_stat is None or stat.mean_reduction > best_stat.mean_reduction):
                best_zone, best_stat = zone, stat
        if best_zone is None:
            return None
        if here.mean_reduction is not None and best_stat.mean_reduction - here.mean_reduction < ALTERNATIVE_MIN_GAIN:
            return None
        for index in self._ranking(predictions, [i for i in other_zones if self.candidates[i].zone == best_zone]):
            setting = self.candidates[index]
            if not self.validator.validate(setting).approved:
                continue
            zone, chosen_zone = best_zone.replace("_", " "), chosen_setting.zone.replace("_", " ")
            compare = (
                f", compared with {here.mean_reduction:.1f} over {here.n} on the {chosen_zone}"
                if here.n else f"; you have no rated sessions on the {chosen_zone} yet"
            )
            reason = (
                f"Your {best_stat.n} previous sessions on the {zone} averaged {best_stat.mean_reduction:.1f} points "
                f"of pain relief{compare}. You can choose the {zone} instead: "
                f"{setting.temperature_c:g}°C for {setting.duration_min:g} minutes."
            )
            return Alternative(setting, round(float(predictions[index]), 2), reason)
        return None

    def recommend(self, user_sessions: pd.DataFrame, context: TherapyContext) -> Recommendation:
        history = build_user_history(user_sessions)
        personalization = assess_personalization(history, self.personalization_min_sessions)

        features = to_frame(
            self.bundle.spec,
            [build_feature_row(self.bundle.spec, context, c, history) for c in self.candidates],
        )
        # A reduction can't exceed the current pain, nor make pain worse than 10.
        predictions = np.clip(
            self.bundle.model.predict(features), context.pain_before - 10, context.pain_before
        )

        # Pain location wins: heat where the user says it hurts, if the belt can heat that zone.
        everywhere = list(range(len(self.candidates)))
        at_pain = [i for i in everywhere if self.candidates[i].zone == context.pain_zone]
        allowed = at_pain or everywhere
        others = [i for i in everywhere if i not in set(at_pain)] if at_pain else []

        for index in self._ranking(predictions, allowed):
            candidate = self.candidates[index]
            safety = self.validator.validate(candidate)
            if not safety.approved:
                logger.error("candidate %s failed safety validation: %s", candidate, safety.violations)
                continue
            predicted = float(predictions[index])
            explanation = self.explainer.explain(
                features.iloc[[index]], candidate, context, history, predicted
            )
            return Recommendation(
                setting=candidate,
                predicted_pain_reduction=round(predicted, 2),
                explanation=explanation,
                personalization=personalization,
                safety=safety,
                model_version=self.bundle.version,
                candidates_evaluated=len(self.candidates),
                alternative=self._alternative(predictions, index, others, history),
            )
        raise NoSafeRecommendationError("no candidate setting passed the safety rules")

"""SHAP explanations for a recommended setting.

Contributions come from shap.TreeExplainer on the trained XGBoost model. They
add up to the prediction: base value + sum(contributions) = predicted pain
reduction. One-hot columns (zone__*, mode__*, phase__*) and related history
columns are summed into one human-level factor each.

The text is assembled only from these contributions and the user's actual
history numbers. Nothing in it is invented; factors too small to matter are
left out.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import shap

from ml.preprocessing.features import ONE_HOT_SEPARATOR, FeatureSpec, TherapyContext
from ml.preprocessing.history import HistoryStat, UserHistory
from ml.models.model_store import ModelBundle
from safety.setting import TherapySetting

MIN_CONTRIBUTION = 0.05  # pain points; smaller contributions are not mentioned
MAX_FACTORS_IN_TEXT = 3

_GROUP_OF_FEATURE = {
    "pain_before": "pain_before",
    "cycle_day": "cycle",
    "temperature_c": "temperature",
    "duration_min": "duration",
    "zone_matches_pain": "zone_matches_pain",
    "hist_n_sessions": "history_overall",
    "hist_mean_reduction": "history_overall",
    "hist_recent_mean_reduction": "history_overall",
    "hist_zone_n": "history_zone",
    "hist_zone_mean_reduction": "history_zone",
    "hist_zone_relative_reduction": "history_zone",
    "hist_temperature_n": "history_temperature",
    "hist_temperature_mean_reduction": "history_temperature",
    "hist_temperature_relative_reduction": "history_temperature",
    "hist_duration_n": "history_duration",
    "hist_duration_mean_reduction": "history_duration",
    "hist_duration_relative_reduction": "history_duration",
}
_GROUP_OF_PREFIX = {"zone": "zone", "mode": "mode", "phase": "cycle"}


def feature_group(feature: str) -> str:
    if ONE_HOT_SEPARATOR in feature:
        return _GROUP_OF_PREFIX[feature.split(ONE_HOT_SEPARATOR, 1)[0]]
    return _GROUP_OF_FEATURE[feature]


def zone_label(zone: str) -> str:
    return zone.replace("_", " ")


@dataclass(frozen=True)
class Factor:
    name: str
    contribution: float
    description: str


@dataclass(frozen=True)
class Explanation:
    base_value: float
    factors: tuple[Factor, ...]
    text: str


def _history_phrase(stat: HistoryStat, what: str) -> str:
    if stat.n == 0:
        return f"no previous sessions {what}"
    plural = "s" if stat.n != 1 else ""
    return f"your {stat.n} previous session{plural} {what} (average reduction {stat.mean_reduction:.1f})"


def _describe(
    group: str,
    setting: TherapySetting,
    context: TherapyContext,
    history: UserHistory,
    spec: FeatureSpec,
) -> str:
    params = spec.history
    zone = zone_label(setting.zone)
    match group:
        case "no_history":
            return "having no therapy history yet"
        case "temperature":
            return f"the temperature of {setting.temperature_c:g}°C"
        case "duration":
            return f"the duration of {setting.duration_min:g} minutes"
        case "zone":
            return f"heating the {zone}"
        case "mode":
            return f"{setting.therapy_mode} mode"
        case "zone_matches_pain":
            if context.pain_zone is None:
                return "no pain location given"
            if context.pain_zone == setting.zone:
                return "heating where you reported pain"
            return f"heating away from where you reported pain ({zone_label(context.pain_zone)})"
        case "pain_before":
            return f"your current pain level ({context.pain_before:g}/10)"
        case "cycle":
            if context.cycle_phase == "unknown":
                return "no cycle information"
            return f"your cycle phase ({context.cycle_phase})"
        case "history_overall":
            return _history_phrase(history.overall(), "overall")
        case "history_zone":
            return _history_phrase(history.for_zone(setting.zone), f"on the {zone}")
        case "history_temperature":
            return _history_phrase(
                history.for_temperature(setting.temperature_c, params), f"at about {setting.temperature_c:g}°C"
            )
        case "history_duration":
            return _history_phrase(
                history.for_duration(setting.duration_min, params), f"of about {setting.duration_min:g} minutes"
            )
    raise ValueError(f"unknown feature group {group}")


HISTORY_GROUPS = ("history_overall", "history_zone", "history_temperature", "history_duration")


def _matched_history(group: str, setting: TherapySetting, history: UserHistory, spec: FeatureSpec) -> HistoryStat:
    match group:
        case "history_zone":
            return history.for_zone(setting.zone)
        case "history_temperature":
            return history.for_temperature(setting.temperature_c, spec.history)
        case "history_duration":
            return history.for_duration(setting.duration_min, spec.history)
    return history.overall()


def _join(parts: list[str]) -> str:
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


class ShapExplainer:
    def __init__(self, bundle: ModelBundle) -> None:
        self.spec = bundle.spec
        self._explainer = shap.TreeExplainer(bundle.model)
        self.base_value = float(np.ravel(self._explainer.expected_value)[0])

    def contributions(self, features: pd.DataFrame) -> dict[str, float]:
        """SHAP value per feature group for a single-row feature frame."""
        values = np.asarray(self._explainer.shap_values(features))[0]
        grouped: dict[str, float] = {}
        for feature, value in zip(features.columns, values):
            group = feature_group(feature)
            grouped[group] = grouped.get(group, 0.0) + float(value)
        return grouped

    def explain(
        self,
        features: pd.DataFrame,
        setting: TherapySetting,
        context: TherapyContext,
        history: UserHistory,
        predicted_reduction: float,
    ) -> Explanation:
        grouped = self.contributions(features)
        if history.n_sessions == 0:
            # Without history the separate history factors all mean the same thing.
            grouped["no_history"] = sum(grouped.pop(g, 0.0) for g in HISTORY_GROUPS)
        factors = tuple(
            Factor(name, round(value, 3), _describe(name, setting, context, history, self.spec))
            for name, value in sorted(grouped.items(), key=lambda kv: abs(kv[1]), reverse=True)
            if abs(value) >= MIN_CONTRIBUTION
        )
        return Explanation(self.base_value, factors, self._text(factors, setting, history, predicted_reduction))

    def _text(
        self,
        factors: tuple[Factor, ...],
        setting: TherapySetting,
        history: UserHistory,
        predicted_reduction: float,
    ) -> str:
        sentences = [
            f"Recommended: {zone_label(setting.zone).capitalize()}, {setting.temperature_c:g}°C for "
            f"{setting.duration_min:g} minutes ({setting.therapy_mode} mode).",
            f"Expected pain reduction is about {predicted_reduction:.1f} points on the 0-10 scale "
            f"(the average across all sessions is {self.base_value:.1f}).",
        ]
        raised = [f for f in factors if f.contribution > 0][:MAX_FACTORS_IN_TEXT]
        lowered = [f for f in factors if f.contribution < 0][:2]
        if raised:
            sentences.append(
                "What raised this estimate most: "
                + _join([f"{f.description} (+{f.contribution:.1f})" for f in raised]) + "."
            )
        if lowered:
            sentences.append(
                "What lowered it: " + _join([f"{f.description} ({f.contribution:.1f})" for f in lowered]) + "."
            )

        # Only claim "better relief" when the matching sessions really did beat the
        # user's own average AND that history pushed this prediction up.
        overall = history.overall()
        better = [
            f for f in raised
            if f.name in HISTORY_GROUPS[1:]
            and overall.mean_reduction is not None
            and (stat := _matched_history(f.name, setting, history, self.spec)).n > 0
            and stat.mean_reduction > overall.mean_reduction
        ]
        if better:
            sentences.append(
                "Similar settings in your previous sessions were associated with better reported pain relief "
                f"than your average of {overall.mean_reduction:.1f} points."
            )
        return " ".join(sentences)

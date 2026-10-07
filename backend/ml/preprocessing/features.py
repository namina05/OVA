"""Feature engineering shared by training and inference.

One function, build_feature_row, turns (current context, candidate setting,
user's prior history) into model features. Training and recommendation both go
through it, so the model always sees features computed the same way.

user_id is never a feature: it is only used to group a user's sessions.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from ml import schema
from ml.preprocessing.history import HistoryParams, HistoryStat, UserHistory
from safety.setting import TherapySetting

ONE_HOT_SEPARATOR = "__"

NUMERIC_FEATURES: tuple[str, ...] = (
    "pain_before",
    "cycle_day",
    "temperature_c",
    "duration_min",
    "zone_matches_pain",
)
HISTORY_FEATURES: tuple[str, ...] = (
    "hist_n_sessions",
    "hist_mean_reduction",
    "hist_recent_mean_reduction",
    "hist_zone_n",
    "hist_zone_mean_reduction",
    "hist_zone_relative_reduction",
    "hist_temperature_n",
    "hist_temperature_mean_reduction",
    "hist_temperature_relative_reduction",
    "hist_duration_n",
    "hist_duration_mean_reduction",
    "hist_duration_relative_reduction",
)


@dataclass(frozen=True)
class TherapyContext:
    """The user's situation when asking for a recommendation."""

    pain_before: float
    pain_zone: str | None = None
    cycle_day: float | None = None
    cycle_phase: str = "unknown"


@dataclass(frozen=True)
class FeatureSpec:
    """Vocabulary and parameters fixed at training time and saved with the model."""

    zones: tuple[str, ...]
    modes: tuple[str, ...]
    cycle_phases: tuple[str, ...] = schema.CYCLE_PHASES
    history: HistoryParams = field(default_factory=HistoryParams)

    @property
    def feature_columns(self) -> list[str]:
        return [
            *NUMERIC_FEATURES,
            *(f"zone{ONE_HOT_SEPARATOR}{z}" for z in self.zones),
            *(f"mode{ONE_HOT_SEPARATOR}{m}" for m in self.modes),
            *(f"phase{ONE_HOT_SEPARATOR}{p}" for p in self.cycle_phases),
            *HISTORY_FEATURES,
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "zones": list(self.zones),
            "modes": list(self.modes),
            "cycle_phases": list(self.cycle_phases),
            "history": asdict(self.history),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FeatureSpec":
        return cls(
            zones=tuple(data["zones"]),
            modes=tuple(data["modes"]),
            cycle_phases=tuple(data["cycle_phases"]),
            history=HistoryParams(**data["history"]),
        )


def _mean_or_nan(stat: HistoryStat) -> float:
    return math.nan if stat.mean_reduction is None else stat.mean_reduction


def _relative_or_nan(stat: HistoryStat, overall: HistoryStat) -> float:
    """How much better (or worse) matching sessions did than the user's own average."""
    if stat.mean_reduction is None or overall.mean_reduction is None:
        return math.nan
    return stat.mean_reduction - overall.mean_reduction


def build_feature_row(
    spec: FeatureSpec,
    context: TherapyContext,
    setting: TherapySetting,
    history: UserHistory,
) -> dict[str, float]:
    """Features for one candidate. Unknown history is NaN (XGBoost treats it as missing)."""
    row: dict[str, float] = {
        "pain_before": float(context.pain_before),
        "cycle_day": math.nan if context.cycle_day is None else float(context.cycle_day),
        "temperature_c": float(setting.temperature_c),
        "duration_min": float(setting.duration_min),
        "zone_matches_pain": float(context.pain_zone is not None and context.pain_zone == setting.zone),
    }
    for z in spec.zones:
        row[f"zone{ONE_HOT_SEPARATOR}{z}"] = float(setting.zone == z)
    for m in spec.modes:
        row[f"mode{ONE_HOT_SEPARATOR}{m}"] = float(setting.therapy_mode == m)
    for p in spec.cycle_phases:
        row[f"phase{ONE_HOT_SEPARATOR}{p}"] = float(context.cycle_phase == p)

    params = spec.history
    overall = history.overall()
    zone_stat = history.for_zone(setting.zone)
    temp_stat = history.for_temperature(setting.temperature_c, params)
    duration_stat = history.for_duration(setting.duration_min, params)
    row.update(
        hist_n_sessions=float(history.n_sessions),
        hist_mean_reduction=_mean_or_nan(overall),
        hist_recent_mean_reduction=_mean_or_nan(history.recent(params)),
        hist_zone_n=float(zone_stat.n),
        hist_zone_mean_reduction=_mean_or_nan(zone_stat),
        hist_zone_relative_reduction=_relative_or_nan(zone_stat, overall),
        hist_temperature_n=float(temp_stat.n),
        hist_temperature_mean_reduction=_mean_or_nan(temp_stat),
        hist_temperature_relative_reduction=_relative_or_nan(temp_stat, overall),
        hist_duration_n=float(duration_stat.n),
        hist_duration_mean_reduction=_mean_or_nan(duration_stat),
        hist_duration_relative_reduction=_relative_or_nan(duration_stat, overall),
    )
    return row


def to_frame(spec: FeatureSpec, rows: list[dict[str, float]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=spec.feature_columns, dtype=float)


def context_from_session(session: pd.Series) -> TherapyContext:
    pain_zone = session.get(schema.PAIN_ZONE)
    cycle_day = session.get(schema.CYCLE_DAY)
    return TherapyContext(
        pain_before=float(session[schema.PAIN_BEFORE]),
        pain_zone=pain_zone if isinstance(pain_zone, str) else None,
        cycle_day=None if cycle_day is None or pd.isna(cycle_day) else float(cycle_day),
        cycle_phase=session.get(schema.CYCLE_PHASE, "unknown"),
    )


def setting_from_session(session: pd.Series) -> TherapySetting:
    return TherapySetting(
        zone=str(session[schema.ZONE]),
        temperature_c=float(session[schema.TEMPERATURE]),
        duration_min=float(session[schema.DURATION]),
        therapy_mode=str(session[schema.MODE]),
    )


def build_training_frame(spec: FeatureSpec, sessions: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray, np.ndarray]:
    """Features, targets and user groups from cleaned sessions.

    Each session's history features use only that user's EARLIER sessions, so
    no session ever sees its own outcome or a later one.
    """
    rows: list[dict[str, float]] = []
    targets: list[float] = []
    groups: list[str] = []
    for user_id, user_sessions in sessions.groupby(schema.USER_ID, sort=False):
        ordered = user_sessions.sort_values(schema.STARTED_AT, kind="stable")
        full_history = UserHistory.from_sessions(ordered)
        for i, (_, session) in enumerate(ordered.iterrows()):
            rows.append(
                build_feature_row(
                    spec,
                    context_from_session(session),
                    setting_from_session(session),
                    full_history.prefix(i),
                )
            )
            targets.append(float(session[schema.PAIN_REDUCTION]))
            groups.append(str(user_id))
    return to_frame(spec, rows), np.asarray(targets, dtype=float), np.asarray(groups)

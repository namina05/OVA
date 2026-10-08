"""Application settings from environment variables.

Safety limits are configured separately (see safety/limits.py) so they can be
reviewed on their own.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from knowledge_graph.graph import DEFAULT_GRAPH_PATH
from safety.limits import DEFAULT_ZONES

KNOWLEDGE_GRAPH_SOURCES = ("auto", "file", "postgres")
CARE_LEVELS = ("emergency", "urgent", "see_doctor")


class ConfigError(ValueError):
    pass


def _int(env: Mapping[str, str], name: str, default: int, minimum: int = 0) -> int:
    raw = env.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from exc
    if value < minimum:
        raise ConfigError(f"{name} must be >= {minimum}")
    return value


def _float(env: Mapping[str, str], name: str, default: float) -> float:
    raw = env.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number, got {raw!r}") from exc


def _choice(env: Mapping[str, str], name: str, default: str, allowed: tuple[str, ...]) -> str:
    value = env.get(name, default)
    if value not in allowed:
        raise ConfigError(f"{name} must be one of {allowed}, got {value!r}")
    return value


def _levels(env: Mapping[str, str], name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = env.get(name)
    if raw is None:
        return default
    levels = tuple(p.strip() for p in raw.split(",") if p.strip())
    unknown = set(levels) - set(CARE_LEVELS)
    if unknown:
        raise ConfigError(f"{name} has unknown care levels {sorted(unknown)}; allowed: {CARE_LEVELS}")
    return levels


@dataclass(frozen=True)
class AppSettings:
    model_dir: Path = Path("models/current")
    database_url: str | None = None
    therapy_sessions_table: str = "public.therapy_sessions"
    history_max_sessions: int = 200
    personalization_min_sessions: int = 5
    tie_tolerance: float = 0.1
    # Zone names in the order of the zone numbers stored in session_zones (1, 2, ...).
    zone_names: tuple[str, ...] = DEFAULT_ZONES
    cycle_model_dir: Path = Path("models/cycle")
    # Fewer complete cycles than this: next-start prediction uses the recent average, not the model.
    min_cycles_for_model: int = 2
    symptom_lookback_days: int = 90
    # Pain at or above this in the forecast is flagged as a day to plan heat therapy for.
    high_pain_threshold: float = 6.0
    # auto: Postgres when DATABASE_URL is set (falling back to the bundled file), else the file.
    knowledge_graph_source: str = "auto"
    knowledge_graph_path: Path = DEFAULT_GRAPH_PATH
    # A health alert at one of these care levels withholds the heat recommendation.
    withhold_care_levels: tuple[str, ...] = ("emergency",)

    # The Supabase project whose signed-in users may call the API. Unset = no sign-in check.
    supabase_url: str | None = None

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "AppSettings":
        env = os.environ if environ is None else environ
        zone_names = env.get("OVA_ZONE_NAMES")
        return cls(
            model_dir=Path(env.get("OVA_MODEL_DIR", str(cls.model_dir))),
            database_url=env.get("DATABASE_URL") or None,
            supabase_url=env.get("SUPABASE_URL") or None,
            therapy_sessions_table=env.get("OVA_THERAPY_SESSIONS_TABLE", cls.therapy_sessions_table),
            history_max_sessions=_int(env, "OVA_HISTORY_MAX_SESSIONS", cls.history_max_sessions, minimum=1),
            personalization_min_sessions=_int(
                env, "OVA_PERSONALIZATION_MIN_SESSIONS", cls.personalization_min_sessions, minimum=1
            ),
            tie_tolerance=_float(env, "OVA_TIE_TOLERANCE", cls.tie_tolerance),
            zone_names=tuple(z.strip() for z in zone_names.split(",")) if zone_names else DEFAULT_ZONES,
            cycle_model_dir=Path(env.get("OVA_CYCLE_MODEL_DIR", str(cls.cycle_model_dir))),
            min_cycles_for_model=_int(env, "OVA_MIN_CYCLES_FOR_MODEL", cls.min_cycles_for_model, minimum=1),
            symptom_lookback_days=_int(env, "OVA_SYMPTOM_LOOKBACK_DAYS", cls.symptom_lookback_days, minimum=1),
            high_pain_threshold=_float(env, "OVA_HIGH_PAIN_THRESHOLD", cls.high_pain_threshold),
            knowledge_graph_source=_choice(env, "OVA_KNOWLEDGE_GRAPH_SOURCE", cls.knowledge_graph_source,
                                           KNOWLEDGE_GRAPH_SOURCES),
            knowledge_graph_path=Path(env.get("OVA_KNOWLEDGE_GRAPH_PATH", str(cls.knowledge_graph_path))),
            withhold_care_levels=_levels(env, "OVA_WITHHOLD_CARE_LEVELS", cls.withhold_care_levels),
        )

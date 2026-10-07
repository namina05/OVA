"""Loads one user's rows from the existing tables for a request."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd
from fastapi import HTTPException, status

from api.services.dependencies import AppServices
from api.services.repository import RepositoryError
from knowledge_graph.personal import PersonalGraph
from ml.cycle import data as cd


@dataclass
class UserContext:
    sessions: pd.DataFrame
    periods: pd.DataFrame
    daily_logs: pd.DataFrame
    profile: cd.Profile


def load_user_context(
    services: AppServices,
    user_id: str,
    *,
    sessions: pd.DataFrame | None = None,
    logs_since: date | None = None,
) -> UserContext:
    """Rows the user owns; a store that isn't configured contributes nothing."""
    try:
        if sessions is None:
            sessions = services.repository.get_user_sessions(user_id) if services.repository else pd.DataFrame()
        cycle_repo = services.cycle_repository
        if cycle_repo is None:
            return UserContext(sessions, pd.DataFrame(), pd.DataFrame(), cd.Profile())
        return UserContext(
            sessions,
            cycle_repo.get_user_periods(user_id),
            cycle_repo.get_user_daily_logs(user_id, since=logs_since),
            cycle_repo.get_user_profile(user_id),
        )
    except RepositoryError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "user data is unavailable")


def personal_graph(services: AppServices, user_id: str, context: UserContext, today: date) -> PersonalGraph:
    return services.personal_graphs.build(user_id, context.sessions, context.periods, context.daily_logs, today)


def symptom_window_start(services: AppServices, today: date) -> date:
    return today - timedelta(days=services.settings.symptom_lookback_days)


def cycle_day_from_periods(periods: pd.DataFrame, today: date) -> int | None:
    """Day of the current cycle (1 = first day of the last logged period), if plausible."""
    if periods.empty:
        return None
    starts = [s for s in cd.clean_periods(periods)[cd.START] if s <= today]
    if not starts:
        return None
    day = (today - max(starts)).days + 1
    return day if day <= cd.MAX_CYCLE_DAYS else None

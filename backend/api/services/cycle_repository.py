"""Read access to periods, daily_logs and profiles, and writing predictions.

Reads the existing tables directly; no user data is copied.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any, Protocol

import pandas as pd

from api.services.repository import RepositoryError
from ml.cycle import data as cd
from ml.cycle.predictor import CycleForecast

PERIOD_COLUMNS = [cd.USER_ID, cd.START, cd.END]
LOG_COLUMNS = [cd.USER_ID, cd.LOG_DATE, cd.PAIN, cd.SYMPTOMS]
PROFILE_COLUMNS = [cd.USER_ID, cd.DATE_OF_BIRTH, cd.TYPICAL_CYCLE, cd.TYPICAL_PERIOD]


class CycleRepository(Protocol):
    def get_user_periods(self, user_id: str) -> pd.DataFrame: ...

    def get_user_daily_logs(self, user_id: str, since: date | None = None) -> pd.DataFrame: ...

    def get_user_profile(self, user_id: str) -> cd.Profile: ...

    def save_prediction(self, user_id: str, forecast: CycleForecast) -> None: ...


def prediction_row(user_id: str, forecast: CycleForecast) -> dict[str, Any]:
    return {
        "user_id": user_id,
        "predicted_start": forecast.predicted_start,
        "range_days": forecast.range_days,
        "method": forecast.method,
        "model_version": forecast.model_version or None,
        "predicted_period_length": forecast.predicted_period_length,
        "period_length_range_days": forecast.period_length_range_days,
        "pain_forecast": [d.to_dict() for d in forecast.pain_forecast],
    }


class DataFrameCycleRepository:
    """In-memory store for development and tests."""

    def __init__(self, periods: pd.DataFrame, daily_logs: pd.DataFrame, profiles: pd.DataFrame) -> None:
        self.periods, self.daily_logs, self.profiles = periods, daily_logs, profiles
        self.saved: list[dict[str, Any]] = []

    @staticmethod
    def _for(df: pd.DataFrame, user_id: str, columns: list[str]) -> pd.DataFrame:
        if df.empty:
            return pd.DataFrame(columns=columns)
        return df[df[cd.USER_ID].astype(str) == user_id].copy()

    def get_user_periods(self, user_id: str) -> pd.DataFrame:
        return self._for(self.periods, user_id, PERIOD_COLUMNS)

    def get_user_daily_logs(self, user_id: str, since: date | None = None) -> pd.DataFrame:
        logs = self._for(self.daily_logs, user_id, LOG_COLUMNS)
        if since is not None and not logs.empty:
            logs = logs[pd.to_datetime(logs[cd.LOG_DATE]).dt.date >= since]
        return logs

    def get_user_profile(self, user_id: str) -> cd.Profile:
        rows = self._for(self.profiles, user_id, PROFILE_COLUMNS)
        return cd.Profile.from_row(rows.iloc[0]) if not rows.empty else cd.Profile()

    def save_prediction(self, user_id: str, forecast: CycleForecast) -> None:
        self.saved.append(prediction_row(user_id, forecast))


class PostgresCycleRepository:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def _fetch(self, query: str, params: tuple, columns: list[str]) -> pd.DataFrame:
        import psycopg

        try:
            with psycopg.connect(self._dsn, connect_timeout=5) as conn, conn.cursor() as cur:
                cur.execute(query, params)
                return pd.DataFrame(cur.fetchall(), columns=columns)
        except psycopg.Error as exc:
            raise RepositoryError("could not read cycle data") from exc

    def get_user_periods(self, user_id: str) -> pd.DataFrame:
        return self._fetch(
            "select user_id::text, start_date, end_date from public.periods where user_id = %s order by start_date",
            (user_id,), PERIOD_COLUMNS,
        )

    def get_user_daily_logs(self, user_id: str, since: date | None = None) -> pd.DataFrame:
        return self._fetch(
            "select user_id::text, log_date, pain, symptoms from public.daily_logs "
            "where user_id = %s and (%s::date is null or log_date >= %s::date) order by log_date",
            (user_id, since, since), LOG_COLUMNS,
        )

    def get_user_profile(self, user_id: str) -> cd.Profile:
        rows = self._fetch(
            "select id::text, date_of_birth, typical_cycle_length, typical_period_length "
            "from public.profiles where id = %s",
            (user_id,), PROFILE_COLUMNS,
        )
        return cd.Profile.from_row(rows.iloc[0]) if not rows.empty else cd.Profile()

    def get_all_periods(self) -> pd.DataFrame:
        return self._fetch("select user_id::text, start_date, end_date from public.periods", (), PERIOD_COLUMNS)

    def get_all_daily_logs(self) -> pd.DataFrame:
        return self._fetch(
            "select user_id::text, log_date, pain, symptoms from public.daily_logs", (), LOG_COLUMNS
        )

    def get_all_profiles(self) -> pd.DataFrame:
        return self._fetch(
            "select id::text, date_of_birth, typical_cycle_length, typical_period_length from public.profiles",
            (), PROFILE_COLUMNS,
        )

    def save_prediction(self, user_id: str, forecast: CycleForecast) -> None:
        import psycopg

        row = prediction_row(user_id, forecast)
        try:
            with psycopg.connect(self._dsn, connect_timeout=5) as conn, conn.cursor() as cur:
                cur.execute(
                    "insert into public.predictions (user_id, predicted_start, range_days, method, model_version, "
                    "predicted_period_length, period_length_range_days, pain_forecast) "
                    "values (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)",
                    (row["user_id"], row["predicted_start"], row["range_days"], row["method"], row["model_version"],
                     row["predicted_period_length"], row["period_length_range_days"], json.dumps(row["pain_forecast"])),
                )
        except psycopg.Error as exc:
            raise RepositoryError("could not save the prediction") from exc

"""Read access to therapy sessions.

Reads the therapy_sessions view (supabase/migrations/..._therapy_sessions_view.sql),
which is built on the existing sessions and session_zones tables, so no user
data is copied. The recommender only reads; it never writes session data.
"""

from __future__ import annotations

import re
from typing import Protocol

import pandas as pd

from ml import schema

COLUMNS: tuple[str, ...] = (
    schema.SESSION_ID,
    schema.USER_ID,
    schema.STARTED_AT,
    schema.ZONE,
    schema.TEMPERATURE,
    schema.DURATION,
    schema.MODE,
    schema.PAIN_ZONE,
    schema.PAIN_BEFORE,
    schema.PAIN_AFTER,
    schema.CYCLE_DAY,
    schema.END_REASON,
)
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class RepositoryError(RuntimeError):
    """The session store could not be read."""


class TherapySessionRepository(Protocol):
    def get_user_sessions(self, user_id: str) -> pd.DataFrame: ...

    def get_all_sessions(self) -> pd.DataFrame: ...


class DataFrameTherapySessionRepository:
    """In-memory store, for CSV-based development and tests."""

    def __init__(self, sessions: pd.DataFrame) -> None:
        self._sessions = sessions

    def get_user_sessions(self, user_id: str) -> pd.DataFrame:
        return self._sessions[self._sessions[schema.USER_ID].astype(str) == user_id].copy()

    def get_all_sessions(self) -> pd.DataFrame:
        return self._sessions.copy()


def zone_number_to_name(value: object, zone_names: tuple[str, ...]) -> str | None:
    """session_zones stores zones as 1..n; the recommender uses names."""
    if value is None or pd.isna(value):
        return None
    index = int(value) - 1
    return zone_names[index] if 0 <= index < len(zone_names) else None


class PostgresTherapySessionRepository:
    def __init__(self, dsn: str, table: str, zone_names: tuple[str, ...], max_sessions: int) -> None:
        parts = table.split(".")
        if not 1 <= len(parts) <= 2 or not all(_IDENTIFIER.match(p) for p in parts):
            raise ValueError(f"invalid table name {table!r}")
        self._dsn = dsn
        self._table_parts = parts
        self._zone_names = zone_names
        self._max_sessions = max_sessions

    @classmethod
    def from_settings(cls, settings) -> "PostgresTherapySessionRepository":
        return cls(
            settings.database_url,
            settings.therapy_sessions_table,
            settings.zone_names,
            settings.history_max_sessions,
        )

    def _query(self, where_user: bool):
        from psycopg import sql

        query = sql.SQL("select {cols} from {table}").format(
            cols=sql.SQL(", ").join(
                sql.SQL("{}::text").format(sql.Identifier(c)) if c in (schema.SESSION_ID, schema.USER_ID)
                else sql.Identifier(c)
                for c in COLUMNS
            ),
            table=sql.Identifier(*self._table_parts),
        )
        if where_user:
            # Most recent sessions only; history is re-sorted oldest-first later.
            query += sql.SQL(" where user_id = %s order by started_at desc limit %s")
        return query

    def _fetch(self, query, params: tuple = ()) -> pd.DataFrame:
        import psycopg

        try:
            with psycopg.connect(self._dsn, connect_timeout=5) as conn, conn.cursor() as cur:
                cur.execute(query, params)
                rows = cur.fetchall()
        except psycopg.Error as exc:
            raise RepositoryError("could not read therapy sessions") from exc
        df = pd.DataFrame(rows, columns=list(COLUMNS))
        for col in (schema.ZONE, schema.PAIN_ZONE):
            df[col] = [zone_number_to_name(v, self._zone_names) for v in df[col]]
        for col in (schema.TEMPERATURE, schema.DURATION):
            df[col] = pd.to_numeric(df[col], errors="coerce")
        return df

    def get_user_sessions(self, user_id: str) -> pd.DataFrame:
        return self._fetch(self._query(where_user=True), (user_id, self._max_sessions))

    def get_all_sessions(self) -> pd.DataFrame:
        return self._fetch(self._query(where_user=False))

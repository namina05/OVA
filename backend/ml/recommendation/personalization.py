"""Personalization layer: the general model plus the user's own history.

The XGBoost model is trained once on everyone's sessions. A user's history is
turned into features (see ml.preprocessing.history) at request time, so each
new logged session changes the next recommendation without retraining.

This module also states honestly how personalized a recommendation is.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import pandas as pd

from ml.preprocessing.cleaning import clean_sessions
from ml.preprocessing.history import UserHistory


class PersonalizationLevel(StrEnum):
    NONE = "none"
    LIMITED = "limited"
    PERSONALIZED = "personalized"


@dataclass(frozen=True)
class PersonalizationInfo:
    level: PersonalizationLevel
    sessions_used: int
    note: str


def build_user_history(raw_sessions: pd.DataFrame) -> UserHistory:
    """History from a user's raw session rows; unusable rows are dropped."""
    if raw_sessions.empty:
        return UserHistory.empty()
    return UserHistory.from_sessions(clean_sessions(raw_sessions))


def assess_personalization(history: UserHistory, min_sessions: int) -> PersonalizationInfo:
    n = history.n_sessions
    if n == 0:
        return PersonalizationInfo(
            PersonalizationLevel.NONE,
            0,
            "You have no rated therapy sessions yet, so this recommendation comes from the general "
            "model only and is not personalized. It will adapt as you log sessions and rate your "
            "pain afterwards.",
        )
    if n < min_sessions:
        return PersonalizationInfo(
            PersonalizationLevel.LIMITED,
            n,
            f"Personalization is limited: this uses the general model and only {n} of your rated "
            f"session{'s' if n != 1 else ''}. It will become more personal after {min_sessions} sessions.",
        )
    return PersonalizationInfo(
        PersonalizationLevel.PERSONALIZED,
        n,
        f"Personalized using your {n} previous rated sessions.",
    )

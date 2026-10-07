"""The therapy setting the recommender proposes and the safety layer checks."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class TherapySetting:
    """One heating configuration: where, how hot, how long, and in which mode."""

    zone: str
    temperature_c: float
    duration_min: float
    therapy_mode: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

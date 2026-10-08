"""Request and response models for the API."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field

CyclePhase = Literal["menstrual", "follicular", "ovulatory", "luteal"]
PersonalizationLevelOut = Literal["none", "limited", "personalized"]

THERAPY_NOTICE = (
    "This is a suggestion, not a medical instruction. Confirm before starting; the belt's own "
    "temperature protection and automatic shut-off stay active."
)


class EvidenceOut(BaseModel):
    source: str
    title: str
    quote: str


class HealthAlertOut(BaseModel):
    trigger: str
    trigger_label: str
    care_level: Literal["emergency", "urgent", "see_doctor"]
    severity: int
    advice: str
    origin: Literal["reported_now", "logged_recently", "cycle_pattern"]
    evidence: list[EvidenceOut]


class RecommendRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    pain_level: int = Field(ge=0, le=10, description="current pain, 0-10")
    pain_location: str | None = Field(None, max_length=64, description="zone name, e.g. lower_abdomen")
    cycle_day: int | None = Field(None, ge=1, le=60, description="if omitted, derived from the logged periods")
    cycle_phase: CyclePhase | None = None
    symptoms: list[str] = Field(
        default_factory=list, max_length=20, description="symptom keys from GET /knowledge-graph/symptoms"
    )


class FactorOut(BaseModel):
    name: str
    contribution: float = Field(description="SHAP contribution to predicted pain reduction, in pain points")
    description: str


class PersonalizationOut(BaseModel):
    level: PersonalizationLevelOut
    sessions_used: int
    note: str


class AlternativeOut(BaseModel):
    zone: str
    temperature: float
    duration: float
    therapy_mode: str
    predicted_pain_reduction: float
    reason: str


class RecommendResponse(BaseModel):
    status: Literal["recommended", "withheld"]
    # The setting fields are null when the recommendation is withheld because of a health alert.
    zone: str | None = None
    temperature: float | None = Field(None, description="°C")
    duration: float | None = Field(None, description="minutes")
    therapy_mode: str | None = None
    predicted_pain_reduction: float | None = None
    explanation: str
    top_factors: list[FactorOut] = Field(default_factory=list)
    personalization: PersonalizationOut | None = None
    safety_status: Literal["approved"] | None = None
    alternative: AlternativeOut | None = Field(
        None, description="another zone the user's history favours; the recommended zone follows pain location"
    )
    requires_user_confirmation: bool = True
    health_alerts: list[HealthAlertOut] = Field(default_factory=list)
    evidence: list[EvidenceOut] = Field(default_factory=list, description="sources supporting heat on this zone")
    cycle_day_used: int | None = None
    cycle_day_source: Literal["reported", "period_log"] | None = None
    model_version: str | None = None
    notice: str = THERAPY_NOTICE


class DeviceCommandRequest(BaseModel):
    zone: str | None = None
    temperature: float | None = None
    duration: float | None = None
    therapy_mode: str | None = None
    user_confirmed: bool = False


class DeviceCommandResponse(BaseModel):
    zone: str
    target_temperature_c: float
    duration_s: int
    therapy_mode: str
    safety_status: Literal["approved"] = "approved"


# -- cycle ---------------------------------------------------------------------


class CyclePredictRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    save: bool = Field(False, description="also store the result in the predictions table")


class PainDayOut(BaseModel):
    date: date
    day: int = Field(description="relative to the predicted start; 0 = first day of the period")
    expected_pain: float
    low: float
    high: float


class CycleFactorOut(BaseModel):
    name: str
    contribution_days: float
    description: str


class CyclePredictResponse(BaseModel):
    method: Literal["onboarding_default", "recent_average", "model"]
    last_period_start: date
    predicted_start: date
    range_days: int
    predicted_cycle_length: float
    predicted_period_length: int
    period_length_range_days: int
    days_until_start: int
    is_late: bool
    ovulation_date: date | None = Field(None, description="estimated; 14 days before the predicted start")
    fertile_start: date | None = None
    fertile_end: date | None = None
    pain_forecast: list[PainDayOut]
    high_pain_dates: list[date] = Field(description="days worth planning heat therapy for")
    personalization_level: PersonalizationLevelOut
    complete_cycles: int
    explanation: str
    factors: list[CycleFactorOut]
    health_alerts: list[HealthAlertOut]
    model_version: str
    saved: bool
    notice: str = (
        "Predictions are estimates from your logged periods. They cannot be used for contraception "
        "or to rule out pregnancy."
    )


# -- knowledge graph ------------------------------------------------------------


class SymptomOut(BaseModel):
    key: str
    label: str
    red_flag: bool


class GraphOut(BaseModel):
    version: str
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]


class PersonalGraphOut(BaseModel):
    user_node: str
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    alerts: list[HealthAlertOut]
    insights: list[dict[str, Any]]

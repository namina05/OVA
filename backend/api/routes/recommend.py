"""Recommendation and device-command endpoints.

Route functions are plain `def` so FastAPI runs the blocking database and
model calls in its thread pool.
"""

from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request, status

from api.schemas import (
    AlternativeOut,
    DeviceCommandRequest,
    DeviceCommandResponse,
    EvidenceOut,
    FactorOut,
    HealthAlertOut,
    PersonalizationOut,
    RecommendRequest,
    RecommendResponse,
)
from api.services.dependencies import (
    AppServices,
    get_recommender,
    get_repository,
    get_services,
    get_today,
    get_validator,
    require_user,
)
from api.services.repository import RepositoryError, TherapySessionRepository
from api.services.user_context import (
    cycle_day_from_periods,
    load_user_context,
    personal_graph,
    symptom_window_start,
)
from knowledge_graph.advisor import HealthAlert, UnknownSymptomError, merge_alerts
from ml.preprocessing.cleaning import normalize_cycle_phase
from ml.preprocessing.features import TherapyContext
from ml.recommendation.service import NoSafeRecommendationError, RecommendationService
from safety.device_command import DeviceCommandRefused, prepare_device_command
from safety.validator import SafetyValidator

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_FACTORS = 5


def alerts_out(alerts: list[HealthAlert]) -> list[HealthAlertOut]:
    return [HealthAlertOut(**a.to_dict()) for a in alerts]


@router.post("/recommend", response_model=RecommendResponse)
def recommend(
    body: RecommendRequest,
    request: Request,
    services: AppServices = Depends(get_services),
    recommender: RecommendationService = Depends(get_recommender),
    repository: TherapySessionRepository = Depends(get_repository),
    today: date = Depends(get_today),
) -> RecommendResponse:
    require_user(request, body.user_id)
    try:
        reported = services.advisor.symptom_node_ids(body.symptoms)
    except UnknownSymptomError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, {"unknown_symptoms": exc.unknown})

    try:
        history = repository.get_user_sessions(body.user_id)
    except RepositoryError:
        logger.exception("failed to read therapy history")
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "therapy history is unavailable")
    context = load_user_context(
        services, body.user_id, sessions=history, logs_since=symptom_window_start(services, today)
    )

    alerts = merge_alerts(
        services.advisor.alerts_for(reported, origin="reported_now"),
        personal_graph(services, body.user_id, context, today).alerts,
    )

    cycle_day, cycle_day_source = body.cycle_day, "reported" if body.cycle_day else None
    if cycle_day is None and (cycle_day := cycle_day_from_periods(context.periods, today)) is not None:
        cycle_day_source = "period_log"

    withholding = [a for a in alerts if a.care_level in services.settings.withhold_care_levels]
    if withholding:
        return RecommendResponse(
            status="withheld",
            explanation=f"Heat therapy is not suggested right now. {withholding[0].advice}",
            health_alerts=alerts_out(alerts),
            cycle_day_used=cycle_day,
            cycle_day_source=cycle_day_source,
        )

    therapy_context = TherapyContext(
        pain_before=body.pain_level,
        pain_zone=body.pain_location,
        cycle_day=cycle_day,
        cycle_phase=normalize_cycle_phase(body.cycle_phase, cycle_day),
    )
    try:
        rec = recommender.recommend(history, therapy_context)
    except NoSafeRecommendationError:
        logger.exception("no safe recommendation")
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "no safe recommendation is available")

    explanation = f"{rec.explanation.text} {rec.personalization.note}"
    alternative = None
    if rec.alternative is not None:
        explanation += f" {rec.alternative.reason}"
        alt = rec.alternative.setting
        alternative = AlternativeOut(
            zone=alt.zone, temperature=alt.temperature_c, duration=alt.duration_min, therapy_mode=alt.therapy_mode,
            predicted_pain_reduction=rec.alternative.predicted_pain_reduction, reason=rec.alternative.reason,
        )
    if alerts:
        explanation = f"Please read the health alert{'s' if len(alerts) > 1 else ''} first. {explanation}"
    return RecommendResponse(
        status="recommended",
        zone=rec.setting.zone,
        temperature=rec.setting.temperature_c,
        duration=rec.setting.duration_min,
        therapy_mode=rec.setting.therapy_mode,
        predicted_pain_reduction=rec.predicted_pain_reduction,
        explanation=explanation,
        top_factors=[
            FactorOut(name=f.name, contribution=f.contribution, description=f.description)
            for f in rec.explanation.factors[:MAX_FACTORS]
        ],
        personalization=PersonalizationOut(
            level=rec.personalization.level.value,
            sessions_used=rec.personalization.sessions_used,
            note=rec.personalization.note,
        ),
        safety_status=rec.safety.status.value,
        alternative=alternative,
        health_alerts=alerts_out(alerts),
        evidence=[EvidenceOut(**e.to_dict()) for e in services.advisor.heat_evidence(rec.setting.zone)],
        cycle_day_used=cycle_day,
        cycle_day_source=cycle_day_source,
        model_version=rec.model_version,
    )


@router.post("/device-command", response_model=DeviceCommandResponse)
def device_command(
    body: DeviceCommandRequest,
    validator: SafetyValidator = Depends(get_validator),
) -> DeviceCommandResponse:
    """Re-validate the (possibly edited) setting the user confirmed and build the command."""
    setting = {
        "zone": body.zone,
        "temperature_c": body.temperature,
        "duration_min": body.duration,
        "therapy_mode": body.therapy_mode,
    }
    try:
        command = prepare_device_command(setting, body.user_confirmed, validator)
    except DeviceCommandRefused as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            {"safety_status": "rejected", "reasons": list(exc.reasons)},
        )
    return DeviceCommandResponse(**command.to_dict())

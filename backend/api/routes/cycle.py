"""Cycle prediction endpoint."""

from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status

from api.routes.recommend import alerts_out
from api.schemas import CycleFactorOut, CyclePredictRequest, CyclePredictResponse, PainDayOut
from api.services.dependencies import AppServices, get_cycle_predictor, get_cycle_repository, get_services, get_today
from api.services.cycle_repository import CycleRepository
from api.services.repository import RepositoryError
from api.services.user_context import load_user_context, personal_graph
from ml.cycle.predictor import CyclePredictor, NoPeriodDataError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/cycle")


@router.post("/predict", response_model=CyclePredictResponse)
def predict_cycle(
    body: CyclePredictRequest,
    services: AppServices = Depends(get_services),
    predictor: CyclePredictor = Depends(get_cycle_predictor),
    repository: CycleRepository = Depends(get_cycle_repository),
    today: date = Depends(get_today),
) -> CyclePredictResponse:
    # TODO(auth): take the user id from the verified Supabase JWT.
    context = load_user_context(services, body.user_id)
    try:
        forecast = predictor.predict(context.periods, context.daily_logs, context.profile, today)
    except NoPeriodDataError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))

    # Cycle-pattern alerts (e.g. no period for 90 days) from the personal knowledge graph.
    alerts = [a for a in personal_graph(services, body.user_id, context, today).alerts if a.origin == "cycle_pattern"]

    saved = False
    if body.save:
        try:
            repository.save_prediction(body.user_id, forecast)
            saved = True
        except RepositoryError:
            logger.exception("failed to save prediction")
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "could not save the prediction")

    threshold = services.settings.high_pain_threshold
    return CyclePredictResponse(
        method=forecast.method,
        last_period_start=forecast.last_period_start,
        predicted_start=forecast.predicted_start,
        range_days=forecast.range_days,
        predicted_cycle_length=forecast.predicted_cycle_length,
        predicted_period_length=forecast.predicted_period_length,
        period_length_range_days=forecast.period_length_range_days,
        days_until_start=forecast.days_until_start,
        is_late=forecast.is_late,
        pain_forecast=[PainDayOut(**d.to_dict()) for d in forecast.pain_forecast],
        high_pain_dates=[d.date for d in forecast.pain_forecast if d.expected_pain >= threshold],
        personalization_level=forecast.personalization_level.value,
        complete_cycles=forecast.complete_cycles,
        explanation=forecast.explanation,
        factors=[CycleFactorOut(**f.__dict__) for f in forecast.factors],
        health_alerts=alerts_out(alerts),
        model_version=forecast.model_version,
        saved=saved,
    )

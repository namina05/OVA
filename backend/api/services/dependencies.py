"""Shared objects for the routes, held on app.state and created at startup."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

from fastapi import HTTPException, Request, status

from api.services.cycle_repository import CycleRepository
from api.services.repository import TherapySessionRepository
from config import AppSettings
from knowledge_graph.advisor import ClinicalAdvisor
from knowledge_graph.graph import KnowledgeGraph
from knowledge_graph.personal import PersonalGraphBuilder
from ml.cycle.predictor import CyclePredictor
from ml.recommendation.service import RecommendationService
from safety.limits import SafetyLimits
from safety.validator import SafetyValidator


@dataclass
class AppServices:
    settings: AppSettings
    limits: SafetyLimits
    validator: SafetyValidator
    recommender: RecommendationService | None
    repository: TherapySessionRepository | None
    graph: KnowledgeGraph
    advisor: ClinicalAdvisor
    personal_graphs: PersonalGraphBuilder
    cycle_predictor: CyclePredictor | None = None
    cycle_repository: CycleRepository | None = None


def get_services(request: Request) -> AppServices:
    return request.app.state.services


def get_today() -> date:
    """Today's date (UTC). Overridden in tests."""
    return datetime.now(timezone.utc).date()


def get_recommender(request: Request) -> RecommendationService:
    recommender = get_services(request).recommender
    if recommender is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "recommendation model is not loaded")
    return recommender


def get_repository(request: Request) -> TherapySessionRepository:
    repository = get_services(request).repository
    if repository is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "therapy session store is not configured")
    return repository


def get_cycle_predictor(request: Request) -> CyclePredictor:
    predictor = get_services(request).cycle_predictor
    if predictor is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "cycle model is not loaded")
    return predictor


def get_cycle_repository(request: Request) -> CycleRepository:
    repository = get_services(request).cycle_repository
    if repository is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "cycle data store is not configured")
    return repository


def get_validator(request: Request) -> SafetyValidator:
    return get_services(request).validator

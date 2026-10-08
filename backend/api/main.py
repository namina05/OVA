"""FastAPI application.

Run:  uvicorn api.main:app --port 8000      (from the backend/ directory)
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from api.routes.cycle import router as cycle_router
from api.routes.knowledge import router as knowledge_router
from api.routes.recommend import router as recommend_router
from api.services.auth import SupabaseTokenVerifier, TokenVerifier
from api.services.cycle_repository import CycleRepository, PostgresCycleRepository
from api.services.dependencies import AppServices
from api.services.repository import PostgresTherapySessionRepository, TherapySessionRepository
from config import AppSettings
from knowledge_graph.advisor import ClinicalAdvisor
from knowledge_graph.graph import KnowledgeGraph
from knowledge_graph.personal import PersonalGraphBuilder
from knowledge_graph.store import GraphStoreError, load_graph_from_postgres
from ml.cycle.model_store import CycleModelBundle, load_cycle_bundle
from ml.cycle.predictor import CyclePredictor
from ml.models.model_store import ModelBundle, ModelNotFoundError, load_bundle
from ml.recommendation.service import RecommendationService
from safety.limits import SafetyLimits, load_safety_limits
from safety.validator import SafetyValidator

logger = logging.getLogger(__name__)


def load_knowledge_graph(settings: AppSettings) -> KnowledgeGraph:
    bundled = KnowledgeGraph.load_json(settings.knowledge_graph_path)
    use_db = settings.knowledge_graph_source == "postgres" or (
        settings.knowledge_graph_source == "auto" and settings.database_url
    )
    if not use_db:
        return bundled
    if not settings.database_url:
        raise RuntimeError("OVA_KNOWLEDGE_GRAPH_SOURCE=postgres needs DATABASE_URL")
    try:
        return load_graph_from_postgres(settings.database_url, fallback_sources=bundled.sources)
    except GraphStoreError:
        if settings.knowledge_graph_source == "postgres":
            raise
        logger.warning("could not load the knowledge graph from Postgres; using the bundled file", exc_info=True)
        return bundled


def _warn_if_synthetic(name: str, metadata: dict) -> None:
    if metadata.get("synthetic_data"):
        logger.warning("the loaded %s model was trained on SYNTHETIC data; do not use it with real users", name)


def build_services(
    settings: AppSettings,
    limits: SafetyLimits,
    bundle: ModelBundle | None = None,
    repository: TherapySessionRepository | None = None,
    cycle_bundle: CycleModelBundle | None = None,
    cycle_repository: CycleRepository | None = None,
    graph: KnowledgeGraph | None = None,
    verifier: TokenVerifier | None = None,
) -> AppServices:
    validator = SafetyValidator(limits)

    if bundle is None:
        try:
            bundle = load_bundle(settings.model_dir)
        except ModelNotFoundError:
            logger.error("no therapy model at %s; /recommend will return 503 until one is trained", settings.model_dir)
    if bundle is not None:
        _warn_if_synthetic("therapy", bundle.metadata)
    recommender = (
        RecommendationService(
            bundle, limits,
            personalization_min_sessions=settings.personalization_min_sessions,
            tie_tolerance=settings.tie_tolerance,
            validator=validator,
        )
        if bundle is not None else None
    )

    if cycle_bundle is None:
        try:
            cycle_bundle = load_cycle_bundle(settings.cycle_model_dir)
        except ModelNotFoundError:
            logger.error("no cycle model at %s; /cycle/predict will return 503", settings.cycle_model_dir)
    if cycle_bundle is not None:
        _warn_if_synthetic("cycle", cycle_bundle.metadata)
    cycle_predictor = (
        CyclePredictor(cycle_bundle, min_cycles_for_model=settings.min_cycles_for_model)
        if cycle_bundle is not None else None
    )

    if settings.database_url:
        repository = repository or PostgresTherapySessionRepository.from_settings(settings)
        cycle_repository = cycle_repository or PostgresCycleRepository(settings.database_url)
    if repository is None:
        logger.error("DATABASE_URL is not set; /recommend will return 503")

    if verifier is None and settings.supabase_url:
        verifier = SupabaseTokenVerifier(settings.supabase_url)
    if verifier is None:
        logger.warning("SUPABASE_URL is not set: requests are NOT checked for sign-in. Local development only.")

    graph = graph or load_knowledge_graph(settings)
    return AppServices(
        settings=settings,
        limits=limits,
        validator=validator,
        recommender=recommender,
        repository=repository,
        graph=graph,
        advisor=ClinicalAdvisor(graph),
        personal_graphs=PersonalGraphBuilder(graph, symptom_lookback_days=settings.symptom_lookback_days),
        cycle_predictor=cycle_predictor,
        cycle_repository=cycle_repository,
        verifier=verifier,
    )


def create_app(services: AppServices | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if not hasattr(app.state, "services"):
            app.state.services = build_services(AppSettings.from_env(), load_safety_limits())
        yield

    app = FastAPI(title="OVA recommender, cycle predictions and knowledge graph", version="0.2.0", lifespan=lifespan)
    if services is not None:
        app.state.services = services
    app.include_router(recommend_router)
    app.include_router(cycle_router)
    app.include_router(knowledge_router)

    @app.get("/health")
    def health() -> dict[str, object]:
        s: AppServices = app.state.services
        return {
            "status": "ok",
            "model_loaded": s.recommender is not None,
            "model_version": s.recommender.bundle.version if s.recommender else None,
            "cycle_model_loaded": s.cycle_predictor is not None,
            "cycle_model_version": s.cycle_predictor.bundle.version if s.cycle_predictor else None,
            "knowledge_graph": {"version": s.graph.version, "nodes": len(s.graph.nodes), "edges": len(s.graph.edges)},
            "session_store": s.repository is not None,
            "cycle_store": s.cycle_repository is not None,
            "sign_in_required": s.verifier is not None,
        }

    return app


app = create_app()

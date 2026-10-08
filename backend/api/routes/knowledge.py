"""Knowledge-graph endpoints for the app and the chatbot."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Request

from api.schemas import GraphOut, PersonalGraphOut, SymptomOut
from api.services.dependencies import AppServices, get_services, get_today, require_user
from api.services.user_context import load_user_context, personal_graph, symptom_window_start

router = APIRouter(prefix="/knowledge-graph")


@router.get("/clinical", response_model=GraphOut)
def clinical_graph(services: AppServices = Depends(get_services)) -> GraphOut:
    return GraphOut(**services.graph.to_dict())


@router.get("/symptoms", response_model=list[SymptomOut])
def symptoms(services: AppServices = Depends(get_services)) -> list[SymptomOut]:
    """Symptom keys the app can offer and store in daily_logs.symptoms."""
    return [
        SymptomOut(key=n.id.split(":", 1)[1], label=n.label, red_flag=bool(n.properties.get("red_flag")))
        for n in sorted(services.graph.nodes_of_type("symptom"), key=lambda n: n.label)
    ]


@router.get("/users/{user_id}", response_model=PersonalGraphOut)
def user_graph(
    user_id: str,
    request: Request,
    services: AppServices = Depends(get_services),
    today: date = Depends(get_today),
) -> PersonalGraphOut:
    require_user(request, user_id)
    context = load_user_context(services, user_id, logs_since=symptom_window_start(services, today))
    return PersonalGraphOut(**personal_graph(services, user_id, context, today).to_dict())

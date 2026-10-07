from datetime import date, timedelta

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from api.main import build_services, create_app
from api.services.cycle_repository import DataFrameCycleRepository
from api.services.dependencies import get_today
from api.services.repository import DataFrameTherapySessionRepository
from config import AppSettings
from ml.cycle import data as cd

TODAY = date(2026, 10, 1)
REGULAR = "regular-user"  # 28-day cycles, last period started 2026-09-25
LAPSED = "lapsed-user"  # last period 2026-05-01: more than 90 days ago
SYMPTOMATIC = "symptomatic-user"  # logged a fever with period pain last week


def _periods(user: str, last_start: date, n: int, length: int = 28) -> list[dict]:
    starts = [last_start - timedelta(days=length * i) for i in reversed(range(n))]
    return [{cd.USER_ID: user, cd.START: s, cd.END: s + timedelta(days=4)} for s in starts]


@pytest.fixture(scope="module")
def cycle_repo(cycle_data):
    periods = pd.concat([
        cycle_data.periods,
        pd.DataFrame(_periods(REGULAR, date(2026, 9, 25), 6) + _periods(LAPSED, date(2026, 5, 1), 4)
                     + _periods(SYMPTOMATIC, date(2026, 9, 20), 4)),
    ])
    logs = pd.concat([
        cycle_data.daily_logs,
        pd.DataFrame([{cd.USER_ID: SYMPTOMATIC, cd.LOG_DATE: date(2026, 9, 24), cd.PAIN: 7,
                       cd.SYMPTOMS: ["fever_with_period_pain"]}]),
    ])
    return DataFrameCycleRepository(periods, logs, cycle_data.profiles)


def make_client(bundle, limits, sessions, cycle_bundle, cycle_repo, settings=AppSettings()):
    services = build_services(
        settings, limits, bundle=bundle, repository=DataFrameTherapySessionRepository(sessions),
        cycle_bundle=cycle_bundle, cycle_repository=cycle_repo,
    )
    app = create_app(services)
    app.dependency_overrides[get_today] = lambda: TODAY
    return TestClient(app)


@pytest.fixture(scope="module")
def client(bundle, limits, synthetic_sessions, cycle_bundle, cycle_repo):
    with make_client(bundle, limits, synthetic_sessions, cycle_bundle, cycle_repo) as c:
        yield c


# -- cycle ---------------------------------------------------------------------

def test_cycle_prediction_for_regular_user(client, cycle_repo):
    r = client.post("/cycle/predict", json={"user_id": REGULAR, "save": True})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["method"] == "model"
    assert abs(date.fromisoformat(body["predicted_start"]) - date(2026, 10, 23)).days <= 3
    assert body["personalization_level"] == "personalized"
    assert body["pain_forecast"] and body["pain_forecast"][0]["day"] == -2
    assert body["saved"] and cycle_repo.saved[-1]["user_id"] == REGULAR
    assert cycle_repo.saved[-1]["method"] == "model"
    assert "contraception" in body["notice"]
    assert body["health_alerts"] == []


def test_lapsed_user_gets_no_period_alert(client):
    body = client.post("/cycle/predict", json={"user_id": LAPSED}).json()
    assert body["is_late"]
    [alert] = body["health_alerts"]
    assert alert["trigger"] == "pattern:no_period_90_days"
    assert alert["evidence"][0]["quote"].startswith("But if you don")


def test_cycle_prediction_without_periods_is_404(client):
    assert client.post("/cycle/predict", json={"user_id": "nobody"}).status_code == 404


def test_cycle_prediction_without_model_is_503(bundle, limits, synthetic_sessions, cycle_repo, tmp_path):
    services = build_services(
        AppSettings(cycle_model_dir=tmp_path), limits, bundle=bundle,
        repository=DataFrameTherapySessionRepository(synthetic_sessions), cycle_repository=cycle_repo,
    )
    with TestClient(create_app(services)) as c:
        assert c.post("/cycle/predict", json={"user_id": REGULAR}).status_code == 503


# -- recommend + knowledge graph ------------------------------------------------

def test_recommend_derives_cycle_day_and_cites_evidence(client):
    body = client.post("/recommend", json={"user_id": REGULAR, "pain_level": 6}).json()
    assert body["status"] == "recommended"
    assert body["cycle_day_used"] == 7 and body["cycle_day_source"] == "period_log"
    assert body["evidence"] and all(e["quote"] and e["source"].startswith("https://") for e in body["evidence"])


def test_reported_red_flag_is_alerted_alongside_recommendation(client):
    body = client.post("/recommend", json={
        "user_id": REGULAR, "pain_level": 9, "cycle_day": 1, "symptoms": ["severe_pain_painkillers_not_helping"],
    }).json()
    assert body["status"] == "recommended"
    assert body["cycle_day_source"] == "reported"
    [alert] = body["health_alerts"]
    assert alert["care_level"] == "urgent" and alert["origin"] == "reported_now"
    assert body["explanation"].startswith("Please read the health alert")


def test_logged_symptom_from_daily_logs_is_alerted(client):
    body = client.post("/recommend", json={"user_id": SYMPTOMATIC, "pain_level": 5}).json()
    assert [a["trigger"] for a in body["health_alerts"]] == ["symptom:fever_with_period_pain"]
    assert body["health_alerts"][0]["origin"] == "logged_recently"


def test_emergency_withholds_heat_recommendation(client):
    body = client.post("/recommend", json={"user_id": REGULAR, "pain_level": 8, "symptoms": ["tss_symptoms"]}).json()
    assert body["status"] == "withheld"
    assert body["zone"] is None and body["temperature"] is None and body["safety_status"] is None
    assert body["health_alerts"][0]["care_level"] == "emergency"


def test_withholding_levels_are_configurable(bundle, limits, synthetic_sessions, cycle_bundle, cycle_repo):
    settings = AppSettings(withhold_care_levels=("emergency", "urgent"))
    with make_client(bundle, limits, synthetic_sessions, cycle_bundle, cycle_repo, settings) as c:
        body = c.post("/recommend", json={
            "user_id": REGULAR, "pain_level": 9, "symptoms": ["severe_pain_painkillers_not_helping"],
        }).json()
    assert body["status"] == "withheld"


def test_unknown_symptom_is_rejected(client):
    r = client.post("/recommend", json={"user_id": REGULAR, "pain_level": 5, "symptoms": ["headache_xyz"]})
    assert r.status_code == 422
    assert r.json()["detail"]["unknown_symptoms"] == ["headache_xyz"]


def test_symptom_vocabulary_and_clinical_graph(client):
    symptoms = {s["key"]: s for s in client.get("/knowledge-graph/symptoms").json()}
    assert symptoms["fever_with_period_pain"]["red_flag"] is True
    assert symptoms["menstrual_cramps"]["red_flag"] is False
    graph = client.get("/knowledge-graph/clinical").json()
    assert graph["nodes"] and all(e["evidence"] for e in graph["edges"])


def test_personal_graph_endpoint(client):
    body = client.get(f"/knowledge-graph/users/{SYMPTOMATIC}").json()
    assert body["user_node"] == f"user:{SYMPTOMATIC}"
    assert any(e["relation"] == "LOGGED" for e in body["edges"])
    assert body["alerts"][0]["trigger"] == "symptom:fever_with_period_pain"


def test_health_reports_all_components(client):
    body = client.get("/health").json()
    assert body["cycle_model_loaded"] and body["knowledge_graph"]["edges"] > 0

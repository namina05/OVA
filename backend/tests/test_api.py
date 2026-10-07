import pandas as pd
import pytest
from fastapi.testclient import TestClient

from api.main import build_services, create_app
from api.services.repository import (
    DataFrameTherapySessionRepository,
    PostgresTherapySessionRepository,
    RepositoryError,
    zone_number_to_name,
)
from config import AppSettings
from safety.validator import SafetyValidator

USER_WITH_HISTORY = "synthetic-user-0001"


@pytest.fixture(scope="module")
def client(bundle, limits, synthetic_sessions):
    services = build_services(
        AppSettings(), limits, bundle=bundle, repository=DataFrameTherapySessionRepository(synthetic_sessions)
    )
    with TestClient(create_app(services)) as c:
        yield c


def test_health(client):
    body = client.get("/health").json()
    assert body["model_loaded"] and body["session_store"]


def test_recommend_returns_a_validated_explained_setting(client, limits):
    r = client.post("/recommend", json={
        "user_id": USER_WITH_HISTORY, "pain_level": 7, "pain_location": "lower_abdomen", "cycle_day": 2,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["safety_status"] == "approved"
    assert body["requires_user_confirmation"] is True
    assert SafetyValidator(limits).validate({
        "zone": body["zone"], "temperature_c": body["temperature"],
        "duration_min": body["duration"], "therapy_mode": body["therapy_mode"],
    }).approved
    assert body["explanation"].startswith("Recommended:")
    assert body["top_factors"] and all("contribution" in f for f in body["top_factors"])
    assert body["personalization"]["sessions_used"] > 0


def test_unknown_user_gets_a_cold_start_recommendation(client):
    body = client.post("/recommend", json={"user_id": "new-user", "pain_level": 6}).json()
    assert body["personalization"]["level"] == "none"
    assert "not personalized" in body["explanation"]


@pytest.mark.parametrize("payload", [
    {"user_id": "u", "pain_level": 11},
    {"user_id": "u", "pain_level": -1},
    {"user_id": "", "pain_level": 5},
    {"pain_level": 5},
    {"user_id": "u", "pain_level": 5, "cycle_phase": "winter"},
])
def test_invalid_requests_are_rejected(client, payload):
    assert client.post("/recommend", json=payload).status_code == 422


def test_missing_model_gives_503(limits, synthetic_sessions, tmp_path):
    services = build_services(
        AppSettings(model_dir=tmp_path), limits, repository=DataFrameTherapySessionRepository(synthetic_sessions)
    )
    with TestClient(create_app(services)) as c:
        assert c.post("/recommend", json={"user_id": "u", "pain_level": 5}).status_code == 503


def test_unreadable_history_gives_503(bundle, limits):
    class Broken:
        def get_user_sessions(self, user_id):
            raise RepositoryError("down")

        def get_all_sessions(self):
            raise RepositoryError("down")

    with TestClient(create_app(build_services(AppSettings(), limits, bundle=bundle, repository=Broken()))) as c:
        assert c.post("/recommend", json={"user_id": "u", "pain_level": 5}).status_code == 503


def test_device_command_needs_confirmation_and_safe_values(client):
    setting = {"zone": "lower_abdomen", "temperature": 40, "duration": 20, "therapy_mode": "continuous"}
    assert client.post("/device-command", json=setting).status_code == 422
    unsafe = client.post("/device-command", json={**setting, "temperature": 48, "user_confirmed": True})
    assert unsafe.status_code == 422
    assert unsafe.json()["detail"]["safety_status"] == "rejected"
    ok = client.post("/device-command", json={**setting, "user_confirmed": True})
    assert ok.status_code == 200
    assert ok.json() == {
        "zone": "lower_abdomen", "target_temperature_c": 40.0, "duration_s": 1200,
        "therapy_mode": "continuous", "safety_status": "approved",
    }


def test_zone_numbers_map_to_names():
    names = ("lower_abdomen", "lower_back")
    assert zone_number_to_name(1, names) == "lower_abdomen"
    assert zone_number_to_name(3, names) is None
    assert zone_number_to_name(None, names) is None


def test_postgres_repository_rejects_unsafe_table_names():
    with pytest.raises(ValueError):
        PostgresTherapySessionRepository("postgresql://x", "therapy_sessions; drop table x", ("a",), 10)


def test_settings_from_env():
    s = AppSettings.from_env({"OVA_PERSONALIZATION_MIN_SESSIONS": "8", "OVA_ZONE_NAMES": "a, b"})
    assert s.personalization_min_sessions == 8
    assert s.zone_names == ("a", "b")

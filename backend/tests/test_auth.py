import pandas as pd
import pytest
from fastapi.testclient import TestClient

from api.main import build_services, create_app
from api.services.auth import InvalidToken
from api.services.cycle_repository import DataFrameCycleRepository
from api.services.repository import DataFrameTherapySessionRepository
from config import AppSettings

USER = "user-a"


class FakeVerifier:
    """Accepts tokens of the form `token-for-<user id>`."""

    def user_id(self, token: str) -> str:
        if not token.startswith("token-for-"):
            raise InvalidToken("not a token")
        return token.removeprefix("token-for-")


@pytest.fixture(scope="module")
def client(bundle, limits, synthetic_sessions, cycle_bundle, cycle_data):
    services = build_services(
        AppSettings(), limits, bundle=bundle,
        repository=DataFrameTherapySessionRepository(synthetic_sessions),
        cycle_bundle=cycle_bundle,
        cycle_repository=DataFrameCycleRepository(cycle_data.periods, cycle_data.daily_logs, cycle_data.profiles),
        verifier=FakeVerifier(),
    )
    return TestClient(create_app(services))


def _as(user: str) -> dict[str, str]:
    return {"Authorization": f"Bearer token-for-{user}"}


REQUESTS = [
    ("post", "/cycle/predict", {"user_id": USER}),
    ("post", "/recommend", {"user_id": USER, "pain_level": 6}),
    ("get", f"/knowledge-graph/users/{USER}", None),
]


@pytest.mark.parametrize("method, path, body", REQUESTS)
def test_requests_without_a_valid_token_are_refused(client, method, path, body):
    assert client.request(method, path, json=body).status_code == 401
    assert client.request(method, path, json=body, headers={"Authorization": "Bearer nonsense"}).status_code == 401


@pytest.mark.parametrize("method, path, body", REQUESTS)
def test_a_user_cannot_ask_about_someone_else(client, method, path, body):
    assert client.request(method, path, json=body, headers=_as("user-b")).status_code == 403


@pytest.mark.parametrize("method, path, body", REQUESTS)
def test_a_signed_in_user_gets_past_the_check(client, method, path, body):
    # 404 is the cycle endpoint's answer for a user with no logged periods.
    assert client.request(method, path, json=body, headers=_as(USER)).status_code in (200, 404)


def test_shared_knowledge_needs_no_sign_in(client):
    assert client.get("/knowledge-graph/symptoms").status_code == 200
    assert client.get("/health").json()["sign_in_required"] is True

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        owner_username="owner",
        owner_password="test-password-123",
        database_url=f"sqlite:///{tmp_path / 'fred-test.db'}",
        ai_provider="mock",
        api_rate_limit_per_minute=500,
        login_rate_limit_per_minute=100,
        chat_rate_limit_per_minute=100,
    )


@pytest.fixture
def client(settings: Settings):
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def login(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/auth/login",
        json={"username": "owner", "password": "test-password-123"},
    )
    assert response.status_code == 200, response.text
    return {"X-CSRF-Token": response.json()["csrf_token"]}


@pytest.fixture
def authorized(client: TestClient):
    return client, login(client)

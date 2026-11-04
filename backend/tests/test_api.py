from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update
from starlette.websockets import WebSocketDisconnect

from app.ai.providers import ProviderError
from app.database.session import create_database
from app.main import create_app
from app.models.entities import AuthSession
from conftest import login


def test_health_is_public_and_reports_mock_provider(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["provider"] == "mock"


@pytest.mark.parametrize("path", [
    "/api/auth/me", "/api/conversations", "/api/memories",
    "/api/memories/export", "/api/settings", "/api/system",
])
def test_private_reads_require_authentication(client, path):
    assert client.get(path).status_code == 401


def test_login_rejects_invalid_credentials_and_untrusted_origins(client):
    assert client.post(
        "/api/auth/login", json={"username": "owner", "password": "incorrect"}
    ).status_code == 401
    assert client.post(
        "/api/auth/login",
        json={"username": "owner", "password": "test-password-123"},
        headers={"Origin": "https://untrusted.example"},
    ).status_code == 403
    assert client.get("/api/auth/me").status_code == 401


def test_login_session_cookie_is_httponly_and_authenticates(client):
    response = client.post(
        "/api/auth/login",
        json={"username": "owner", "password": "test-password-123"},
        headers={"Origin": "http://localhost:5173"},
    )
    assert response.status_code == 200
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=strict" in cookie
    assert client.get("/api/auth/me").json()["user"]["username"] == "owner"


def test_mutations_require_session_bound_csrf_and_trusted_origin(authorized):
    client, headers = authorized
    payload = {"category": "personal", "content": "Use concise replies."}
    assert client.post("/api/memories", json=payload).status_code == 403
    assert client.post(
        "/api/memories", json=payload, headers={"X-CSRF-Token": "wrong"}
    ).status_code == 403
    assert client.post(
        "/api/memories", json=payload,
        headers={**headers, "Origin": "https://untrusted.example"},
    ).status_code == 403
    assert client.get("/api/memories").json() == []


def test_memory_review_search_update_export_and_delete(authorized):
    client, headers = authorized
    response = client.post(
        "/api/memories", json={"category": "personal", "content": "I prefer Italian espresso."},
        headers=headers,
    )
    assert response.status_code in (200, 201), response.text
    memory = response.json()
    assert memory["category"] == "personal"
    assert memory["created_at"]
    memory_id = memory["id"]
    assert len(client.get("/api/memories", params={"q": "espresso"}).json()) == 1
    assert client.get("/api/memories", params={"q": "nonexistent-term"}).json() == []

    update = client.patch(
        f"/api/memories/{memory_id}",
        json={"category": "operational", "content": "Order espresso for the office."},
        headers=headers,
    )
    assert update.status_code == 200
    assert update.json()["category"] == "operational"
    assert "Order espresso for the office." in client.get("/api/memories/export").text
    assert client.delete(f"/api/memories/{memory_id}", headers=headers).status_code in (200, 204)
    assert client.get("/api/memories").json() == []
    assert "Order espresso for the office." not in client.get("/api/memories/export").text


def test_inputs_are_validated(authorized):
    client, headers = authorized
    assert client.post("/api/chat", json={"message": ""}, headers=headers).status_code == 422
    assert client.post(
        "/api/memories", json={"category": "secret", "content": "unknown category"},
        headers=headers,
    ).status_code == 422
    assert client.put("/api/settings", json={"mode": "unrestricted"}, headers=headers).status_code == 422


def test_mock_chat_persists_history_and_memory_across_restart(settings):
    with TestClient(create_app(settings)) as first:
        headers = login(first)
        memory = first.post(
            "/api/memories", json={"category": "personal", "content": "Prefer concise replies."},
            headers=headers,
        ).json()
        response = first.post("/api/chat", json={"message": "Good morning, Fred."}, headers=headers)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["provider"] == "mock"
        assert body["message"]["role"] == "assistant"
        assert "mock" in body["message"]["content"].lower()
        conversation_id = body["conversation_id"]

    with TestClient(create_app(settings)) as second:
        login(second)
        history = second.get(f"/api/conversations/{conversation_id}/messages").json()
        assert [message["role"] for message in history] == ["user", "assistant"]
        assert history[0]["content"] == "Good morning, Fred."
        assert history[1]["content"] == body["message"]["content"]
        assert second.get("/api/memories").json()[0]["id"] == memory["id"]


def test_continue_and_delete_conversation(authorized):
    client, headers = authorized
    created = client.post("/api/conversations", json={}, headers=headers)
    assert created.status_code in (200, 201), created.text
    conversation_id = created.json()["id"]
    for message in ("Hello Fred", "Focus mode, please"):
        response = client.post(
            "/api/chat", json={"message": message, "conversation_id": conversation_id}, headers=headers
        )
        assert response.status_code == 200, response.text
        assert response.json()["conversation_id"] == conversation_id
    assert len(client.get(f"/api/conversations/{conversation_id}/messages").json()) == 4
    assert client.delete(f"/api/conversations/{conversation_id}", headers=headers).status_code in (200, 204)
    assert client.get(f"/api/conversations/{conversation_id}/messages").status_code == 404
    assert not any(item["id"] == conversation_id for item in client.get("/api/conversations").json())


def test_settings_persist_after_restart(settings):
    with TestClient(create_app(settings)) as first:
        headers = login(first)
        response = first.put(
            "/api/settings", json={"mode": "executive", "model": "gpt-4.1-mini"}, headers=headers
        )
        assert response.status_code == 200, response.text
        assert response.json()["mode"] == "executive"
        assert response.json()["provider"] == "mock"
    with TestClient(create_app(settings)) as second:
        login(second)
        assert second.get("/api/settings").json()["mode"] == "executive"


def test_provider_failure_is_clear_and_does_not_fabricate_assistant_reply(authorized):
    client, headers = authorized

    class FailingProvider:
        async def complete(self, messages, model):
            raise ProviderError("OpenAI rejected the API credentials. Check OPENAI_API_KEY.", status_code=502)

    client.app.state.ai_provider = FailingProvider()
    response = client.post("/api/chat", json={"message": "Please respond."}, headers=headers)
    assert response.status_code == 502
    assert "credentials" in response.json()["detail"].lower()
    conversation_id = client.get("/api/conversations").json()[0]["id"]
    history = client.get(f"/api/conversations/{conversation_id}/messages").json()
    assert [item["role"] for item in history] == ["user"]


def test_chat_retrieves_bounded_relevant_memories_as_reference_data(authorized):
    client, headers = authorized
    markers = [f"APPROVED_ESPRESSO_CONTEXT_{index}" for index in range(8)]
    for marker in markers:
        response = client.post(
            "/api/memories", headers=headers,
            json={"category": "operational", "content": f"Espresso project: {marker}"},
        )
        assert response.status_code in (200, 201)
    client.post(
        "/api/memories", headers=headers,
        json={"category": "personal", "content": "NONMATCHING_PRIVATE_PERSONAL_DETAIL"},
    )

    captured = []

    class CapturingProvider:
        async def complete(self, messages, model):
            captured.extend(messages)
            return "Context received."

    client.app.state.ai_provider = CapturingProvider()
    response = client.post(
        "/api/chat", json={"message": "Review espresso priorities"}, headers=headers,
    )
    assert response.status_code == 200, response.text
    all_content = "\n".join(item["content"] for item in captured)
    assert "NONMATCHING_PRIVATE_PERSONAL_DETAIL" not in all_content
    assert 1 <= sum(marker in all_content for marker in markers) <= 5
    system_content = "\n".join(item["content"] for item in captured if item["role"] == "system")
    assert not any(marker in system_content for marker in markers)
    assert "untrusted" in system_content.lower()


def test_logout_revokes_session(authorized):
    client, headers = authorized
    old_cookies = dict(client.cookies)
    assert client.post("/api/auth/logout", headers=headers).status_code in (200, 204)
    client.cookies.update(old_cookies)
    assert client.get("/api/auth/me").status_code == 401


def test_expired_session_cannot_read_private_data_or_open_websocket(authorized, settings):
    client, _ = authorized
    engine, session_factory = create_database(settings.database_url)
    try:
        with session_factory() as db:
            db.execute(update(AuthSession).values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)))
            db.commit()
    finally:
        engine.dispose()
    assert client.get("/api/memories").status_code == 401
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/api/ws", headers={"Origin": "http://localhost:5173"}):
            pass


def test_csrf_token_is_bound_to_each_session(authorized):
    client, first_headers = authorized
    second_headers = login(client)
    assert first_headers["X-CSRF-Token"] != second_headers["X-CSRF-Token"]
    assert client.post(
        "/api/memories", json={"category": "personal", "content": "Rejected cross-session token"},
        headers=first_headers,
    ).status_code == 403


def test_other_configured_owner_cannot_access_existing_records(settings):
    with TestClient(create_app(settings)) as first:
        headers = login(first)
        memory_id = first.post(
            "/api/memories", json={"category": "personal", "content": "Owner confidential preference"},
            headers=headers,
        ).json()["id"]
        conversation_id = first.post(
            "/api/chat", json={"message": "Private conversation"}, headers=headers,
        ).json()["conversation_id"]

    alternate_settings = settings.model_copy(update={"owner_username": "alex"})
    with TestClient(create_app(alternate_settings)) as second:
        response = second.post(
            "/api/auth/login", json={"username": "alex", "password": "test-password-123"}
        )
        assert response.status_code == 200, response.text
        headers = {"X-CSRF-Token": response.json()["csrf_token"]}
        assert second.get("/api/memories").json() == []
        assert second.get("/api/conversations").json() == []
        assert "Owner confidential preference" not in second.get("/api/memories/export").text
        assert second.patch(
            f"/api/memories/{memory_id}", json={"content": "Overwritten"}, headers=headers
        ).status_code == 404
        assert second.delete(f"/api/memories/{memory_id}", headers=headers).status_code == 404
        assert second.get(f"/api/conversations/{conversation_id}/messages").status_code == 404
        assert second.delete(f"/api/conversations/{conversation_id}", headers=headers).status_code == 404
        assert second.post(
            "/api/chat", json={"message": "Append", "conversation_id": conversation_id}, headers=headers
        ).status_code == 404


def test_websocket_rejects_unauthenticated_client(client):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/api/ws", headers={"Origin": "http://localhost:5173"}):
            pass


def test_websocket_reports_actual_initial_idle_state(authorized):
    client, _ = authorized
    with client.websocket_connect("/api/ws", headers={"Origin": "http://localhost:5173"}) as socket:
        event = socket.receive_json()
        assert event["type"] == "status"
        assert event["status"] == "idle"


def test_websocket_rejects_untrusted_origin(authorized):
    client, _ = authorized
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/api/ws", headers={"Origin": "https://untrusted.example"}):
            pass


def test_websocket_rejects_revoked_session(authorized):
    client, headers = authorized
    old_cookies = dict(client.cookies)
    assert client.post("/api/auth/logout", headers=headers).status_code in (200, 204)
    client.cookies.update(old_cookies)
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/api/ws", headers={"Origin": "http://localhost:5173"}):
            pass


def test_login_rate_limit(settings):
    settings.login_rate_limit_per_minute = 2
    with TestClient(create_app(settings)) as client:
        credentials = {"username": "owner", "password": "wrong"}
        assert client.post("/api/auth/login", json=credentials).status_code == 401
        assert client.post("/api/auth/login", json=credentials).status_code == 401
        assert client.post("/api/auth/login", json=credentials).status_code == 429

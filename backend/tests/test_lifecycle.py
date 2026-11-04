import asyncio
import logging

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select

from app.core.config import Settings
from app.main import create_app
from app.models.entities import Message
from app.services.events import EventHub
from app.services.lifecycle import ServiceManager
from conftest import login


def test_lifespan_reports_readiness_and_stops_cleanly(settings):
    app = create_app(settings)
    with TestClient(app) as client:
        assert client.get('/api/ready').json() == {
            'status': 'ok', 'service': 'ready', 'database': 'connected',
        }
        manager = app.state.service
        assert manager.phase == 'ready'
    assert manager.phase == 'stopped'
    assert manager.readiness()['status'] == 'unavailable'


def test_readiness_detects_database_failure_without_leaking_details(settings, monkeypatch, caplog):
    with TestClient(create_app(settings)) as client:
        def broken_connect():
            raise RuntimeError('secret-database-password-and-private-message')
        monkeypatch.setattr(client.app.state.engine, 'connect', broken_connect)
        response = client.get('/api/ready')
        assert response.status_code == 503
        assert response.json()['database'] == 'unavailable'
        assert 'secret-database' not in response.text + caplog.text
        assert client.get('/api/health').status_code == 200  # Liveness != storage readiness.


def test_private_history_and_approved_memory_survive_service_restart(settings):
    with TestClient(create_app(settings)) as first:
        headers = login(first)
        reply = first.post('/api/chat', json={'message': 'Persistent test conversation'}, headers=headers)
        assert reply.status_code == 200
        conversation_id = reply.json()['conversation_id']
        memory = first.post('/api/memories', json={'category': 'personal', 'content': 'Approved test preference'}, headers=headers)
        assert memory.status_code == 201
        memory_id = memory.json()['id']
    with TestClient(create_app(settings)) as second:
        login(second)
        assert len(second.get(f'/api/conversations/{conversation_id}/messages').json()) == 2
        assert second.get('/api/memories').json()[0]['id'] == memory_id


def test_configuration_errors_never_print_secret_values():
    with pytest.raises(ValidationError) as caught:
        Settings(_env_file=None, owner_password='SENTINEL_OWNER_SECRET', openai_api_key='SENTINEL_AI_SECRET',
                 rooms=[{'id': 'room', 'name': 'Room'}, {'id': 'room', 'name': 'Duplicate'}])
    assert 'SENTINEL' not in str(caught.value)


def test_start_failure_is_sanitized_and_resources_released(settings, monkeypatch, caplog):
    import app.services.lifecycle as lifecycle
    def broken_database(_url):
        raise RuntimeError('SENTINEL_SQL_SECRET')
    monkeypatch.setattr(lifecycle, 'create_database', broken_database)
    manager = ServiceManager(settings, EventHub())
    with pytest.raises(RuntimeError, match='could not initialize') as caught:
        asyncio.run(manager.start())
    assert manager.phase == 'failed'
    assert 'SENTINEL' not in str(caught.value) + caplog.text


def test_requests_sanitize_unexpected_failures_without_logging_contents(settings, caplog):
    app = create_app(settings)
    @app.get('/unexpected-failure')
    def broken():
        raise RuntimeError('SENTINEL_PRIVATE_REQUEST')
    with TestClient(app) as client:
        with caplog.at_level(logging.ERROR):
            response = client.get('/unexpected-failure')
        assert response.status_code == 503
        assert 'SENTINEL' not in response.text + caplog.text
        assert 'request.failed' in caplog.text


def test_shutdown_cancels_active_inference_before_releasing_storage(settings):
    async def exercise():
        manager = ServiceManager(settings, EventHub())
        await manager.start()
        started = asyncio.Event()
        class WaitingProvider:
            async def complete(self, _messages, _model):
                started.set()
                await asyncio.Event().wait()
        task = asyncio.create_task(manager.assistant.respond(settings.owner_username, 'Wait here', provider=WaitingProvider()))
        await asyncio.wait_for(started.wait(), 5)
        await asyncio.wait_for(manager.stop(), 5)
        assert task.cancelled()
        assert manager.phase == 'stopped'
        with manager.factory() as db:
            assert [row.role for row in db.scalars(select(Message))] == ['user']
    asyncio.run(exercise())

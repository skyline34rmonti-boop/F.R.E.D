"""The conversation pipeline is exercised without an HTTP server or hardware."""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.ai.providers import MockProvider, ProviderError
from app.core.engine import AssistantEngine, AssistantError
from app.database.session import Base, create_database
from app.models.entities import AuditEntry, Conversation, Memory, Message, User, UserSettings


class Events:
    def __init__(self):
        self.statuses = []

    async def emit(self, owner, status, conversation_id=None):
        self.statuses.append(status)


@pytest.fixture
def pipeline(settings):
    database, factory = create_database(settings.database_url)
    Base.metadata.create_all(database)
    with factory() as db:
        db.add(User(username=settings.owner_username, display_name='Owner', password_hash='unused-test-hash', role='owner'))
        db.flush()
        db.add(UserSettings(owner_username=settings.owner_username, model='test-model', mode='standard'))
        db.commit()
    events = Events()
    assistant = AssistantEngine(settings, factory, MockProvider(), events)
    yield assistant, factory, events
    database.dispose()


def test_core_persists_turns_and_resumes_session_in_new_engine(pipeline, settings):
    assistant, factory, events = pipeline
    first = asyncio.run(assistant.respond(settings.owner_username, 'Hello'))
    replacement = AssistantEngine(settings, factory, MockProvider(), events)
    second = asyncio.run(replacement.respond(settings.owner_username, 'Continue', first['conversation_id']))
    assert second['conversation_id'] == first['conversation_id']
    assert second['message']['role'] == 'assistant'
    assert second['message']['created_at'].endswith('+00:00')
    with factory() as db:
        turns = list(db.scalars(select(Message).order_by(Message.created_at)))
        assert [turn.role for turn in turns] == ['user', 'assistant', 'user', 'assistant']
    assert events.statuses == ['thinking', 'idle', 'thinking', 'idle']


def test_core_checks_session_ownership_at_persistence_boundary(pipeline, settings):
    assistant, factory, _ = pipeline
    with factory() as db:
        db.add(User(username='another-owner', display_name='Other', password_hash='unused', role='owner'))
        db.flush()
        record = Conversation(owner_username='another-owner', title='Private')
        db.add(record)
        db.commit()
        foreign_id = record.id
    with pytest.raises(AssistantError) as denied:
        asyncio.run(assistant.respond(settings.owner_username, 'Append', foreign_id))
    assert denied.value.status_code == 404
    with pytest.raises(AssistantError) as wrong_identity:
        asyncio.run(assistant.respond('another-owner', 'Append'))
    assert wrong_identity.value.status_code == 403
    with factory() as db:
        assert list(db.scalars(select(Message))) == []


@pytest.mark.parametrize('message,mode', [('', None), (' ' * 5, None), ('x' * 8001, None), ('Hi', 'unrestricted')])
def test_core_validates_input_without_transport(pipeline, settings, message, mode):
    assistant, factory, _ = pipeline
    with pytest.raises(AssistantError) as failed:
        asyncio.run(assistant.respond(settings.owner_username, message, mode=mode))
    assert failed.value.status_code == 422
    with factory() as db:
        assert list(db.scalars(select(Conversation))) == []


def test_exact_mode_command_is_persisted_without_calling_provider(pipeline, settings):
    assistant, factory, _ = pipeline

    class UnusedProvider:
        async def complete(self, messages, model):
            raise AssertionError('A style command must not invoke AI')

    reply = asyncio.run(assistant.respond(settings.owner_username, 'Fred, enable focus mode.', provider=UnusedProvider()))
    assert reply['message']['content'] == f'Focus mode enabled, {settings.owner_name}.'
    with factory() as db:
        assert db.get(UserSettings, settings.owner_username).mode == 'focus'


def test_provider_failure_retains_user_turn_and_reports_clear_error(pipeline, settings):
    assistant, factory, events = pipeline

    class FailingProvider:
        async def complete(self, messages, model):
            raise ProviderError('Provider unavailable. Retry later.', 503)

    with pytest.raises(AssistantError, match='Provider unavailable') as failed:
        asyncio.run(assistant.respond(settings.owner_username, 'Hello', provider=FailingProvider()))
    assert failed.value.status_code == 503
    with factory() as db:
        assert [item.role for item in db.scalars(select(Message))] == ['user']
        assert db.scalars(select(AuditEntry).where(AuditEntry.outcome == 'provider_error')).first()
    assert events.statuses == ['thinking', 'error', 'idle']


def test_cancelled_turn_retains_user_message_and_releases_pipeline(pipeline, settings):
    assistant, factory, events = pipeline

    async def scenario():
        started = asyncio.Event()

        class WaitingProvider:
            async def complete(self, messages, model):
                started.set()
                await asyncio.Event().wait()

        active = asyncio.create_task(assistant.respond(settings.owner_username, 'Cancelled turn', provider=WaitingProvider()))
        await asyncio.wait_for(started.wait(), timeout=5)
        with pytest.raises(AssistantError) as busy:
            await assistant.respond(settings.owner_username, 'Concurrent turn')
        assert busy.value.status_code == 409
        active.cancel()
        with pytest.raises(asyncio.CancelledError):
            await active
        with factory() as db:
            assert [item.role for item in db.scalars(select(Message))] == ['user']
            assert db.scalars(select(AuditEntry).where(AuditEntry.outcome == 'cancelled')).first()
        response = await assistant.respond(settings.owner_username, 'Fresh turn')
        assert response['provider'] == 'mock'

    asyncio.run(scenario())
    assert events.statuses == ['thinking', 'idle', 'thinking', 'idle']


def test_shutdown_cancels_inference_and_rejects_new_work(pipeline, settings):
    assistant, _, events = pipeline

    async def scenario():
        started = asyncio.Event()

        class WaitingProvider:
            async def complete(self, messages, model):
                started.set()
                await asyncio.Event().wait()

        active = asyncio.create_task(assistant.respond(settings.owner_username, 'Pending turn', provider=WaitingProvider()))
        await asyncio.wait_for(started.wait(), timeout=5)
        await assistant.shutdown()
        assert active.cancelled()
        with pytest.raises(AssistantError) as closed:
            await assistant.respond(settings.owner_username, 'After shutdown')
        assert closed.value.status_code == 503

    asyncio.run(scenario())
    assert events.statuses[-1] == 'idle'


def test_context_is_bounded_and_owner_approved_memory_is_reference_data(pipeline, settings):
    assistant, factory, _ = pipeline
    with factory() as db:
        conversation = Conversation(owner_username=settings.owner_username, title='Long conversation')
        db.add(conversation)
        db.flush()
        conversation_id = conversation.id
        beginning = datetime.now(timezone.utc) - timedelta(hours=1)
        for index in range(40):
            db.add(Message(conversation_id=conversation_id, role='user', content=f'Past turn {index}',
                           created_at=beginning + timedelta(seconds=index)))
        db.add(Memory(owner_username=settings.owner_username, category='operational', content='Espresso APPROVED_CONTEXT'))
        db.add(Memory(owner_username=settings.owner_username, category='personal', content='Unrelated confidential record'))
        db.commit()
    captured = []

    class CapturingProvider:
        async def complete(self, messages, model):
            captured.extend(messages)
            assert model == 'test-model'
            return 'Bounded response.'

    asyncio.run(assistant.respond(settings.owner_username, 'Espresso priorities', conversation_id, provider=CapturingProvider()))
    assert len(captured) == 26  # system + explicit reference data + at most 24 history messages
    assert 'APPROVED_CONTEXT' not in captured[0]['content']
    assert 'UNTRUSTED STORED REFERENCE DATA' in captured[1]['content']
    assert 'APPROVED_CONTEXT' in captured[1]['content']
    assert not any('Unrelated confidential record' in item['content'] for item in captured)
    assert captured[-1]['content'] == 'Espresso priorities'


def test_memory_feature_flag_disables_retrieval(pipeline, settings):
    assistant, factory, _ = pipeline
    settings.memory_enabled = False
    with factory() as db:
        db.add(Memory(owner_username=settings.owner_username, category='personal', content='Espresso SECRET_REFERENCE'))
        db.commit()
    captured = []

    class CapturingProvider:
        async def complete(self, messages, model):
            captured.extend(messages)
            return 'No memory context.'

    asyncio.run(assistant.respond(settings.owner_username, 'Espresso', provider=CapturingProvider()))
    assert not any('SECRET_REFERENCE' in item['content'] for item in captured)


def test_unexpected_provider_exception_does_not_expose_sensitive_details(pipeline, settings, caplog):
    assistant, factory, events = pipeline

    class BrokenProvider:
        async def complete(self, messages, model):
            raise RuntimeError('PRIVATE_PROVIDER_CREDENTIAL_DETAIL')

    with pytest.raises(AssistantError) as failed:
        asyncio.run(assistant.respond(settings.owner_username, 'Hello', provider=BrokenProvider()))
    assert failed.value.status_code == 502
    assert 'PRIVATE_PROVIDER_CREDENTIAL_DETAIL' not in str(failed.value)
    assert 'PRIVATE_PROVIDER_CREDENTIAL_DETAIL' not in caplog.text
    with factory() as db:
        assert [item.role for item in db.scalars(select(Message))] == ['user']
    assert events.statuses == ['thinking', 'error', 'idle']

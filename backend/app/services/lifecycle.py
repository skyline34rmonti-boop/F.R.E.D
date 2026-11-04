"""Own service resources without depending on a desktop, microphone or OS driver."""
import logging

from sqlalchemy import delete, text

from app.ai.providers import MockProvider, OpenAIProvider
from app.core.config import Settings
from app.core.engine import AssistantEngine
from app.core.logging import operational_event
from app.core.security import password_hash, verify_password
from app.database.session import Base, create_database
from app.models.entities import AuthSession, User, UserSettings
from app.services.events import EventHub


class ServiceManager:
    def __init__(self, settings: Settings, events: EventHub) -> None:
        self.settings = settings
        self.events = events
        self.phase = 'starting'
        self.engine = self.factory = self.provider = self.assistant = None

    async def start(self) -> None:
        try:
            self.settings.validate_startup()
        except RuntimeError:
            self.phase = 'failed'
            operational_event('service.configuration_invalid', level=logging.ERROR)
            raise  # Validation messages contain setting names, never values.
        try:
            self.engine, self.factory = create_database(self.settings.database_url)
            Base.metadata.create_all(self.engine)
            with self.factory() as db:
                owner = db.get(User, self.settings.owner_username)
                password = self.settings.owner_password.get_secret_value()
                if owner is None:
                    owner = User(username=self.settings.owner_username, display_name=self.settings.owner_name,
                                 password_hash=password_hash(password), role='owner')
                    db.add(owner)
                    db.flush()
                elif not verify_password(password, owner.password_hash):
                    owner.password_hash = password_hash(password)
                    db.execute(delete(AuthSession).where(AuthSession.owner_username == owner.username))
                owner.display_name = self.settings.owner_name
                if not db.get(UserSettings, owner.username):
                    db.add(UserSettings(owner_username=owner.username, model=self.settings.openai_model, mode='standard'))
                db.commit()
            self.provider = (OpenAIProvider(self.settings.openai_api_key.get_secret_value(), self.settings.openai_timeout_seconds)
                             if self.settings.ai_provider == 'openai' else MockProvider())
            self.assistant = AssistantEngine(self.settings, self.factory, self.provider, self.events)
            self.phase = 'ready'
            operational_event('service.started', provider=self.settings.ai_provider)
        except Exception:
            self.phase = 'failed'
            try:
                await self._release()
            except Exception:
                operational_event('service.cleanup_failed', level=logging.ERROR)
            operational_event('service.start_failed', level=logging.ERROR)
            raise RuntimeError('FRED could not initialize storage or its provider. Verify configuration and storage access.') from None

    def readiness(self) -> dict:
        if self.phase != 'ready':
            return {'status': 'unavailable', 'service': self.phase, 'database': 'unknown'}
        try:
            with self.engine.connect() as connection:
                connection.execute(text('SELECT 1'))
        except Exception:
            return {'status': 'unavailable', 'service': self.phase, 'database': 'unavailable'}
        return {'status': 'ok', 'service': self.phase, 'database': 'connected'}

    async def _release(self) -> None:
        try:
            if self.assistant is not None:
                await self.assistant.shutdown()
        finally:
            try:
                if self.provider is not None and hasattr(self.provider, 'close'):
                    await self.provider.close()
            finally:
                if self.engine is not None:
                    self.engine.dispose()

    async def stop(self) -> None:
        self.phase = 'stopping'
        try:
            await self._release()
        except Exception:
            operational_event('service.stop_failed', level=logging.ERROR)
            raise RuntimeError('FRED resource cleanup failed. Check service health before restarting.') from None
        finally:
            self.phase = 'stopped'
            operational_event('service.stopped')

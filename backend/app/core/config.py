"""Typed server-only configuration, independent of OS and optional device drivers."""
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.integrations.contracts import DeviceDefinition, RoomDefinition
from app.integrations.registry import DeviceRegistry
from app.voice.contracts import VoiceSettings

ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / '.env', extra='ignore', populate_by_name=True,
                                      hide_input_in_errors=True)

    owner_username: str = Field('owner', validation_alias='FRED_OWNER_USERNAME', min_length=1, max_length=80)
    owner_password: SecretStr | None = Field(None, validation_alias='FRED_OWNER_PASSWORD')
    owner_name: str = Field('Owner', validation_alias='FRED_OWNER_NAME', min_length=1, max_length=80)
    ai_provider: Literal['mock', 'openai'] = Field('mock', validation_alias='FRED_AI_PROVIDER')
    openai_api_key: SecretStr | None = Field(None, validation_alias='OPENAI_API_KEY')
    openai_model: str = Field('gpt-4.1-mini', validation_alias='OPENAI_MODEL', min_length=1, max_length=120)
    personality_instruction: str = Field(
        'Communicate naturally and professionally. Be concise, confident, and clear about uncertainty.',
        validation_alias='FRED_PERSONALITY_INSTRUCTION', max_length=2000,
    )
    database_url: str = Field(f'sqlite:///{ROOT / "data" / "fred.db"}', validation_alias='DATABASE_URL')
    allowed_origins: list[str] = Field(
        ['http://localhost:5173', 'http://127.0.0.1:5173'], validation_alias='FRED_ALLOWED_ORIGINS'
    )
    secure_cookies: bool = Field(False, validation_alias='FRED_COOKIE_SECURE')
    session_ttl_hours: int = Field(12, ge=1, le=168, validation_alias='FRED_SESSION_TTL_HOURS')
    api_rate_limit_per_minute: int = Field(120, ge=1, validation_alias='FRED_API_RATE_LIMIT')
    chat_rate_limit_per_minute: int = Field(20, ge=1, validation_alias='FRED_CHAT_RATE_LIMIT')
    login_rate_limit_per_minute: int = Field(10, ge=1, validation_alias='FRED_LOGIN_RATE_LIMIT')
    openai_timeout_seconds: float = Field(45, ge=1, le=120, validation_alias='FRED_OPENAI_TIMEOUT')

    memory_enabled: bool = Field(True, validation_alias='FRED_MEMORY_ENABLED')
    voice_enabled: bool = Field(False, validation_alias='FRED_VOICE_ENABLED')
    smart_home_enabled: bool = Field(False, validation_alias='FRED_SMART_HOME_ENABLED')
    remote_control_enabled: bool = Field(False, validation_alias='FRED_REMOTE_CONTROL_ENABLED')
    automations_enabled: bool = Field(False, validation_alias='FRED_AUTOMATIONS_ENABLED')
    voice: VoiceSettings = Field(default_factory=VoiceSettings, validation_alias='FRED_VOICE')
    rooms: tuple[RoomDefinition, ...] = Field((), validation_alias='FRED_ROOMS')
    devices: tuple[DeviceDefinition, ...] = Field((), validation_alias='FRED_DEVICES')

    @field_validator('owner_username', 'owner_name')
    @classmethod
    def reject_blank_names(cls, value: str) -> str:
        if not value.strip():
            raise ValueError('Owner identifiers cannot be blank.')
        return value.strip()

    @field_validator('allowed_origins')
    @classmethod
    def exact_origins(cls, value: list[str]) -> list[str]:
        for origin in value:
            parsed = urlsplit(origin)
            if (parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username
                    or parsed.password or parsed.path or parsed.query or parsed.fragment or '*' in origin):
                raise ValueError('Use exact HTTP(S) origins without paths, credentials, or wildcards.')
            try:
                parsed.port
            except ValueError as exc:
                raise ValueError('Origin port is invalid.') from exc
        return value

    @model_validator(mode='after')
    def validate_device_configuration(self) -> 'Settings':
        DeviceRegistry(self.rooms, self.devices)
        return self

    @property
    def device_registry(self) -> DeviceRegistry:
        return DeviceRegistry(self.rooms, self.devices)

    @property
    def feature_flags(self) -> dict[str, bool]:
        return {
            'memory': self.memory_enabled, 'voice': self.voice_enabled,
            'smart_home': self.smart_home_enabled, 'remote_control': self.remote_control_enabled,
            'automations': self.automations_enabled,
        }

    def validate_startup(self) -> None:
        password = self.owner_password.get_secret_value() if self.owner_password else ''
        if not 12 <= len(password) <= 500 or password == 'CHANGE_ME_TO_A_LONG_RANDOM_PASSWORD':
            raise RuntimeError('Set FRED_OWNER_PASSWORD to a unique password of 12–500 characters in .env. Run scripts/bootstrap.py first.')
        if self.ai_provider == 'openai' and not self.openai_api_key:
            raise RuntimeError('FRED_AI_PROVIDER=openai requires OPENAI_API_KEY. Use mock to run without API credentials.')
        unavailable = [name for name, enabled in self.feature_flags.items() if enabled and name != 'memory']
        if unavailable:
            raise RuntimeError('Unavailable in V1: ' + ', '.join(unavailable) + '. Keep these feature flags disabled; interfaces alone do not install capabilities.')

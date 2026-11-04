from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.ai.personality import CommunicationMode

Category = Literal['personal', 'operational', 'conversation', 'system']


class InputModel(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class LoginInput(InputModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=False)

    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=500)

    @field_validator('username')
    @classmethod
    def normalize_username(cls, value: str) -> str:
        return value.strip()


class ConversationInput(InputModel):
    pass


class ChatInput(InputModel):
    message: str = Field(min_length=1, max_length=8000)
    conversation_id: str | None = Field(None, max_length=36)
    mode: CommunicationMode | None = None


class MemoryInput(InputModel):
    category: Category
    content: str = Field(min_length=1, max_length=4000)


class MemoryPatch(InputModel):
    category: Category | None = None
    content: str | None = Field(None, min_length=1, max_length=4000)


class SettingsInput(InputModel):
    mode: CommunicationMode | None = None
    model: str | None = Field(None, min_length=1, max_length=120, pattern=r'^[a-zA-Z0-9_.:\-]+$')


class UTCOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    @field_validator('created_at', 'updated_at', check_fields=False)
    @classmethod
    def normalize_database_datetime(cls, value: datetime) -> datetime:
        # SQLite drops timezone metadata; all stored application timestamps are UTC.
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


class ConversationOutput(UTCOutput):
    id: str
    title: str
    created_at: datetime


class MessageOutput(UTCOutput):
    id: str
    role: str
    content: str
    created_at: datetime


class MemoryOutput(UTCOutput):
    id: str
    category: str
    content: str
    created_at: datetime
    updated_at: datetime

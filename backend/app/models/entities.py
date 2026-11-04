"""Owner-scoped persistent records. All authorization remains in deterministic services."""
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base


def now() -> datetime:
    return datetime.now(timezone.utc)


def identifier() -> str:
    return str(uuid4())


class User(Base):
    __tablename__ = 'users'
    username: Mapped[str] = mapped_column(String(80), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(80))
    password_hash: Mapped[str] = mapped_column(String(300))
    role: Mapped[str] = mapped_column(String(30), default='owner')


class AuthSession(Base):
    __tablename__ = 'auth_sessions'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_username: Mapped[str] = mapped_column(ForeignKey('users.username', ondelete='CASCADE'), index=True)
    csrf_token: Mapped[str] = mapped_column(String(100))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Conversation(Base):
    __tablename__ = 'conversations'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    owner_username: Mapped[str] = mapped_column(ForeignKey('users.username'), index=True)
    title: Mapped[str] = mapped_column(String(100), default='New conversation')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Message(Base):
    __tablename__ = 'messages'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    conversation_id: Mapped[str] = mapped_column(ForeignKey('conversations.id', ondelete='CASCADE'), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Memory(Base):
    __tablename__ = 'memories'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    owner_username: Mapped[str] = mapped_column(ForeignKey('users.username'), index=True)
    category: Mapped[str] = mapped_column(String(30))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class UserSettings(Base):
    __tablename__ = 'user_settings'
    owner_username: Mapped[str] = mapped_column(ForeignKey('users.username'), primary_key=True)
    mode: Mapped[str] = mapped_column(String(30), default='standard')
    model: Mapped[str] = mapped_column(String(120))


class AuditEntry(Base):
    __tablename__ = 'audit_entries'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    owner_username: Mapped[str | None] = mapped_column(String(80), nullable=True)
    action: Mapped[str] = mapped_column(String(60))
    resource_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    outcome: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


Index('ix_messages_conversation_created', Message.conversation_id, Message.created_at)

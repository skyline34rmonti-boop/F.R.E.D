import asyncio
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query, Request, Response, WebSocket, WebSocketDisconnect
from sqlalchemy import delete, select

from app.api.dependencies import CurrentIdentity, DB
from app.api.schemas import (
    ChatInput, ConversationInput, ConversationOutput, LoginInput, MemoryInput, MemoryOutput,
    MemoryPatch, MessageOutput, SettingsInput,
)
from app.core.logging import audit
from app.core.engine import AssistantError
from app.core.security import COOKIE_NAME, expired, token_hash, verify_password
from app.integrations.registry import INTEGRATIONS
from app.models.entities import AuthSession, Conversation, Memory, Message, User, UserSettings

router = APIRouter(prefix='/api')


def auth_output(user: User, session: AuthSession) -> dict:
    return {'user': {'username': user.username, 'display_name': user.display_name}, 'csrf_token': session.csrf_token}


def owned_conversation(db, owner: str, conversation_id: str) -> Conversation:
    record = db.scalar(select(Conversation).where(Conversation.id == conversation_id, Conversation.owner_username == owner))
    if not record:
        raise HTTPException(404, 'Conversation not found.')
    return record


def owned_memory(db, owner: str, memory_id: str) -> Memory:
    record = db.scalar(select(Memory).where(Memory.id == memory_id, Memory.owner_username == owner))
    if not record:
        raise HTTPException(404, 'Memory not found.')
    return record


def settings_output(record: UserSettings, request: Request) -> dict:
    config = request.app.state.settings
    return {'mode': record.mode, 'model': record.model, 'provider': config.ai_provider, 'owner_name': config.owner_name}


@router.get('/health')
def health(request: Request):
    return {'status': 'ok', 'provider': request.app.state.settings.ai_provider, 'version': '0.1.0'}


@router.get('/ready')
def ready(request: Request, response: Response):
    status = request.app.state.service.readiness()
    if status['status'] != 'ok':
        response.status_code = 503
    return status


@router.post('/auth/login')
async def login(data: LoginInput, request: Request, response: Response, db: DB):
    config = request.app.state.settings
    address = request.client.host if request.client else 'unknown'
    if not request.app.state.limiter.allow(f'login:{address}', config.login_rate_limit_per_minute):
        raise HTTPException(429, 'Too many sign-in attempts. Wait one minute before trying again.', headers={'Retry-After': '60'})
    configured_user = db.get(User, config.owner_username)
    # Verify even for unknown usernames so the configured account cannot be trivially enumerated by timing.
    valid_password = await asyncio.to_thread(verify_password, data.password, configured_user.password_hash)
    if data.username != config.owner_username or not valid_password:
        audit(db, 'auth.login', outcome='denied')
        raise HTTPException(401, 'Incorrect username or password.')
    old_token = request.cookies.get(COOKIE_NAME)
    if old_token:
        db.execute(delete(AuthSession).where(AuthSession.token_hash == token_hash(old_token)))
    db.execute(delete(AuthSession).where(AuthSession.expires_at <= datetime.now(timezone.utc)))
    raw_token = secrets.token_urlsafe(48)
    session = AuthSession(token_hash=token_hash(raw_token), owner_username=configured_user.username,
                          csrf_token=secrets.token_urlsafe(32),
                          expires_at=datetime.now(timezone.utc) + timedelta(hours=config.session_ttl_hours))
    db.add(session)
    db.commit()
    response.set_cookie(COOKIE_NAME, raw_token, httponly=True, secure=config.secure_cookies,
                        samesite='strict', max_age=config.session_ttl_hours * 3600, path='/api')
    audit(db, 'auth.login', configured_user.username)
    return auth_output(configured_user, session)


@router.get('/auth/me')
def me(identity: CurrentIdentity):
    return {'user': {'username': identity.username, 'display_name': identity.display_name}, 'csrf_token': identity.csrf_token}


@router.post('/auth/logout', status_code=204)
def logout(request: Request, response: Response, db: DB, identity: CurrentIdentity):
    db.execute(delete(AuthSession).where(AuthSession.token_hash == identity.token_hash))
    audit(db, 'auth.logout', identity.username)
    response.delete_cookie(COOKIE_NAME, path='/api', secure=request.app.state.settings.secure_cookies,
                           httponly=True, samesite='strict')


@router.get('/conversations', response_model=list[ConversationOutput])
def list_conversations(db: DB, identity: CurrentIdentity):
    return list(db.scalars(select(Conversation).where(Conversation.owner_username == identity.username)
                           .order_by(Conversation.created_at.desc())))


@router.post('/conversations', response_model=ConversationOutput, status_code=201)
def create_conversation(data: ConversationInput, db: DB, identity: CurrentIdentity):
    record = Conversation(owner_username=identity.username)
    db.add(record)
    db.commit()
    audit(db, 'conversation.create', identity.username, record.id)
    return record


@router.get('/conversations/{conversation_id}/messages', response_model=list[MessageOutput])
def messages(conversation_id: str, db: DB, identity: CurrentIdentity):
    owned_conversation(db, identity.username, conversation_id)
    return list(db.scalars(select(Message).where(Message.conversation_id == conversation_id)
                           .order_by(Message.created_at, Message.id)))


@router.delete('/conversations/{conversation_id}', status_code=204)
def delete_conversation(conversation_id: str, db: DB, identity: CurrentIdentity):
    db.delete(owned_conversation(db, identity.username, conversation_id))
    audit(db, 'conversation.delete', identity.username, conversation_id)


@router.post('/chat')
async def chat(data: ChatInput, request: Request, db: DB, identity: CurrentIdentity):
    config = request.app.state.settings
    if not request.app.state.limiter.allow(f'chat:{identity.username}', config.chat_rate_limit_per_minute):
        raise HTTPException(429, 'Conversation rate limit reached. Wait one minute and try again.', headers={'Retry-After': '60'})
    try:
        return await request.app.state.assistant.respond(
            identity.username, data.message, data.conversation_id, data.mode,
            provider=request.app.state.ai_provider,
        )
    except AssistantError as exc:
        raise HTTPException(exc.status_code, exc.detail) from exc


@router.get('/memories', response_model=list[MemoryOutput])
def list_memories(db: DB, identity: CurrentIdentity, q: str = Query('', max_length=200)):
    statement = select(Memory).where(Memory.owner_username == identity.username)
    if q.strip():
        statement = statement.where(Memory.content.icontains(q.strip(), autoescape=True))
    return list(db.scalars(statement.order_by(Memory.updated_at.desc())))


@router.get('/memories/export')
def export_memories(db: DB, identity: CurrentIdentity):
    records = list(db.scalars(select(Memory).where(Memory.owner_username == identity.username)
                             .order_by(Memory.created_at)))
    audit(db, 'memory.export', identity.username)
    return {'version': '0.1', 'exported_at': datetime.now(timezone.utc).isoformat(),
            'memories': [MemoryOutput.model_validate(record).model_dump(mode='json') for record in records]}


@router.post('/memories', response_model=MemoryOutput, status_code=201)
def create_memory(data: MemoryInput, db: DB, identity: CurrentIdentity):
    record = Memory(owner_username=identity.username, **data.model_dump())
    db.add(record)
    db.commit()
    audit(db, 'memory.create', identity.username, record.id)
    return record


@router.patch('/memories/{memory_id}', response_model=MemoryOutput)
def update_memory(memory_id: str, data: MemoryPatch, db: DB, identity: CurrentIdentity):
    record = owned_memory(db, identity.username, memory_id)
    updates = data.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(422, 'Supply a category or content to update.')
    for key, value in updates.items():
        setattr(record, key, value)
    db.commit()
    audit(db, 'memory.update', identity.username, record.id)
    return record


@router.delete('/memories/{memory_id}', status_code=204)
def delete_memory(memory_id: str, db: DB, identity: CurrentIdentity):
    db.delete(owned_memory(db, identity.username, memory_id))
    audit(db, 'memory.delete', identity.username, memory_id)


@router.get('/settings')
def get_settings(request: Request, db: DB, identity: CurrentIdentity):
    return settings_output(db.get(UserSettings, identity.username), request)


@router.put('/settings')
def update_settings(data: SettingsInput, request: Request, db: DB, identity: CurrentIdentity):
    prefs = db.get(UserSettings, identity.username)
    for key, value in data.model_dump(exclude_none=True).items():
        setattr(prefs, key, value)
    audit(db, 'settings.update', identity.username)
    return settings_output(prefs, request)


@router.get('/system')
def system(request: Request, db: DB, identity: CurrentIdentity):
    prefs = db.get(UserSettings, identity.username)
    config = request.app.state.settings
    return {'provider': request.app.state.settings.ai_provider, 'model': prefs.model,
            'database': request.app.state.service.readiness()['database'], 'integrations': INTEGRATIONS,
            'features': config.feature_flags,
            'devices': [config.device_registry.status(device.id) for device in config.devices]}


@router.websocket('/ws')
async def websocket(socket: WebSocket):
    app = socket.app
    origin = socket.headers.get('origin')
    if not origin or origin not in app.state.settings.allowed_origins:
        await socket.close(code=1008, reason='Origin not authorized.')
        return
    raw_token = socket.cookies.get(COOKIE_NAME)
    hashed = token_hash(raw_token) if raw_token else ''
    with app.state.session_factory() as db:
        session = db.get(AuthSession, hashed)
        user = db.get(User, session.owner_username) if session else None
        if not session or expired(session.expires_at) or session.owner_username != app.state.settings.owner_username or not user or user.role != 'owner':
            await socket.close(code=1008, reason='Authentication required.')
            return
        owner = session.owner_username
    await socket.accept()
    hub = app.state.events
    hub.connect(owner, socket)
    try:
        await socket.send_json(hub.statuses.get(owner, {'type': 'status', 'status': 'idle'}))
        while True:
            try:
                message = await asyncio.wait_for(socket.receive_text(), timeout=20)
                if len(message) > 1024:
                    await socket.close(code=1009, reason='Message too large.')
                    break
            except asyncio.TimeoutError:
                pass
            with app.state.session_factory() as db:
                session = db.get(AuthSession, hashed)
                user = db.get(User, session.owner_username) if session else None
                if not session or expired(session.expires_at) or not user or user.role != 'owner':
                    await socket.close(code=1008, reason='Session expired.')
                    break
    except WebSocketDisconnect:
        pass
    finally:
        hub.disconnect(owner, socket)

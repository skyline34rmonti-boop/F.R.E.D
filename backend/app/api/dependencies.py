import hmac
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.security import COOKIE_NAME, expired, token_hash
from app.models.entities import AuthSession, User


def get_db(request: Request):
    with request.app.state.session_factory() as db:
        yield db


DB = Annotated[Session, Depends(get_db)]


@dataclass
class Identity:
    username: str
    display_name: str
    csrf_token: str
    token_hash: str
    role: str


def current_identity(request: Request, db: DB) -> Identity:
    token = request.cookies.get(COOKIE_NAME)
    session = db.get(AuthSession, token_hash(token)) if token else None
    if not session or expired(session.expires_at):
        raise HTTPException(401, 'Your session has expired or is missing. Sign in to FRED.')
    owner = db.get(User, session.owner_username)
    if not owner or owner.username != request.app.state.settings.owner_username or owner.role != 'owner':
        raise HTTPException(403, 'This account is not authorized for this workspace.')
    if request.method in {'POST', 'PUT', 'PATCH', 'DELETE'}:
        csrf = request.headers.get('X-CSRF-Token', '')
        if not hmac.compare_digest(csrf.encode(), session.csrf_token.encode()):
            raise HTTPException(403, 'Invalid request token. Refresh FRED and try again.')
    return Identity(owner.username, owner.display_name, session.csrf_token, session.token_hash, owner.role)


CurrentIdentity = Annotated[Identity, Depends(current_identity)]

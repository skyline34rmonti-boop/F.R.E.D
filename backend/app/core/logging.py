import json
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.entities import AuditEntry

logger = logging.getLogger('fred.audit')


def operational_event(event: str, *, level: int = logging.INFO, **fields: str) -> None:
    """Callers supply only fixed metadata, never exception text or request bodies."""
    logging.getLogger('fred.service').log(level, json.dumps({
        'timestamp': datetime.now(timezone.utc).isoformat(), 'event': event, **fields,
    }))


def audit(db: Session, action: str, owner: str | None = None, resource_id: str | None = None, outcome: str = 'success') -> None:
    """Never log message text, credentials, memory contents or provider responses."""
    db.add(AuditEntry(action=action, owner_username=owner, resource_id=resource_id, outcome=outcome))
    db.commit()
    logger.info(json.dumps({'timestamp': datetime.now(timezone.utc).isoformat(), 'event': action,
                            'owner': owner, 'resource_id': resource_id, 'outcome': outcome}))

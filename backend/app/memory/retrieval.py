import re

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.entities import Memory

STOP_WORDS = {'the', 'and', 'that', 'with', 'this', 'from', 'have', 'what', 'fred', 'please', 'about', 'your', 'would'}


def relevant_memories(db: Session, owner: str, query: str, limit: int = 5) -> list[Memory]:
    """Bounded lexical retrieval; no wholesale database or automatic personal-data extraction."""
    terms = list(dict.fromkeys(term for term in re.findall(r'\w{3,}', query.lower()) if term not in STOP_WORDS))[:12]
    if not terms:
        return []
    candidates = list(db.scalars(
        select(Memory).where(Memory.owner_username == owner,
                             or_(*(Memory.content.icontains(term, autoescape=True) for term in terms)))
        .order_by(Memory.updated_at.desc()).limit(50)
    ))
    candidates.sort(key=lambda record: sum(term in record.content.lower() for term in terms), reverse=True)
    return candidates[:limit]

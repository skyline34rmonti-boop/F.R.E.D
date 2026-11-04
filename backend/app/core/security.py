import hashlib
import hmac
import secrets
from datetime import datetime, timezone

ITERATIONS = 600_000
COOKIE_NAME = 'fred_session'


def password_hash(password: str) -> str:
    salt = secrets.token_hex(16)
    value = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), ITERATIONS).hex()
    return f'pbkdf2_sha256${ITERATIONS}${salt}${value}'


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt, expected = encoded.split('$')
        if algorithm != 'pbkdf2_sha256':
            return False
        value = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), int(iterations)).hex()
        return hmac.compare_digest(value, expected)
    except (ValueError, TypeError):
        return False


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def expired(value: datetime) -> bool:
    return value.replace(tzinfo=value.tzinfo or timezone.utc) <= datetime.now(timezone.utc)

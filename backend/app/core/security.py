"""Password hashing, JWT access tokens and password-reset token helpers.

bcrypt is used directly (no passlib shim) so the cost factor and the 72-byte
input limit are handled explicitly. Reset tokens are stored only as SHA-256
hashes, so a database dump cannot be replayed against the reset endpoint.
"""
import base64
import hashlib
import logging
import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

import bcrypt
import jwt

from app.core.config import settings

logger = logging.getLogger(__name__)

BCRYPT_ROUNDS = 12
BCRYPT_MAX_BYTES = 72


def _prepare(password: str) -> bytes:
    """Pre-hash so bcrypt's 72-byte input limit cannot silently truncate a password.

    SHA-256 digest -> base64 gives a fixed 44-byte input that still differs for
    every distinct password, however long the original was.
    """
    digest = hashlib.sha256((password or "").encode("utf-8")).digest()
    return base64.b64encode(digest)[:BCRYPT_MAX_BYTES]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_prepare(password), bcrypt.gensalt(rounds=BCRYPT_ROUNDS)).decode()


def verify_password(password: str, password_hash: Optional[str]) -> bool:
    if not password or not password_hash:
        return False
    try:
        return bcrypt.checkpw(_prepare(password), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(
    subject: str,
    role: str,
    user_id: int,
    expires_minutes: Optional[int] = None,
) -> str:
    now = datetime.now(timezone.utc)
    minutes = expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES
    payload: Dict[str, Any] = {
        "sub": str(subject),
        "uid": user_id,
        "role": role,
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=minutes)).timestamp()),
        "jti": secrets.token_hex(8),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Return the payload, or None when the token is missing, invalid or expired."""
    if not token:
        return None
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
    except jwt.PyJWTError as exc:
        logger.debug("Rejected token: %s", exc)
        return None
    if payload.get("type") != "access":
        return None
    return payload


def generate_reset_token() -> Tuple[str, str]:
    """Return (token_for_the_email, hash_for_the_database)."""
    raw = secrets.token_urlsafe(48)
    return raw, hash_token(raw)


def hash_token(raw: str) -> str:
    return hashlib.sha256((raw or "").encode("utf-8")).hexdigest()


def generate_initial_password(length: int = 12) -> str:
    """A readable-but-random first password for a newly created account."""
    alphabet = string.ascii_letters + string.digits
    while True:
        candidate = "".join(secrets.choice(alphabet) for _ in range(length - 2))
        candidate = f"Rg{candidate}"
        if any(c.isdigit() for c in candidate) and any(c.islower() for c in candidate):
            return candidate


def password_strength_error(password: str) -> Optional[str]:
    if len(password or "") < 8:
        return "Password must be at least 8 characters long."
    if not any(c.isalpha() for c in password):
        return "Password must contain at least one letter."
    if not any(c.isdigit() for c in password):
        return "Password must contain at least one number."
    return None

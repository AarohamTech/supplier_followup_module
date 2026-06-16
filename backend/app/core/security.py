"""Password hashing (bcrypt) and JWT encode/decode.

Pure functions — no FastAPI, no DB. Used by `core.deps` and the auth router.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from jose import JWTError, jwt

from .config import settings


# ── Passwords ────────────────────────────────────────────────────────────────
# We use the `bcrypt` library directly (passlib 1.7.x is incompatible with
# bcrypt 5.x on modern Python). bcrypt hashes at most 72 bytes, so we truncate
# the UTF-8 encoding explicitly to stay within that limit.
def _to_bytes(plain: str) -> bytes:
    return plain.encode("utf-8")[:72]


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(_to_bytes(plain), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(_to_bytes(plain), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        # Malformed/empty stored hash.
        return False


# ── JWT ──────────────────────────────────────────────────────────────────────
class TokenError(Exception):
    """Raised when a token is missing, expired, or fails verification."""


def create_access_token(
    *,
    subject: str | int,
    role: str,
    email: str | None = None,
    expires_minutes: int | None = None,
    extra: dict[str, Any] | None = None,
) -> str:
    now = datetime.now(timezone.utc)
    minutes = expires_minutes if expires_minutes is not None else settings.ACCESS_TOKEN_EXPIRE_MINUTES
    payload: dict[str, Any] = {
        "sub": str(subject),
        "role": role,
        "iat": int(now.timestamp()),
        "exp": now + timedelta(minutes=minutes),
    }
    if email:
        payload["email"] = email
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except JWTError as exc:  # expired, bad signature, malformed, etc.
        raise TokenError(str(exc)) from exc

"""Symmetric encryption for secrets stored at rest (e.g. mail passwords).

Uses Fernet (AES-128-CBC + HMAC) with a key deterministically derived from the
app's ``JWT_SECRET`` — so there is no extra key to manage or rotate, and no new
dependency (``cryptography`` is already present via ``python-jose[cryptography]``).

Rotating ``JWT_SECRET`` invalidates previously-encrypted values; the admin simply
re-enters affected mail passwords. Stored values carry an ``enc:v1:`` prefix so we
can detect — and gracefully pass through — any legacy/plaintext value.
"""
from __future__ import annotations

import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken

from .config import settings

log = logging.getLogger(__name__)

_PREFIX = "enc:v1:"


def _fernet() -> Fernet:
    digest = hashlib.sha256((settings.JWT_SECRET or "").encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt(plaintext: str | None) -> str:
    """Encrypt a secret for storage. Empty/None → empty string."""
    if not plaintext:
        return ""
    token = _fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")
    return _PREFIX + token


def decrypt(stored: str | None) -> str:
    """Decrypt a stored secret. Tolerates empty and legacy plaintext values."""
    if not stored:
        return ""
    if not stored.startswith(_PREFIX):
        # Value written before encryption existed (or a plaintext import) — pass through.
        return stored
    token = stored[len(_PREFIX):]
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        log.warning("Failed to decrypt a stored secret (JWT_SECRET rotated?); returning empty")
        return ""


def is_encrypted(stored: str | None) -> bool:
    return bool(stored) and stored.startswith(_PREFIX)

"""User-uploaded file attachments on communication messages, stored in S3.

Flow: a file is uploaded first (an unbound `MessageAttachment` row + the bytes
in the private bucket), then bound to the `communication_messages` row when the
chat message / hub reply is actually sent. Downloads are proxied through the
scoped routers (staff / employee / supplier) — the bucket is never public and
no presigned URLs leave the backend.

Disabled until the S3_* settings are configured; every caller should check
`storage_enabled()` and surface `disabled_reason()` to the user.
"""
from __future__ import annotations

import logging
import re
import threading
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.config import settings
from ..models.message_attachment import MessageAttachment

log = logging.getLogger(__name__)

_lock = threading.Lock()
_client_cache: dict[str, Any] = {}

_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._ ()\-]+")


def storage_enabled() -> bool:
    return bool(settings.S3_BUCKET and settings.S3_ACCESS_KEY_ID and settings.S3_SECRET_ACCESS_KEY)


def disabled_reason() -> str:
    return "File attachments are not configured yet (S3 bucket/keys missing)."


def _client():
    """Cached boto3 S3 client (lazy import so the app runs without boto3 until
    the feature is actually configured and used)."""
    key = f"{settings.S3_ENDPOINT_URL}|{settings.S3_REGION}|{settings.S3_ACCESS_KEY_ID}"
    with _lock:
        client = _client_cache.get(key)
        if client is None:
            import boto3

            client = boto3.client(
                "s3",
                region_name=settings.S3_REGION or None,
                endpoint_url=settings.S3_ENDPOINT_URL or None,
                aws_access_key_id=settings.S3_ACCESS_KEY_ID,
                aws_secret_access_key=settings.S3_SECRET_ACCESS_KEY,
            )
            _client_cache.clear()
            _client_cache[key] = client
        return client


def safe_filename(name: str | None) -> str:
    base = (name or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    base = _SAFE_NAME_RE.sub("_", base)
    return base[:200] or "file"


def max_bytes() -> int:
    return int(settings.ATTACHMENT_MAX_MB or 15) * 1024 * 1024


def save_upload(
    db: Session,
    *,
    data: bytes,
    filename: str | None,
    content_type: str | None,
    uploaded_by_kind: str,
    uploaded_by_id: int | None,
    uploaded_by_label: str | None = None,
    supplier_id: int | None = None,
    commit: bool = True,
) -> MessageAttachment:
    """Store the bytes in the bucket and create an unbound attachment row.

    Raises ValueError with a user-presentable message on validation problems —
    the routers turn that into a 4xx.
    """
    if not storage_enabled():
        raise ValueError(disabled_reason())
    if not data:
        raise ValueError("The file is empty.")
    if len(data) > max_bytes():
        raise ValueError(f"File too large (max {settings.ATTACHMENT_MAX_MB} MB).")

    name = safe_filename(filename)
    key = f"{settings.S3_KEY_PREFIX or ''}{uuid4().hex}/{name}"
    _client().put_object(
        Bucket=settings.S3_BUCKET,
        Key=key,
        Body=data,
        ContentType=content_type or "application/octet-stream",
    )
    att = MessageAttachment(
        filename=name,
        content_type=content_type or "application/octet-stream",
        size_bytes=len(data),
        storage_key=key,
        uploaded_by_kind=uploaded_by_kind,
        uploaded_by_id=uploaded_by_id,
        uploaded_by_label=(uploaded_by_label or "")[:128] or None,
        supplier_id=supplier_id,
    )
    db.add(att)
    if commit:
        db.commit()
        db.refresh(att)
    else:
        db.flush()
    return att


def bind(
    db: Session,
    message_id: int,
    attachment_ids: list[int] | None,
    *,
    expect_kind: str | None = None,
    expect_uploader_id: int | None = None,
    commit: bool = True,
) -> list[MessageAttachment]:
    """Attach previously-uploaded (unbound) files to a message. Silently skips
    ids that don't exist, are already bound, or fail the uploader expectation —
    a stale client can never steal or re-send someone else's file."""
    if not attachment_ids:
        return []
    stmt = select(MessageAttachment).where(
        MessageAttachment.id.in_(attachment_ids),
        MessageAttachment.message_id.is_(None),
    )
    if expect_kind:
        stmt = stmt.where(MessageAttachment.uploaded_by_kind == expect_kind)
    if expect_uploader_id is not None:
        stmt = stmt.where(MessageAttachment.uploaded_by_id == expect_uploader_id)
    rows = list(db.scalars(stmt).all())
    for att in rows:
        att.message_id = message_id
    if rows and commit:
        db.commit()
    return rows


def get_bytes(att: MessageAttachment) -> bytes:
    obj = _client().get_object(Bucket=settings.S3_BUCKET, Key=att.storage_key)
    return obj["Body"].read()


def out(att: MessageAttachment) -> dict[str, Any]:
    return {
        "id": att.id,
        "filename": att.filename,
        "content_type": att.content_type,
        "size_bytes": att.size_bytes,
    }


def for_messages(db: Session, message_ids: list[int]) -> dict[int, list[dict[str, Any]]]:
    """Batch-load attachment metadata for a set of messages: {message_id: [out]}."""
    if not message_ids:
        return {}
    rows = db.scalars(
        select(MessageAttachment)
        .where(MessageAttachment.message_id.in_(message_ids))
        .order_by(MessageAttachment.id.asc())
    ).all()
    by_msg: dict[int, list[dict[str, Any]]] = {}
    for att in rows:
        by_msg.setdefault(att.message_id, []).append(out(att))
    return by_msg


def load_for_email(db: Session, message_id: int) -> list[tuple[str, str, bytes]]:
    """(filename, content_type, bytes) for every attachment on a message — used
    by the SMTP send worker to attach the files to the outgoing email."""
    rows = db.scalars(
        select(MessageAttachment)
        .where(MessageAttachment.message_id == message_id)
        .order_by(MessageAttachment.id.asc())
    ).all()
    return [
        (att.filename, att.content_type or "application/octet-stream", get_bytes(att))
        for att in rows
    ]

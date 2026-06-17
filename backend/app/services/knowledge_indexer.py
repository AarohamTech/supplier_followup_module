"""Indexes domain records into the pgvector knowledge store.

This is the bridge between the live tables (customer mails, replies, supplier
reply messages) and the semantic memory the agent searches. Everything here is
best-effort and gated on `RAG_ENABLED` + a working vector store — if either is
off, every function is a cheap no-op so callers never have to guard.

Source types stored in `knowledge_chunks.source_type`:
  - "customer_mail"   → an inbound customer/general mail
  - "supplier_reply"  → an inbound supplier reply (CommunicationMessage)
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.communication_message import CommunicationMessage
from ..models.customer_mail import CustomerMail
from . import embeddings_service, vector_store

log = logging.getLogger(__name__)

# nv-embedqa-e5-v5 caps around 512 tokens; keep chunks comfortably under that.
_CHUNK_CHARS = 1400
_MAX_CHUNKS = 6


def enabled() -> bool:
    return embeddings_service.is_enabled() and vector_store.available()


def _chunk(text: str) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= _CHUNK_CHARS:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text) and len(chunks) < _MAX_CHUNKS:
        end = start + _CHUNK_CHARS
        # Prefer to break on a newline/space near the boundary.
        slice_ = text[start:end]
        if end < len(text):
            cut = max(slice_.rfind("\n"), slice_.rfind(". "), slice_.rfind(" "))
            if cut > _CHUNK_CHARS // 2:
                slice_ = slice_[: cut + 1]
                end = start + len(slice_)
        chunks.append(slice_.strip())
        start = end
    return [c for c in chunks if c]


def _embed_and_store(
    db: Session,
    *,
    source_type: str,
    source_id: int,
    header: str,
    body: str,
    metadata: dict[str, Any],
) -> int:
    chunks = _chunk(f"{header}\n\n{body}".strip())
    if not chunks:
        return 0
    try:
        vectors = embeddings_service.embed_documents(chunks)
    except Exception:  # noqa: BLE001
        log.exception("embed failed for %s#%s", source_type, source_id)
        return 0
    if len(vectors) != len(chunks):
        return 0
    return vector_store.upsert(
        db,
        source_type=source_type,
        source_id=source_id,
        chunks=chunks,
        embeddings=vectors,
        metadata=metadata,
    )


def index_customer_mail(db: Session, mail: CustomerMail) -> int:
    if not enabled() or mail is None:
        return 0
    header = (
        f"Customer mail from {mail.from_name or mail.from_email or 'unknown'} "
        f"| subject: {mail.subject or '(none)'} "
        f"| PO: {mail.linked_supplier_po_no or '-'}"
    )
    return _embed_and_store(
        db,
        source_type="customer_mail",
        source_id=mail.id,
        header=header,
        body=mail.body or "",
        metadata={
            "subject": mail.subject,
            "from_email": mail.from_email,
            "customer_name": mail.customer_name,
            "supplier_po_no": mail.linked_supplier_po_no,
            "received_at": mail.received_at.isoformat() if mail.received_at else None,
            "mail_type": mail.mail_type,
        },
    )


def index_supplier_reply(db: Session, msg: CommunicationMessage) -> int:
    if not enabled() or msg is None or msg.direction != "INCOMING":
        return 0
    header = (
        f"Supplier reply from {msg.supplier_name or msg.sender_email or 'unknown'} "
        f"| subject: {msg.subject or '(none)'} "
        f"| PO: {msg.supplier_po_no or '-'} "
        f"| parsed status: {msg.parsed_status or '-'}"
    )
    return _embed_and_store(
        db,
        source_type="supplier_reply",
        source_id=msg.id,
        header=header,
        body=msg.body or "",
        metadata={
            "subject": msg.subject,
            "supplier_name": msg.supplier_name,
            "supplier_po_no": msg.supplier_po_no,
            "parsed_status": msg.parsed_status,
            "received_at": msg.received_at.isoformat() if msg.received_at else None,
        },
    )


def backfill(db: Session, *, limit: int = 500) -> dict[str, Any]:
    """Embed existing customer mails + supplier replies not yet in the store."""
    if not enabled():
        return {"enabled": False, "indexed": 0, "skipped": 0}

    indexed = 0
    skipped = 0

    done_mail = vector_store.indexed_source_ids(db, "customer_mail")
    mails = db.scalars(
        select(CustomerMail).order_by(CustomerMail.id.desc()).limit(limit)
    ).all()
    for mail in mails:
        if mail.id in done_mail:
            skipped += 1
            continue
        if index_customer_mail(db, mail):
            indexed += 1

    done_reply = vector_store.indexed_source_ids(db, "supplier_reply")
    replies = db.scalars(
        select(CommunicationMessage)
        .where(CommunicationMessage.direction == "INCOMING")
        .order_by(CommunicationMessage.id.desc())
        .limit(limit)
    ).all()
    for msg in replies:
        if msg.id in done_reply:
            skipped += 1
            continue
        if index_supplier_reply(db, msg):
            indexed += 1

    return {"enabled": True, "indexed": indexed, "skipped": skipped}

"""Supplier Inbox: incoming supplier correspondence surfaced as a flat list.

A message belongs to the supplier inbox when it is INCOMING and either tagged
`is_supplier_inbox` (matched supplier OR a configured supplier sender domain at
ingestion) or its sender address is on a configured supplier domain (covers
historical rows ingested before the tag existed).
"""
from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..core.config import settings
from ..models.communication_message import CommunicationMessage as CM


def _supplier_clause():
    conds = [CM.is_supplier_inbox.is_(True)]
    for d in settings.supplier_mail_domains:
        conds.append(CM.sender_email.ilike(f"%@{d}"))
    return or_(*conds)


def list_supplier_inbox(
    db: Session, *, search: str | None = None, limit: int = 100, offset: int = 0
) -> tuple[list[CM], int]:
    supplier_clause = _supplier_clause()
    stmt = select(CM).where(CM.direction == "INCOMING", supplier_clause)
    count_stmt = select(func.count(CM.id)).where(CM.direction == "INCOMING", supplier_clause)
    if search:
        like = f"%{search}%"
        clause = or_(
            CM.subject.ilike(like),
            CM.sender_email.ilike(like),
            CM.supplier_name.ilike(like),
            CM.supplier_po_no.ilike(like),
        )
        stmt = stmt.where(clause)
        count_stmt = count_stmt.where(clause)

    total = int(db.scalar(count_stmt) or 0)
    rows = list(
        db.scalars(
            stmt.order_by(CM.received_at.desc().nullslast(), CM.id.desc())
            .offset(offset)
            .limit(limit)
        ).all()
    )
    return rows, total


def get_message(db: Session, message_id: int) -> CM | None:
    row = db.get(CM, message_id)
    if row is None or row.direction != "INCOMING":
        return None
    return row

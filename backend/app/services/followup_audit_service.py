"""Record + read PO follow-up attempts. Pure service layer (no FastAPI).

`record()` is best-effort: a logging failure must never break the follow-up it
is auditing, so callers can use `record_safe()` which swallows errors.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.followup_attempt import FollowupAttempt

log = logging.getLogger(__name__)


def record(
    db: Session,
    *,
    supplier_po_no: Optional[str],
    supplier_name: Optional[str],
    signal: Optional[str],
    mail_type: Optional[str] = None,
    source: str = "auto",
    outcome: str = "QUEUED",
    detail: Optional[str] = None,
    ai_used: bool = False,
    ai_error: Optional[str] = None,
    history_id: Optional[int] = None,
    message_id: Optional[int] = None,
    commit: bool = False,
) -> FollowupAttempt:
    row = FollowupAttempt(
        supplier_po_no=supplier_po_no,
        supplier_name=supplier_name,
        signal=(signal or None),
        mail_type=mail_type,
        source=source,
        outcome=outcome,
        detail=detail,
        ai_used=ai_used,
        ai_error=ai_error,
        history_id=history_id,
        message_id=message_id,
    )
    db.add(row)
    if commit:
        db.commit()
        db.refresh(row)
    else:
        db.flush()
    return row


def record_safe(db: Session, **kwargs) -> None:
    """Record without ever raising (the audited action must not fail on logging)."""
    try:
        record(db, **kwargs)
    except Exception:  # noqa: BLE001
        log.exception("Follow-up audit record failed (ignored)")


def list_attempts(
    db: Session,
    *,
    signal: Optional[str] = None,
    outcome: Optional[str] = None,
    supplier_po_no: Optional[str] = None,
    source: Optional[str] = None,
    limit: int = 100,
) -> list[FollowupAttempt]:
    stmt = select(FollowupAttempt)
    if signal:
        stmt = stmt.where(FollowupAttempt.signal == signal.upper())
    if outcome:
        stmt = stmt.where(FollowupAttempt.outcome == outcome.upper())
    if supplier_po_no:
        stmt = stmt.where(FollowupAttempt.supplier_po_no == supplier_po_no)
    if source:
        stmt = stmt.where(FollowupAttempt.source == source)
    stmt = stmt.order_by(FollowupAttempt.created_at.desc()).limit(max(1, min(limit, 500)))
    return list(db.scalars(stmt).all())

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.deps import require_manager
from ..database import get_db
from ..models.mail_history import MailHistory
from ..models.procurement import ProcurementRecord
from ..schemas.mail_history import MailHistoryOut, MailHistoryStatusUpdate
from ..services.followup_engine import apply_followup_logic

router = APIRouter(prefix="/api/mail-history", tags=["mail-history"])

MAIL_HISTORY_STATUSES = {"DRAFT", "READY", "FAILED", "SENT", "COPIED", "MAILTO_OPENED", "SENT_MANUALLY"}


def _target_procurement_rows(db: Session, row: MailHistory) -> list[ProcurementRecord]:
    is_po_mail = (row.material_name or "").strip().upper().startswith("ALL MATERIALS") or (
        row.mail_type or ""
    ).strip().upper().startswith("PO_")
    if is_po_mail and row.supplier_po_no:
        stmt = select(ProcurementRecord).where(
            ProcurementRecord.supplier_po_no == row.supplier_po_no
        )
        if row.supplier_name:
            stmt = stmt.where(
                func.upper(ProcurementRecord.supplier_name)
                == row.supplier_name.strip().upper()
            )
        rows = list(db.scalars(stmt).all())
        if rows:
            return rows

    rec = db.get(ProcurementRecord, row.procurement_record_id)
    return [rec] if rec else []


@router.get("", response_model=list[MailHistoryOut])
def list_history(
    db: Session = Depends(get_db),
    supplier: Optional[str] = None,
    po_no: Optional[str] = None,
    supplier_po_no: Optional[str] = None,
    subject: Optional[str] = None,
    mail_type: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(200, ge=1, le=1000),
):
    stmt = select(MailHistory)
    if supplier:
        stmt = stmt.where(MailHistory.supplier_name.ilike(f"%{supplier}%"))
    po_filter = supplier_po_no or po_no
    if po_filter:
        stmt = stmt.where(MailHistory.supplier_po_no.ilike(f"%{po_filter}%"))
    if subject:
        stmt = stmt.where(MailHistory.subject.ilike(f"%{subject}%"))
    if mail_type:
        stmt = stmt.where(MailHistory.mail_type == mail_type)
    if status:
        stmt = stmt.where(MailHistory.sent_status == status)
    return db.scalars(stmt.order_by(MailHistory.created_at.desc()).limit(limit)).all()


@router.get("/by-record/{record_id}", response_model=list[MailHistoryOut])
def by_record(record_id: int, db: Session = Depends(get_db)):
    return db.scalars(
        select(MailHistory)
        .where(MailHistory.procurement_record_id == record_id)
        .order_by(MailHistory.created_at.desc())
    ).all()


@router.get("/by-subject", response_model=list[MailHistoryOut])
def by_subject(subject: str, db: Session = Depends(get_db)):
    return db.scalars(
        select(MailHistory)
        .where(MailHistory.subject.ilike(f"%{subject}%"))
        .order_by(MailHistory.created_at.desc())
    ).all()


@router.get("/{history_id}", response_model=MailHistoryOut)
def get_history(history_id: int, db: Session = Depends(get_db)):
    row = db.get(MailHistory, history_id)
    if not row:
        raise HTTPException(404, "Mail history not found")
    return row


@router.put("/{history_id}/status", response_model=MailHistoryOut, dependencies=[Depends(require_manager)])
def update_history_status(
    history_id: int,
    payload: MailHistoryStatusUpdate,
    db: Session = Depends(get_db),
):
    status = payload.sent_status.upper()
    if status not in MAIL_HISTORY_STATUSES:
        raise HTTPException(422, f"Status must be one of: {', '.join(sorted(MAIL_HISTORY_STATUSES))}")

    row = db.get(MailHistory, history_id)
    if not row:
        raise HTTPException(404, "Mail history not found")

    old_status = row.sent_status
    row.sent_status = status
    if payload.remarks is not None:
        row.remarks = payload.remarks

    if status == "SENT_MANUALLY" and old_status != "SENT_MANUALLY":
        row.sent_at = row.sent_at or datetime.utcnow()

    for rec in _target_procurement_rows(db, row):
        apply_followup_logic(rec)
        rec.mail_status = status
        if status == "SENT_MANUALLY":
            rec.last_followup_date = row.sent_at
            # Don't double-count if the worker already marked this mail SENT.
            if (old_status or "").upper() not in {"SENT", "SENT_MANUALLY"}:
                rec.followup_count = (rec.followup_count or 0) + 1

    db.commit()
    db.refresh(row)
    return row

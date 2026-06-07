"""PO-wise follow-up read APIs.

These endpoints surface procurement_records grouped by (supplier_name,
supplier_po_no). They do not mutate procurement state.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..services import po_followup_mail_service, po_followup_service

router = APIRouter(prefix="/api/po-followups", tags=["po-followups"])


@router.get("/groups")
def list_groups(
    signal: Optional[str] = Query(None),
    supplier_name: Optional[str] = Query(None),
    supplier_po_no: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(25, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return po_followup_service.list_po_groups(
        db,
        signal=signal,
        supplier_name=supplier_name,
        supplier_po_no=supplier_po_no,
        search=search,
        page=page,
        size=size,
    )


@router.get("/groups/by-key")
def group_by_key(
    supplier_name: str = Query(...),
    supplier_po_no: str = Query(...),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    group = po_followup_service.get_po_group(db, supplier_name, supplier_po_no)
    if not group:
        raise HTTPException(404, "PO group not found")
    return group


@router.get("/commitments")
def list_commitments(
    supplier_po_no: Optional[str] = Query(None),
    supplier_name: Optional[str] = Query(None),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    return po_followup_service.list_commitments(
        db, supplier_po_no=supplier_po_no, supplier_name=supplier_name
    )


@router.post("/auto-queue/test")
def test_auto_queue(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Preview automatic PO follow-up mails without creating queued messages."""
    return po_followup_mail_service.queue_due_po_followups(db, limit=limit, dry_run=True)


@router.post("/auto-queue")
def auto_queue(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Queue due PO follow-up mails according to signal/status rules."""
    return po_followup_mail_service.queue_due_po_followups(db, limit=limit)

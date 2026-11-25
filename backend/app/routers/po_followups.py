"""PO-wise follow-up read APIs.

These endpoints surface procurement_records grouped by (supplier_name,
supplier_po_no). They do not mutate procurement state.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..core.deps import require_manager
from ..database import get_db
from ..services import po_followup_mail_service, po_followup_service
from ..services.staff_scope import StaffScopeDep, StaffScope, filter_items, get_staff_scope

router = APIRouter(prefix="/api/po-followups", tags=["po-followups"])


@router.get("/groups")
def list_groups(
    signal: Optional[str] = Query(None),
    supplier_name: Optional[str] = Query(None),
    supplier_po_no: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(25, ge=1, le=200),
    include_closed: bool = Query(False, description="Also show closed PO lines"),
    db: Session = Depends(get_db),
    scope: StaffScopeDep = None,
) -> dict[str, Any]:
    if scope is not None:
        # Non-admins see only their own POs (services/staff_scope.py): filter
        # the full group set, then page.
        groups = filter_items(scope, po_followup_service.build_all_po_groups(
            db, signal=signal, supplier_name=supplier_name,
            supplier_po_no=supplier_po_no, search=search, include_closed=include_closed,
        ))
        start = (page - 1) * size
        return {"total": len(groups), "page": page, "size": size,
                "items": groups[start:start + size]}
    return po_followup_service.list_po_groups(
        db,
        signal=signal,
        supplier_name=supplier_name,
        supplier_po_no=supplier_po_no,
        search=search,
        page=page,
        size=size,
        include_closed=include_closed,
    )


@router.get("/groups/by-key")
def group_by_key(
    supplier_name: str = Query(...),
    supplier_po_no: str = Query(...),
    include_closed: bool = Query(False),
    db: Session = Depends(get_db),
    scope: StaffScopeDep = None,
) -> dict[str, Any]:
    if scope is not None and not scope.allows_pair(supplier_name, supplier_po_no):
        raise HTTPException(404, "PO group not found")
    group = po_followup_service.get_po_group(
        db, supplier_name, supplier_po_no, include_closed=include_closed
    )
    if not group:
        raise HTTPException(404, "PO group not found")
    return group


@router.get("/commitments")
def list_commitments(
    supplier_po_no: Optional[str] = Query(None),
    supplier_po_nos: Optional[str] = Query(
        None, description="Comma-separated counters of one vendor-PO thread"
    ),
    supplier_name: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    scope: StaffScopeDep = None,
) -> list[dict[str, Any]]:
    po_filter: Any = supplier_po_no
    if supplier_po_nos:
        po_filter = [p for p in supplier_po_nos.split(",") if p.strip()]
    if scope is not None:
        # Rows carry no supplier/PO pair, so scope the requested counters instead.
        wanted = po_filter if isinstance(po_filter, list) else ([po_filter] if po_filter else [])
        allowed = [p for p in wanted if scope.allows_pair(supplier_name, p.strip())]
        if not allowed:
            return []
        po_filter = allowed if isinstance(po_filter, list) else allowed[0]
    return po_followup_service.list_commitments(
        db, supplier_po_no=po_filter, supplier_name=supplier_name
    )


@router.post("/auto-queue/test")
def test_auto_queue(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Preview automatic PO follow-up mails without creating queued messages."""
    return po_followup_mail_service.queue_due_po_followups(db, limit=limit, dry_run=True)


@router.post("/auto-queue", dependencies=[Depends(require_manager)])
def auto_queue(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Queue due PO follow-up mails according to signal/status rules."""
    return po_followup_mail_service.queue_due_po_followups(db, limit=limit)

"""Admin Purchase Orders view: all POs, per-PO detail (materials + communication),
and a whole-PO cancellation request. Admin only (guarded at the router level)."""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core.deps import get_current_user, require_admin
from ..database import get_db
from ..models.user import User
from ..services import po_cancel_service, po_view_service

router = APIRouter(
    prefix="/api/po-view",
    tags=["po-view"],
    dependencies=[Depends(require_admin)],
)


class PoCancelIn(BaseModel):
    remark: str | None = None


@router.get("/pos")
def list_pos(
    db: Session = Depends(get_db),
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=200),
) -> dict:
    items, total = po_view_service.grouped_pos(db, search=search, page=page, size=size)
    return {"items": items, "total": total, "page": page, "size": size}


@router.get("/lines")
def list_lines(
    db: Session = Depends(get_db),
    search: str | None = Query(default=None),
    owner: str | None = Query(default=None),
    signal: str | None = Query(default=None),
    po_status: str | None = Query(default=None),
    supplier_name: str | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    include_closed: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=200),
) -> dict:
    """Material-wise PO lines for the Orders page (one row per material)."""
    items, total = po_view_service.material_lines(
        db, search=search, owner_emp_code=owner, signal=signal, po_status=po_status,
        supplier_name=supplier_name,
        date_from=datetime.combine(date_from, datetime.min.time()) if date_from else None,
        date_to=datetime.combine(date_to, datetime.max.time()) if date_to else None,
        include_closed=include_closed, page=page, size=size,
    )
    return {"items": items, "total": total, "page": page, "size": size}


@router.get("/line-owners")
def list_line_owners(db: Session = Depends(get_db)) -> dict:
    return {"owners": po_view_service.line_owners(db)}


@router.post("/lines/{record_id}/request-cancel")
def request_line_cancel(
    record_id: int,
    payload: PoCancelIn | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Material-wise cancellation: one PO line, with the requester's remark."""
    result = po_cancel_service.request_line_cancellation(
        db,
        record_id=record_id,
        requested_by=user.email,
        remark=payload.remark if payload else None,
    )
    if result is None:
        raise HTTPException(404, "PO line not found")
    return result


@router.get("/pos/{supplier_po_no}/detail")
def po_detail(
    supplier_po_no: str,
    supplier_name: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict:
    detail = po_view_service.po_detail(
        db, supplier_po_no=supplier_po_no, supplier_name=supplier_name
    )
    if detail is None:
        raise HTTPException(404, "PO not found")
    return detail


@router.post("/pos/{supplier_po_no}/request-cancel")
def request_cancel(
    supplier_po_no: str,
    payload: PoCancelIn | None = None,
    supplier_name: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Raise a cancellation for the whole PO (all lines, any owner)."""
    result = po_cancel_service.request_cancellation(
        db,
        supplier_po_no=supplier_po_no,
        supplier_name=supplier_name,
        requested_by=user.email,
        owner_emp_code=None,
        remark=payload.remark if payload else None,
    )
    if result is None:
        raise HTTPException(404, "PO not found")
    return result

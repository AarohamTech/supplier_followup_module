"""Employee-scoped shipments (ASNs) — read-only view of the shipments raised
against the employee's own POs (``ProcurementRecord.owner_emp_code``).

Mirrors the staff `/api/asns` read endpoints; mounted in main.py with
``Depends(get_current_employee)``. Employees can refresh live courier tracking
(harmless read-side pull) but cannot add events, edit, or submit ASNs.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.deps import get_current_employee
from ..database import get_db
from ..models.procurement import ProcurementRecord
from ..models.user import User
from ..schemas.asn import AsnListOut, AsnOut
from ..services import asn_service, courier_tracking_service

router = APIRouter(prefix="/api/eportal/asns", tags=["eportal-asns"])


def _owned_po_set(db: Session, user: User) -> set[str]:
    rows = db.scalars(
        select(ProcurementRecord.supplier_po_no)
        .where(ProcurementRecord.owner_emp_code == user.emp_code)
        .distinct()
    ).all()
    return {po for po in rows if po}


def _scoped_asn(db: Session, user: User, asn_id: int):
    asn = asn_service.get_asn(db, asn_id, po_nos=_owned_po_set(db, user))
    if asn is None:
        # 404 (not 403) so out-of-scope IDs don't leak existence.
        raise HTTPException(404, "ASN not found")
    return asn


@router.get("/summary")
def summary(
    user: User = Depends(get_current_employee), db: Session = Depends(get_db)
) -> dict[str, int]:
    return asn_service.asn_summary(db, po_nos=_owned_po_set(db, user))


@router.get("", response_model=AsnListOut)
def list_asns(
    user: User = Depends(get_current_employee),
    db: Session = Depends(get_db),
    tab: str | None = Query(default=None),
    status: str | None = Query(default=None),
    search: str | None = Query(default=None),
) -> AsnListOut:
    rows = asn_service.list_asns(
        db, tab=tab, status=status, search=search, po_nos=_owned_po_set(db, user)
    )
    return AsnListOut(count=len(rows), items=[AsnOut.model_validate(r) for r in rows])


@router.get("/{asn_id}", response_model=AsnOut)
def get_asn(
    asn_id: int,
    user: User = Depends(get_current_employee),
    db: Session = Depends(get_db),
) -> AsnOut:
    return AsnOut.model_validate(_scoped_asn(db, user, asn_id))


@router.post("/{asn_id}/refresh-tracking", response_model=AsnOut)
def refresh_tracking(
    asn_id: int,
    user: User = Depends(get_current_employee),
    db: Session = Depends(get_db),
) -> AsnOut:
    """On-demand courier checkpoint pull for an owned-PO shipment. Fail-safe:
    returns the ASN unchanged when tracking is disabled/unreachable."""
    asn = _scoped_asn(db, user, asn_id)
    courier_tracking_service.poll_one(db, asn)
    return AsnOut.model_validate(_scoped_asn(db, user, asn_id))

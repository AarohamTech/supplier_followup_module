"""Internal staff view of ASNs (shipments suppliers submit).

Mounted with the staff `_rbac` guard in main.py, so reads are open to any staff
member and state changes require `user`+ (viewer is read-only). Suppliers never
reach this router — they use `/api/portal/asns`.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.asn import Asn
from ..schemas.asn import AsnEventIn, AsnListOut, AsnOut, AsnSummaryOut, AsnUpdate
from ..services import asn_service, courier_tracking_service
from ..services.staff_scope import StaffScopeDep, StaffScope, get_staff_scope

router = APIRouter(prefix="/api/asns", tags=["asns"])


def _where(scope: Optional[StaffScope]) -> Any:
    """Non-admins see ASNs of their own POs and of their assigned suppliers
    (services/staff_scope.py). None = admin, no filter."""
    if scope is None:
        return None
    conds = [scope.pair_clause(Asn.supplier_name, Asn.supplier_po_no)]
    if scope.assigned_supplier_ids:
        conds.append(Asn.supplier_id.in_(sorted(scope.assigned_supplier_ids)))
    return or_(*conds)


def _get_or_404(db: Session, asn_id: int, scope: Optional[StaffScope]):
    asn = asn_service.get_asn(db, asn_id, where=_where(scope))
    if asn is None:
        raise HTTPException(404, "ASN not found")
    return asn


@router.get("/summary", response_model=AsnSummaryOut)
def summary(
    db: Session = Depends(get_db),
    scope: StaffScopeDep = None,
) -> AsnSummaryOut:
    return AsnSummaryOut(**asn_service.asn_summary(db, where=_where(scope)))


@router.get("", response_model=AsnListOut)
def list_asns(
    db: Session = Depends(get_db),
    tab: str | None = Query(default=None),
    status: str | None = Query(default=None),
    search: str | None = Query(default=None),
    scope: StaffScopeDep = None,
) -> AsnListOut:
    rows = asn_service.list_asns(db, tab=tab, status=status, search=search, where=_where(scope))
    return AsnListOut(count=len(rows), items=[AsnOut.model_validate(r) for r in rows])


@router.get("/{asn_id}", response_model=AsnOut)
def get_asn(
    asn_id: int,
    db: Session = Depends(get_db),
    scope: StaffScopeDep = None,
) -> AsnOut:
    return AsnOut.model_validate(_get_or_404(db, asn_id, scope))


@router.patch("/{asn_id}", response_model=AsnOut)
def update_asn(
    asn_id: int,
    payload: AsnUpdate,
    db: Session = Depends(get_db),
    scope: StaffScopeDep = None,
) -> AsnOut:
    asn = _get_or_404(db, asn_id, scope)
    asn = asn_service.update_asn(db, asn, payload.model_dump(exclude_unset=True))
    return AsnOut.model_validate(asn)


@router.post("/{asn_id}/refresh-tracking", response_model=AsnOut)
def refresh_tracking(
    asn_id: int,
    db: Session = Depends(get_db),
    scope: StaffScopeDep = None,
) -> AsnOut:
    """Pull fresh courier checkpoints for this ASN on demand (drawer open).

    Fail-safe: if courier polling is disabled, the ASN isn't trackable, or the
    courier API is unreachable, this returns the ASN unchanged.
    """
    asn = _get_or_404(db, asn_id, scope)
    courier_tracking_service.poll_one(db, asn)
    asn = asn_service.get_asn(db, asn_id)
    return AsnOut.model_validate(asn)


@router.post("/{asn_id}/events", response_model=AsnOut)
def add_event(
    asn_id: int,
    payload: AsnEventIn,
    db: Session = Depends(get_db),
    scope: StaffScopeDep = None,
) -> AsnOut:
    asn = _get_or_404(db, asn_id, scope)
    if not asn_service.is_valid_status(payload.stage):
        raise HTTPException(422, f"Unknown stage '{payload.stage}'")
    asn = asn_service.add_event(
        db, asn,
        stage=payload.stage,
        location=payload.location,
        note=payload.note,
        label=payload.label,
        alert=payload.alert,
        alert_reason=payload.alert_reason,
        created_by="staff",
        occurred_at=payload.occurred_at,
    )
    return AsnOut.model_validate(asn)

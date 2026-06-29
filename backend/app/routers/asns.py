"""Internal staff view of ASNs (shipments suppliers submit).

Mounted with the staff `_rbac` guard in main.py, so reads are open to any staff
member and state changes require `user`+ (viewer is read-only). Suppliers never
reach this router — they use `/api/portal/asns`.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas.asn import AsnEventIn, AsnListOut, AsnOut, AsnSummaryOut, AsnUpdate
from ..services import asn_service, courier_tracking_service

router = APIRouter(prefix="/api/asns", tags=["asns"])


@router.get("/summary", response_model=AsnSummaryOut)
def summary(db: Session = Depends(get_db)) -> AsnSummaryOut:
    return AsnSummaryOut(**asn_service.asn_summary(db))


@router.get("", response_model=AsnListOut)
def list_asns(
    db: Session = Depends(get_db),
    tab: str | None = Query(default=None),
    status: str | None = Query(default=None),
    search: str | None = Query(default=None),
) -> AsnListOut:
    rows = asn_service.list_asns(db, tab=tab, status=status, search=search)
    return AsnListOut(count=len(rows), items=[AsnOut.model_validate(r) for r in rows])


@router.get("/{asn_id}", response_model=AsnOut)
def get_asn(asn_id: int, db: Session = Depends(get_db)) -> AsnOut:
    asn = asn_service.get_asn(db, asn_id)
    if asn is None:
        raise HTTPException(404, "ASN not found")
    return AsnOut.model_validate(asn)


@router.patch("/{asn_id}", response_model=AsnOut)
def update_asn(asn_id: int, payload: AsnUpdate, db: Session = Depends(get_db)) -> AsnOut:
    asn = asn_service.get_asn(db, asn_id)
    if asn is None:
        raise HTTPException(404, "ASN not found")
    asn = asn_service.update_asn(db, asn, payload.model_dump(exclude_unset=True))
    return AsnOut.model_validate(asn)


@router.post("/{asn_id}/refresh-tracking", response_model=AsnOut)
def refresh_tracking(asn_id: int, db: Session = Depends(get_db)) -> AsnOut:
    """Pull fresh courier checkpoints for this ASN on demand (drawer open).

    Fail-safe: if courier polling is disabled, the ASN isn't trackable, or the
    courier API is unreachable, this returns the ASN unchanged.
    """
    asn = asn_service.get_asn(db, asn_id)
    if asn is None:
        raise HTTPException(404, "ASN not found")
    courier_tracking_service.poll_one(db, asn)
    asn = asn_service.get_asn(db, asn_id)
    return AsnOut.model_validate(asn)


@router.post("/{asn_id}/events", response_model=AsnOut)
def add_event(asn_id: int, payload: AsnEventIn, db: Session = Depends(get_db)) -> AsnOut:
    asn = asn_service.get_asn(db, asn_id)
    if asn is None:
        raise HTTPException(404, "ASN not found")
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

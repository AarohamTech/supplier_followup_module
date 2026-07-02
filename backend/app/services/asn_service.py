"""ASN lifecycle + queries. Pure service layer (no FastAPI imports).

Owns the shipment-stage metadata (progress %, badge label, summary-card bucket),
ASN-number generation, create/update/advance, list/summary, and the
"PO is Completed when it has a Delivered ASN" rule the portal dashboard uses.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..models.asn import Asn, AsnEvent, AsnItem

# Lifecycle stages in order. CANCELLED is terminal but off the happy path.
STAGE_ORDER: tuple[str, ...] = (
    "DRAFT",
    "SUBMITTED",
    "DISPATCHED",
    "IN_TRANSIT",
    "AT_CUSTOMS",
    "INBOUND_HUB",
    "OUT_FOR_DELIVERY",
    "DELIVERED",
)

# progress %, default badge label, and which dashboard card the stage feeds.
STAGE_META: dict[str, dict[str, Any]] = {
    "DRAFT": {"progress": 0, "label": "Draft", "bucket": "draft"},
    "SUBMITTED": {"progress": 10, "label": "Created", "bucket": "active"},
    "DISPATCHED": {"progress": 25, "label": "On Board / Departed", "bucket": "active"},
    "IN_TRANSIT": {"progress": 55, "label": "In Transit", "bucket": "active"},
    "AT_CUSTOMS": {"progress": 70, "label": "At Customs", "bucket": "pending"},
    "INBOUND_HUB": {"progress": 85, "label": "Inbound Hub", "bucket": "pending"},
    "OUT_FOR_DELIVERY": {"progress": 95, "label": "Arriving Soon", "bucket": "active"},
    "DELIVERED": {"progress": 100, "label": "Delivered", "bucket": "finalized"},
    "CANCELLED": {"progress": 0, "label": "Cancelled", "bucket": "none"},
}

# Tabs in the ASN portal.
ACTIVE_STATUSES = ("SUBMITTED", "DISPATCHED", "IN_TRANSIT", "AT_CUSTOMS", "INBOUND_HUB", "OUT_FOR_DELIVERY")
HISTORY_STATUSES = ("DELIVERED", "CANCELLED")
TRANSPORT_MODES = ("SEA", "AIR", "ROAD", "RAIL")


def stage_meta(status: str) -> dict[str, Any]:
    return STAGE_META.get((status or "").upper(), STAGE_META["DRAFT"])


def is_valid_status(status: str | None) -> bool:
    return (status or "").upper() in STAGE_META


# ── ASN number ────────────────────────────────────────────────────────────────
def next_asn_no(db: Session) -> str:
    """`ASN-YYYY-NNNN`, sequential within the year."""
    year = datetime.utcnow().year
    prefix = f"ASN-{year}-"
    rows = db.scalars(select(Asn.asn_no).where(Asn.asn_no.like(f"{prefix}%"))).all()
    max_seq = 0
    for no in rows:
        try:
            max_seq = max(max_seq, int(str(no).rsplit("-", 1)[-1]))
        except (ValueError, IndexError):
            continue
    return f"{prefix}{max_seq + 1:04d}"


# ── Stage application ─────────────────────────────────────────────────────────
def _apply_stage(asn: Asn, status: str, *, label: str | None = None) -> None:
    status = (status or "DRAFT").upper()
    meta = stage_meta(status)
    asn.status = status
    asn.status_label = label or meta["label"]
    asn.progress_percent = int(meta["progress"])
    if status == "DELIVERED":
        asn.delivered_at = asn.delivered_at or datetime.utcnow()
        # Delivery clears any in-flight alert.
        asn.alert = False
        asn.alert_reason = None


# ── Create / update / advance ─────────────────────────────────────────────────
def create_asn(
    db: Session,
    *,
    supplier_id: int,
    supplier_name: str | None,
    supplier_po_no: str,
    crm_no: str | None = None,
    carrier_name: str | None = None,
    courier_code: str | None = None,
    tracking_no: str | None = None,
    transport_mode: str | None = None,
    origin: str | None = None,
    destination: str | None = None,
    dispatch_date: datetime | None = None,
    eta: datetime | None = None,
    remarks: str | None = None,
    items: list[dict[str, Any]] | None = None,
    submit: bool = False,
    created_by_user_id: int | None = None,
    created_by_email: str | None = None,
) -> Asn:
    asn = Asn(
        asn_no=next_asn_no(db),
        supplier_id=supplier_id,
        supplier_name=supplier_name,
        supplier_po_no=supplier_po_no,
        crm_no=crm_no,
        carrier_name=carrier_name,
        courier_code=(courier_code or None),
        tracking_no=tracking_no,
        transport_mode=(transport_mode or None),
        origin=origin,
        destination=destination,
        dispatch_date=dispatch_date,
        eta=eta,
        remarks=remarks,
        created_by_user_id=created_by_user_id,
        created_by_email=created_by_email,
    )
    initial_status = "SUBMITTED" if submit else "DRAFT"
    _apply_stage(asn, initial_status)

    for it in items or []:
        asn.items.append(
            AsnItem(
                procurement_record_id=it.get("procurement_record_id"),
                material_name=it.get("material_name") or "",
                material_code=it.get("material_code"),
                po_qty=it.get("po_qty"),
                qty_shipped=it.get("qty_shipped"),
                uom=it.get("uom"),
                invoice_no=it.get("invoice_no"),
            )
        )

    db.add(asn)
    db.flush()
    if submit:
        asn.events.append(
            AsnEvent(
                stage="SUBMITTED",
                status_label=stage_meta("SUBMITTED")["label"],
                note="ASN submitted",
                created_by=created_by_email,
            )
        )
    db.commit()
    db.refresh(asn)
    return asn


EDITABLE_FIELDS = (
    "supplier_po_no", "crm_no", "carrier_name", "courier_code", "tracking_no",
    "transport_mode", "origin", "destination", "dispatch_date", "eta", "remarks",
)


def update_asn(db: Session, asn: Asn, data: dict[str, Any]) -> Asn:
    for field in EDITABLE_FIELDS:
        if field in data and data[field] is not None:
            setattr(asn, field, data[field])
    # Allow toggling the alert flag directly.
    if "alert" in data and data["alert"] is not None:
        asn.alert = bool(data["alert"])
        asn.alert_reason = data.get("alert_reason") if asn.alert else None
    # Submitting a draft.
    if data.get("submit") and asn.status == "DRAFT":
        _apply_stage(asn, "SUBMITTED")
        asn.events.append(
            AsnEvent(stage="SUBMITTED", status_label=stage_meta("SUBMITTED")["label"], note="ASN submitted")
        )
    db.commit()
    db.refresh(asn)
    return asn


def add_event(
    db: Session,
    asn: Asn,
    *,
    stage: str,
    location: str | None = None,
    note: str | None = None,
    label: str | None = None,
    alert: bool | None = None,
    alert_reason: str | None = None,
    created_by: str | None = None,
    occurred_at: datetime | None = None,
    lat: float | None = None,
    lng: float | None = None,
    source: str | None = None,
) -> Asn:
    """Append a tracking event and advance the ASN to that stage."""
    stage = (stage or "").upper()
    _apply_stage(asn, stage, label=label)
    if alert is not None:
        asn.alert = bool(alert)
        asn.alert_reason = alert_reason if asn.alert else None
    asn.events.append(
        AsnEvent(
            stage=stage,
            status_label=label or stage_meta(stage)["label"],
            location=location,
            note=note,
            created_by=created_by,
            occurred_at=occurred_at or datetime.utcnow(),
            lat=lat,
            lng=lng,
            source=source,
        )
    )
    db.commit()
    db.refresh(asn)
    return asn


# ── Queries ───────────────────────────────────────────────────────────────────
def _base_query(supplier_id: int | None, po_nos: set[str] | None = None):
    stmt = select(Asn).options(selectinload(Asn.items), selectinload(Asn.events))
    if supplier_id is not None:
        stmt = stmt.where(Asn.supplier_id == supplier_id)
    # Employee scope: only shipments against this PO-number set (empty → none).
    if po_nos is not None:
        stmt = stmt.where(Asn.supplier_po_no.in_(po_nos))
    return stmt


def get_asn(
    db: Session,
    asn_id: int,
    *,
    supplier_id: int | None = None,
    po_nos: set[str] | None = None,
) -> Optional[Asn]:
    stmt = _base_query(supplier_id, po_nos).where(Asn.id == asn_id)
    return db.scalar(stmt)


def list_asns(
    db: Session,
    *,
    supplier_id: int | None = None,
    tab: str | None = None,
    search: str | None = None,
    status: str | None = None,
    po_nos: set[str] | None = None,
) -> list[Asn]:
    stmt = _base_query(supplier_id, po_nos)
    tab = (tab or "").lower()
    if tab == "active":
        stmt = stmt.where(Asn.status.in_(ACTIVE_STATUSES))
    elif tab == "drafts":
        stmt = stmt.where(Asn.status == "DRAFT")
    elif tab == "history":
        stmt = stmt.where(Asn.status.in_(HISTORY_STATUSES))
    if status:
        stmt = stmt.where(Asn.status == status.upper())
    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                Asn.asn_no.ilike(like),
                Asn.supplier_po_no.ilike(like),
                Asn.carrier_name.ilike(like),
                Asn.tracking_no.ilike(like),
                Asn.supplier_name.ilike(like),
            )
        )
    stmt = stmt.order_by(Asn.created_at.desc())
    return list(db.scalars(stmt).all())


def asn_summary(
    db: Session, *, supplier_id: int | None = None, po_nos: set[str] | None = None
) -> dict[str, int]:
    """The four shipment-tracking cards: active / pending / urgent / finalized."""
    def count(*conditions) -> int:
        stmt = select(func.count(Asn.id))
        if supplier_id is not None:
            stmt = stmt.where(Asn.supplier_id == supplier_id)
        if po_nos is not None:
            stmt = stmt.where(Asn.supplier_po_no.in_(po_nos))
        for cond in conditions:
            stmt = stmt.where(cond)
        return int(db.scalar(stmt) or 0)

    active = count(Asn.status.in_(("SUBMITTED", "DISPATCHED", "IN_TRANSIT", "OUT_FOR_DELIVERY")))
    pending = count(Asn.status.in_(("AT_CUSTOMS", "INBOUND_HUB")))
    urgent = count(Asn.alert.is_(True), Asn.status.notin_(("DELIVERED", "CANCELLED")))
    finalized = count(
        Asn.status == "DELIVERED",
        Asn.delivered_at >= datetime.utcnow() - timedelta(days=30),
    )
    total = count()
    drafts = count(Asn.status == "DRAFT")
    return {
        "active": active,
        "pending": pending,
        "urgent": urgent,
        "finalized": finalized,
        "total": total,
        "drafts": drafts,
    }


def completed_po_numbers(db: Session, *, supplier_id: int | None = None) -> set[str]:
    """PO numbers that have at least one DELIVERED ASN (→ PO is Completed)."""
    stmt = select(Asn.supplier_po_no).where(Asn.status == "DELIVERED")
    if supplier_id is not None:
        stmt = stmt.where(Asn.supplier_id == supplier_id)
    return {po for po in db.scalars(stmt).all() if po}

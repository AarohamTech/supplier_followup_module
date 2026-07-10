"""Grouped PO views shared by the admin Purchase Orders page and the employee portal.

Groups procurement records by (supplier, PO) and provides a per-PO detail with
materials + the full communication history (messages with dates). Pass
``owner_emp_code`` to scope to one employee's POs; omit it for the admin all-POs view.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import case, desc, func, or_, select
from sqlalchemy.orm import Session

from ..models.communication_message import CommunicationMessage
from ..models.procurement import ProcurementRecord

_SIGNAL_LABEL = {4: "BLACK", 3: "RED", 2: "YELLOW", 1: "GREEN", 0: None}
_CANCEL_LABEL = {2: "CANCELLED", 1: "PENDING", 0: None}


def _as_dt(d: Any) -> datetime | None:
    if d is None:
        return None
    return d if isinstance(d, datetime) else datetime.combine(d, datetime.min.time())


def _po_cancel(records: list[ProcurementRecord]) -> str | None:
    """PO-level cancellation: CANCELLED wins over PENDING wins over none."""
    result = None
    for r in records:
        cs = (r.cancellation_status or "").upper()
        if cs == "CANCELLED":
            return "CANCELLED"
        if cs == "PENDING":
            result = "PENDING"
    return result


def grouped_pos(
    db: Session,
    *,
    owner_emp_code: str | None = None,
    search: str | None = None,
    page: int | None = None,
    size: int | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """POs grouped by (supplier, PO), aggregated in SQL so we never load every row.

    Returns (items, total_groups). Pass page+size to get one page; omit both for all.
    A supplier's PO matches `search` if any of its lines match po/vendor/CRM.
    """
    R = ProcurementRecord
    sig_rank = case(
        (func.upper(R.signal) == "BLACK", 4),
        (func.upper(R.signal) == "RED", 3),
        (func.upper(R.signal) == "YELLOW", 2),
        (func.upper(R.signal) == "GREEN", 1),
        else_=0,
    )
    cancel_rank = case(
        (func.upper(R.cancellation_status) == "CANCELLED", 2),
        (func.upper(R.cancellation_status) == "PENDING", 1),
        else_=0,
    )
    escalated = func.max(
        case((func.upper(func.coalesce(R.escalation_level, "NONE")) != "NONE", 1), else_=0)
    ).label("escalated")
    signal_c = func.max(sig_rank).label("signal_rank")
    cancel_c = func.max(cancel_rank).label("cancel_rank")
    # Receipt progress rollup: a PO is COMPLETED only when every line is COMPLETED;
    # any received progress on any line makes it PARTIAL.
    completed_c = func.sum(
        case((func.upper(func.coalesce(R.receipt_status, "")) == "COMPLETED", 1), else_=0)
    ).label("completed_lines")
    progressed_c = func.sum(
        case((func.upper(func.coalesce(R.receipt_status, "")).in_(["COMPLETED", "PARTIAL"]), 1), else_=0)
    ).label("progressed_lines")
    tracked_c = func.sum(
        case((R.receipt_status.isnot(None), 1), else_=0)
    ).label("tracked_lines")
    name_key = func.upper(func.coalesce(R.supplier_name, ""))

    base = select(
        R.supplier_po_no.label("po"),
        func.max(R.supplier_name).label("supplier_name"),
        func.max(R.crm_no).label("crm_no"),
        func.count(R.id).label("material_count"),
        signal_c,
        escalated,
        cancel_c,
        completed_c,
        progressed_c,
        tracked_c,
        func.min(R.shipment_date).label("earliest"),
        func.max(R.po_status).label("po_status"),
    ).where(R.supplier_po_no.isnot(None))
    if owner_emp_code:
        base = base.where(R.owner_emp_code == owner_emp_code)
    if search and search.strip():
        like = f"%{search.strip()}%"
        base = base.where(or_(
            R.supplier_po_no.ilike(like),
            R.supplier_name.ilike(like),
            R.crm_no.ilike(like),
        ))
    grouped = base.group_by(name_key, R.supplier_po_no)

    total = db.scalar(select(func.count()).select_from(grouped.subquery())) or 0

    ordered = grouped.order_by(desc("escalated"), desc("signal_rank"), R.supplier_po_no.asc())
    if page and size:
        ordered = ordered.limit(size).offset((page - 1) * size)
    rows = db.execute(ordered).all()

    items: list[dict[str, Any]] = []
    keys: list[tuple[str, str]] = []
    for r in rows:
        material_count = int(r.material_count or 0)
        completed = int(r.completed_lines or 0)
        progressed = int(r.progressed_lines or 0)
        tracked = int(r.tracked_lines or 0)
        if tracked > 0 and completed == material_count:
            receipt = "COMPLETED"
        elif progressed > 0:
            receipt = "PARTIAL"
        elif tracked > 0:
            receipt = "PENDING"
        else:
            receipt = None
        items.append({
            "supplier_po_no": r.po,
            "crm_no": r.crm_no,
            "supplier_name": r.supplier_name,
            "material_count": material_count,
            "overall_signal": _SIGNAL_LABEL.get(int(r.signal_rank or 0)),
            "po_status": r.po_status,
            "cancellation_status": _CANCEL_LABEL.get(int(r.cancel_rank or 0)),
            "receipt_status": receipt,
            "earliest_shipment_date": _as_dt(r.earliest),
            "escalated": bool(r.escalated),
            "unread_inbound": 0,
        })
        keys.append(((r.supplier_name or "").strip().upper(), r.po))

    # Unread INCOMING supplier replies — only for the POs on this page.
    po_nos = [k[1] for k in keys]
    if po_nos:
        unread: dict[tuple[str, str], int] = {}
        for sup_name, po_no, cnt in db.execute(
            select(
                CommunicationMessage.supplier_name,
                CommunicationMessage.supplier_po_no,
                func.count(CommunicationMessage.id),
            )
            .where(
                CommunicationMessage.direction == "INCOMING",
                CommunicationMessage.read_at.is_(None),
                CommunicationMessage.supplier_po_no.in_(po_nos),
            )
            .group_by(CommunicationMessage.supplier_name, CommunicationMessage.supplier_po_no)
        ).all():
            if po_no:
                unread[((sup_name or "").strip().upper(), po_no)] = int(cnt or 0)
        for item, key in zip(items, keys):
            item["unread_inbound"] = unread.get(key, 0)

    return items, int(total)


def list_groups(db: Session, *, owner_emp_code: str | None = None) -> list[dict[str, Any]]:
    """All POs (grouped), unpaginated. Used by the employee portal (small, own POs)."""
    items, _ = grouped_pos(db, owner_emp_code=owner_emp_code)
    return items


def _material(r: ProcurementRecord) -> dict[str, Any]:
    return {
        "procurement_record_id": r.id,
        "crm_no": r.crm_no,
        "material_name": r.material_name,
        "uom": r.uom,
        "qty": float(r.qty) if r.qty is not None else None,
        "supplier_name": r.supplier_name,
        "shipment_date": _as_dt(r.shipment_date),
        "signal": r.signal,
        "po_status": r.po_status,
        "rate": float(r.rate) if r.rate is not None else None,
        "lead_time": r.lead_time,
        "commitment_date": _as_dt(r.commitment_date),
        # Receipt progress from the CRM desk feed (GRN quantities).
        "po_qty": float(r.po_qty) if r.po_qty is not None else None,
        "grn_qty": float(r.grn_qty) if r.grn_qty is not None else None,
        "pending_qty": float(r.pending_qty) if r.pending_qty is not None else None,
        "receipt_status": r.receipt_status,
    }


def _message(m: CommunicationMessage) -> dict[str, Any]:
    return {
        "id": m.id,
        "direction": m.direction,
        "subject": m.subject,
        "snippet": (m.body or "")[:280],
        "sender_email": m.sender_email,
        "receiver_email": m.receiver_email,
        "status": m.status,
        "mail_type": m.mail_type,
        "created_at": m.created_at,
        "received_at": m.received_at,
        "sent_at": m.sent_at,
    }


def po_detail(
    db: Session, *, supplier_po_no: str, supplier_name: str | None = None,
    owner_emp_code: str | None = None,
) -> dict[str, Any] | None:
    """Materials + full communication history for one PO. Returns None if no
    matching (scoped) records exist — the caller turns that into a 404."""
    mstmt = select(ProcurementRecord).where(ProcurementRecord.supplier_po_no == supplier_po_no)
    if supplier_name:
        mstmt = mstmt.where(func.upper(ProcurementRecord.supplier_name) == supplier_name.strip().upper())
    if owner_emp_code:
        mstmt = mstmt.where(ProcurementRecord.owner_emp_code == owner_emp_code)
    rows = list(db.scalars(mstmt).all())
    if not rows:
        return None

    cstmt = select(CommunicationMessage).where(CommunicationMessage.supplier_po_no == supplier_po_no)
    if supplier_name:
        cstmt = cstmt.where(func.upper(CommunicationMessage.supplier_name) == supplier_name.strip().upper())
    msgs = list(db.scalars(cstmt.order_by(CommunicationMessage.created_at.asc())).all())

    return {
        "supplier_po_no": supplier_po_no,
        "supplier_name": rows[0].supplier_name,
        "cancellation_status": _po_cancel(rows),
        "materials": [_material(r) for r in rows],
        "messages": [_message(m) for m in msgs],
    }

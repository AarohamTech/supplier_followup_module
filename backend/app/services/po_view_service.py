"""Grouped PO views shared by the admin Purchase Orders page and the employee portal.

Groups procurement records by (supplier, PO) and provides a per-PO detail with
materials + the full communication history (messages with dates). Pass
``owner_emp_code`` to scope to one employee's POs; omit it for the admin all-POs view.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models.communication_message import CommunicationMessage
from ..models.procurement import ProcurementRecord

_SIGNAL_RANK = {"GREEN": 1, "YELLOW": 2, "RED": 3, "BLACK": 4}


def _worst_signal(signals: list[str | None]) -> str | None:
    worst, worst_rank = None, 0
    for sig in signals:
        r = _SIGNAL_RANK.get((sig or "").upper(), 0)
        if r > worst_rank:
            worst_rank, worst = r, (sig or "").upper()
    return worst


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


def list_groups(db: Session, *, owner_emp_code: str | None = None) -> list[dict[str, Any]]:
    """Every PO (grouped by supplier+PO). Scope to one employee with owner_emp_code."""
    stmt = select(ProcurementRecord)
    if owner_emp_code:
        stmt = stmt.where(ProcurementRecord.owner_emp_code == owner_emp_code)
    records = list(db.scalars(stmt).all())

    groups: dict[tuple[str, str], dict] = {}
    for r in records:
        po = r.supplier_po_no
        if not po:
            continue
        key = ((r.supplier_name or "").strip().upper(), po)
        g = groups.setdefault(key, {
            "supplier_po_no": po,
            "crm_no": r.crm_no,
            "supplier_name": r.supplier_name,
            "signals": [],
            "po_status": r.po_status,
            "records": [],
            "earliest": None,
            "escalated": False,
        })
        g["signals"].append(r.signal)
        g["records"].append(r)
        if (r.escalation_level or "NONE").upper() != "NONE":
            g["escalated"] = True
        sd = _as_dt(r.shipment_date)
        if sd and (g["earliest"] is None or sd < g["earliest"]):
            g["earliest"] = sd

    # Unread INCOMING supplier replies per (supplier, PO).
    unread: dict[tuple[str, str], int] = {}
    po_nos = [g["supplier_po_no"] for g in groups.values()]
    if po_nos:
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

    items: list[dict[str, Any]] = []
    for key, g in groups.items():
        items.append({
            "supplier_po_no": g["supplier_po_no"],
            "crm_no": g["crm_no"],
            "supplier_name": g["supplier_name"],
            "material_count": len(g["records"]),
            "overall_signal": _worst_signal(g["signals"]),
            "po_status": g["po_status"],
            "cancellation_status": _po_cancel(g["records"]),
            "earliest_shipment_date": g["earliest"],
            "escalated": g["escalated"],
            "unread_inbound": unread.get(key, 0),
        })
    items.sort(key=lambda p: (
        0 if p["escalated"] else 1,
        -_SIGNAL_RANK.get((p["overall_signal"] or "").upper(), 0),
        p["supplier_po_no"],
    ))
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

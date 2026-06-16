"""Communication Hub aggregation router.

Reads existing pipeline data (ProcurementRecord, MailHistory, SupplierMaster,
CommunicationTask) and provides action endpoints.

Does NOT modify procurement / mail-template / signal / cron / supplier-master logic.
Only consumes those systems as data sources and triggers them via their own services.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..core.deps import require_manager
from ..database import get_db
from ..models.communication_task import (
    TASK_PRIORITIES,
    TASK_SIGNALS,
    TASK_STATUSES,
    CommunicationTask,
)
from ..models.communication_message import CommunicationMessage
from ..models.mail_history import MailHistory
from ..models.procurement import ProcurementRecord
from ..models.supplier import SupplierMaster
from ..models.supplier_email import SupplierEmail
from ..schemas.communication_task import (
    CommunicationTaskCreate,
    CommunicationTaskUpdate,
)
from ..services.followup_engine import apply_followup_logic, get_followup_rule
from ..services.mail_template_service import build_context, pick_template, render
from ..services import communication_message_service as msg_service
from ..services import po_followup_service
from ..services.reply_table_parser import parse_reply_table

router = APIRouter(prefix="/api/communication-hub", tags=["communication-hub"])

# ─────────────────────────────────────────────────────────────────────────────
# Signal display helpers (read-only mapping, no business logic)
# ─────────────────────────────────────────────────────────────────────────────
_SIGNAL_RANK: dict[str, int] = {"GREEN": 1, "YELLOW": 2, "RED": 3, "BLACK": 4}
_HEALTH: dict[str, int] = {"GREEN": 88, "YELLOW": 65, "RED": 35, "BLACK": 12}
_RISK_LEVEL: dict[str, str] = {
    "GREEN": "LOW",
    "YELLOW": "MEDIUM",
    "RED": "HIGH",
    "BLACK": "CRITICAL",
}

_MAIL_TYPE_TO_SIGNAL: dict[str, str] = {
    "BLACK_ESCALATION": "BLACK",
    "AI_REQUIRED": "RED",
    "RED_DAY1": "RED",
    "RED_DAY2": "RED",
    "YELLOW_REMINDER": "YELLOW",
    "GREEN_PO_RELEASE": "GREEN",
    "GENERAL_FOLLOWUP": "GREEN",
}


def _norm_signal(s: Optional[str]) -> str:
    v = (s or "GREEN").upper()
    return v if v in _SIGNAL_RANK else "GREEN"


def _worst_signal(signals: list[str]) -> str:
    if not signals:
        return "GREEN"
    return max(signals, key=lambda s: _SIGNAL_RANK.get(_norm_signal(s), 1))


def _signal_from_mail_type(mail_type: str) -> str:
    t = (mail_type or "").upper()
    for k, v in _MAIL_TYPE_TO_SIGNAL.items():
        if k in t:
            return v
    if "BLACK" in t or "CRITIC" in t or "ESCAL" in t:
        return "BLACK"
    if "RED" in t:
        return "RED"
    if "YELLOW" in t or "REMIND" in t or "DELAY" in t:
        return "YELLOW"
    return "GREEN"


def _validate_enum(field: str, value: str, allowed: tuple[str, ...]) -> None:
    if value not in allowed:
        raise HTTPException(422, f"{field} must be one of: {', '.join(allowed)}")


def _is_po_group_mail(row: MailHistory) -> bool:
    return (row.material_name or "").strip().upper().startswith("ALL MATERIALS") or (
        row.mail_type or ""
    ).strip().upper().startswith("PO_")


def _po_message_table_rows(po_group: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not po_group:
        return []
    rows: list[dict[str, Any]] = []
    for material in po_group.get("materials") or []:
        commitment = material.get("commitment") or {}
        rows.append(
            {
                "crm_no": material.get("crm_no"),
                "material_name": material.get("material_name"),
                "qty": material.get("po_qty"),
                "uom": material.get("uom"),
                "due_date": material.get("due_date"),
                "status": material.get("current_status") or material.get("signal"),
                "commitment_date": commitment.get("commitment_date"),
                "remark": commitment.get("supplier_remark"),
            }
        )
    return rows


def _reply_message_table_rows(body: str | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in parse_reply_table(body):
        commitment_date = row.get("commitment_date")
        rows.append(
            {
                "crm_no": row.get("material_code"),
                "material_name": row.get("material_name"),
                "qty": row.get("quantity"),
                "uom": None,
                "due_date": None,
                "status": row.get("supplier_status"),
                "commitment_date": commitment_date.isoformat()
                if commitment_date
                else None,
                "remark": row.get("remark"),
            }
        )
    return rows


def _norm_cell(value: Any) -> str:
    return str(value or "").strip().upper()


def _merge_po_and_reply_rows(
    po_rows: list[dict[str, Any]], reply_rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    if not po_rows:
        return reply_rows
    if not reply_rows:
        return po_rows

    merged: list[dict[str, Any]] = []
    for po_row in po_rows:
        reply = next(
            (
                row
                for row in reply_rows
                if (
                    _norm_cell(row.get("crm_no"))
                    and _norm_cell(row.get("crm_no")) == _norm_cell(po_row.get("crm_no"))
                )
                or (
                    _norm_cell(row.get("material_name"))
                    and _norm_cell(row.get("material_name"))
                    == _norm_cell(po_row.get("material_name"))
                )
            ),
            None,
        )
        if not reply:
            merged.append(po_row)
            continue

        next_row = dict(po_row)
        if reply.get("qty") is not None:
            next_row["qty"] = reply.get("qty")
        if reply.get("status") not in (None, "", "-"):
            next_row["status"] = reply.get("status")
        if reply.get("commitment_date") not in (None, "", "-"):
            next_row["commitment_date"] = reply.get("commitment_date")
        if reply.get("remark") not in (None, "", "-"):
            next_row["remark"] = reply.get("remark")
        merged.append(next_row)

    return merged


def _reply_rows_match_po(
    po_rows: list[dict[str, Any]], reply_rows: list[dict[str, Any]]
) -> bool:
    if not po_rows or not reply_rows:
        return False

    po_keys = {
        (_norm_cell(row.get("crm_no")), _norm_cell(row.get("material_name")))
        for row in po_rows
    }
    matches = 0
    for row in reply_rows:
        key = (_norm_cell(row.get("crm_no")), _norm_cell(row.get("material_name")))
        if key in po_keys:
            matches += 1
            continue
        crm = key[0]
        material = key[1]
        if any((crm and crm == po_crm) or (material and material == po_material) for po_crm, po_material in po_keys):
            matches += 1

    return matches > 0 and matches >= min(len(reply_rows), max(1, len(po_rows) // 2))


def _looks_like_po_draft_echo(body: str | None) -> bool:
    text = (body or "").upper()
    return (
        "THIS IS A FOLLOW-UP FOR PO NO." in text
        and "PLEASE REPLY BY FILLING THE FOLLOWING COLUMNS" in text
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1. Dashboard
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/dashboard")
def comm_dashboard(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Aggregate KPI counts from existing data sources."""

    def _count(model: Any, *conds: Any) -> int:
        stmt = select(func.count(model.id))
        for c in conds:
            stmt = stmt.where(c)
        return db.execute(stmt).scalar_one()

    return {
        "active_suppliers": _count(SupplierMaster, SupplierMaster.is_active.is_(True)),
        "active_pos": _count(ProcurementRecord),
        "draft_mails": _count(MailHistory, MailHistory.sent_status == "DRAFT"),
        "sent_mails": _count(MailHistory, MailHistory.sent_status != "DRAFT"),
        "open_tasks": _count(CommunicationTask, CommunicationTask.status != "DONE"),
        "critical_escalations": _count(CommunicationTask, CommunicationTask.signal == "BLACK"),
        "delayed_pos": _count(ProcurementRecord, ProcurementRecord.signal.in_(["RED", "BLACK"])),
        "waiting_supplier": _count(CommunicationTask, CommunicationTask.status == "WAITING_SUPPLIER"),
        "unread_inbound": _count(
            CommunicationMessage,
            CommunicationMessage.direction == "INCOMING",
            CommunicationMessage.read_at.is_(None),
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 2. Suppliers list
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/suppliers")
def list_suppliers(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    """
    Live supplier list from supplier_master enriched with PO / mail / task aggregates.
    Also surfaces procurement_records suppliers not yet in master.
    """
    masters = db.scalars(
        select(SupplierMaster).where(SupplierMaster.is_active.is_(True))
    ).all()
    master_by_upper: dict[str, SupplierMaster] = {
        m.supplier_name.strip().upper(): m for m in masters
    }

    po_names: list[str] = list(
        db.execute(select(ProcurementRecord.supplier_name).distinct()).scalars().all()
    )
    extra_names: list[str] = sorted(
        {
            n.strip()
            for n in po_names
            if n and n.strip().upper() not in master_by_upper
        }
    )

    result: list[dict[str, Any]] = []
    for m in masters:
        result.append(_build_supplier_entry(db, m.id, m.supplier_name))
    for name in extra_names:
        result.append(_build_supplier_entry(db, None, name))

    result.sort(
        key=lambda s: (
            -_SIGNAL_RANK.get(_norm_signal(s["highest_signal"]), 1),
            -(1 if s["last_activity_at"] else 0),
        )
    )
    return result


def _build_supplier_entry(
    db: Session, supplier_id: Optional[int], supplier_name: str
) -> dict[str, Any]:
    upper = supplier_name.strip().upper()

    pos = db.scalars(
        select(ProcurementRecord).where(
            func.upper(ProcurementRecord.supplier_name) == upper
        )
    ).all()

    mails = db.scalars(
        select(MailHistory)
        .where(func.upper(MailHistory.supplier_name) == upper)
        .order_by(MailHistory.created_at.desc())
    ).all()

    open_task_count: int = db.execute(
        select(func.count(CommunicationTask.id)).where(
            func.upper(CommunicationTask.supplier_name) == upper,
            CommunicationTask.status != "DONE",
        )
    ).scalar_one()

    mapping_status = "NO_EMAIL"
    if supplier_id:
        email_row = db.scalar(
            select(SupplierEmail).where(
                SupplierEmail.supplier_id == supplier_id,
                SupplierEmail.is_active.is_(True),
            )
        )
        if email_row:
            mapping_status = "OK"

    po_signals = [_norm_signal(p.signal) for p in pos]
    mail_signals = [_signal_from_mail_type(m.mail_type) for m in mails]
    highest = _worst_signal(po_signals + mail_signals) if (po_signals or mail_signals) else "GREEN"
    latest = mails[0] if mails else None
    draft_count = sum(1 for m in mails if m.sent_status == "DRAFT")

    return {
        "supplier_id": supplier_id,
        "supplier_name": supplier_name,
        "last_subject": latest.subject if latest else None,
        "last_activity_at": latest.created_at.isoformat() if latest else None,
        "open_po_count": len(pos),
        "mail_count": len(mails),
        "draft_mail_count": draft_count,
        "task_count": open_task_count,
        "highest_signal": highest,
        "health_score": _HEALTH.get(highest, 65),
        "mapping_status": mapping_status,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 3. PO lists (two routes: by supplier_id and by supplier_name fallback)
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/suppliers/{supplier_id}/purchase-orders")
def supplier_pos_by_id(
    supplier_id: int, db: Session = Depends(get_db)
) -> list[dict[str, Any]]:
    """POs for a supplier identified by supplier_master.id."""
    supplier = db.get(SupplierMaster, supplier_id)
    if not supplier:
        raise HTTPException(404, "Supplier not found")
    return _pos_for_supplier(db, supplier_id, supplier.supplier_name)


@router.get("/purchase-orders")
def pos_by_supplier_name(
    supplier_name: str = Query(...),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """POs for a supplier identified by name (fallback for suppliers without master entry)."""
    master = db.scalar(
        select(SupplierMaster).where(
            func.upper(SupplierMaster.supplier_name) == supplier_name.strip().upper()
        )
    )
    return _pos_for_supplier(db, master.id if master else None, supplier_name)


def _pos_for_supplier(
    db: Session, supplier_id: Optional[int], supplier_name: str
) -> list[dict[str, Any]]:
    """Return one entry per (supplier_po_no) for the supplier, materials nested inside."""
    upper = supplier_name.strip().upper()
    records = db.scalars(
        select(ProcurementRecord)
        .where(func.upper(ProcurementRecord.supplier_name) == upper)
        .order_by(ProcurementRecord.shipment_date)
    ).all()

    buckets: dict[str, list[ProcurementRecord]] = {}
    for rec in records:
        if not rec.supplier_po_no:
            continue
        buckets.setdefault(rec.supplier_po_no, []).append(rec)

    result: list[dict[str, Any]] = []
    for po_no, items in buckets.items():
        group = po_followup_service.build_po_group_payload(
            db, items, supplier_name, po_no
        )
        record_ids = group["procurement_record_ids"]
        mail_count: int = db.execute(
            select(func.count(MailHistory.id)).where(
                MailHistory.procurement_record_id.in_(record_ids)
            )
        ).scalar_one() if record_ids else 0
        open_task_count: int = db.execute(
            select(func.count(CommunicationTask.id)).where(
                CommunicationTask.procurement_record_id.in_(record_ids),
                CommunicationTask.status != "DONE",
            )
        ).scalar_one() if record_ids else 0
        # Unread inbound supplier replies for this PO — WhatsApp-style badge.
        unread_inbound: int = db.execute(
            select(func.count(CommunicationMessage.id)).where(
                CommunicationMessage.direction == "INCOMING",
                CommunicationMessage.read_at.is_(None),
                or_(
                    CommunicationMessage.procurement_record_id.in_(record_ids)
                    if record_ids
                    else False,
                    CommunicationMessage.supplier_po_no == po_no,
                ),
            )
        ).scalar_one() or 0
        latest_mail = db.scalar(
            select(MailHistory)
            .where(MailHistory.procurement_record_id.in_(record_ids))
            .order_by(MailHistory.created_at.desc())
            .limit(1)
        ) if record_ids else None
        latest_inbound = db.scalar(
            select(CommunicationMessage)
            .where(
                CommunicationMessage.direction == "INCOMING",
                or_(
                    CommunicationMessage.procurement_record_id.in_(record_ids)
                    if record_ids
                    else False,
                    CommunicationMessage.supplier_po_no == po_no,
                ),
            )
            .order_by(CommunicationMessage.created_at.desc())
            .limit(1)
        )
        signal = _norm_signal(group["overall_signal"])
        result.append(
            {
                # legacy keys kept for the existing frontend table
                "procurement_record_id": group["anchor_record_id"],
                "supplier_id": supplier_id or group.get("supplier_id"),
                "supplier_name": supplier_name,
                "supplier_po_no": po_no,
                "material_name": f"ALL MATERIALS ({group['material_count']})",
                "qty": sum(
                    (float(m.get("po_qty")) for m in group["materials"] if m.get("po_qty") is not None),
                    0.0,
                ) or None,
                "shipment_date": group.get("earliest_due_date"),
                "signal": signal,
                "risk_level": _RISK_LEVEL.get(signal, "MEDIUM"),
                "mail_count": mail_count,
                "task_count": open_task_count,
                "unread_inbound": int(unread_inbound or 0),
                "latest_inbound_at": latest_inbound.created_at.isoformat()
                if latest_inbound
                else None,
                "last_activity_at": latest_mail.created_at.isoformat()
                if latest_mail
                else None,
                # new PO-wise payload
                "material_count": group["material_count"],
                "materials": group["materials"],
                "procurement_record_ids": record_ids,
            }
        )

    rank_dir = {"BLACK": 0, "RED": 1, "YELLOW": 2, "GREEN": 3}
    result.sort(
        key=lambda r: (
            rank_dir.get(_norm_signal(r["signal"]), 3),
            r.get("shipment_date") or "9999-99-99",
        )
    )
    return result


# ─────────────────────────────────────────────────────────────────────────────
# 4. PO Thread
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/thread")
def get_thread(
    supplier_id: Optional[int] = None,
    procurement_record_id: Optional[int] = None,
    supplier_po_no: Optional[str] = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Build conversation thread from existing mail_history for a given PO."""
    stmt = select(MailHistory)
    selected_rec: Optional[ProcurementRecord] = None
    po_scoped_record_ids: list[int] = []

    if procurement_record_id is not None:
        selected_rec = db.get(ProcurementRecord, procurement_record_id)
        if selected_rec and selected_rec.supplier_po_no:
            scoped_stmt = select(ProcurementRecord.id).where(
                ProcurementRecord.supplier_po_no == selected_rec.supplier_po_no
            )
            if selected_rec.supplier_name:
                scoped_stmt = scoped_stmt.where(
                    func.upper(ProcurementRecord.supplier_name)
                    == selected_rec.supplier_name.strip().upper()
                )
            po_scoped_record_ids = list(db.execute(scoped_stmt).scalars().all())

    if procurement_record_id is not None and selected_rec and selected_rec.supplier_po_no:
        stmt = stmt.where(
            or_(
                MailHistory.supplier_po_no == selected_rec.supplier_po_no,
                MailHistory.procurement_record_id.in_(
                    po_scoped_record_ids or [procurement_record_id]
                ),
            )
        )
        if selected_rec.supplier_name:
            stmt = stmt.where(
                func.upper(MailHistory.supplier_name)
                == selected_rec.supplier_name.strip().upper()
            )
    elif procurement_record_id is not None:
        stmt = stmt.where(MailHistory.procurement_record_id == procurement_record_id)
    elif supplier_id is not None and supplier_po_no:
        sup = db.get(SupplierMaster, supplier_id)
        if sup:
            stmt = stmt.where(
                func.upper(MailHistory.supplier_name) == sup.supplier_name.strip().upper(),
                MailHistory.supplier_po_no == supplier_po_no,
            )
        else:
            stmt = stmt.where(MailHistory.supplier_po_no == supplier_po_no)
    elif supplier_po_no:
        stmt = stmt.where(MailHistory.supplier_po_no == supplier_po_no)
    else:
        return _empty_thread(supplier_id, procurement_record_id, supplier_po_no)

    mails = db.scalars(stmt.order_by(MailHistory.created_at.asc())).all()

    rec: Optional[ProcurementRecord] = None
    if procurement_record_id is not None:
        rec = selected_rec or db.get(ProcurementRecord, procurement_record_id)
    elif mails:
        rec = db.get(ProcurementRecord, mails[0].procurement_record_id)

    if rec:
        signal = _norm_signal(rec.signal)
        sname = rec.supplier_name
        s_po_no = rec.supplier_po_no
        s_id = supplier_id or (mails[0].supplier_id if mails else None)
        rec_id = rec.id
    elif mails:
        mail_sigs = [_signal_from_mail_type(m.mail_type) for m in mails]
        signal = _worst_signal(mail_sigs)
        sname = mails[0].supplier_name
        s_po_no = mails[0].supplier_po_no
        s_id = supplier_id or mails[0].supplier_id
        rec_id = mails[0].procurement_record_id
    else:
        # No procurement record and no legacy mail history — fall back to
        # communication_messages so newly-fetched supplier replies still surface.
        fallback = _load_comm_messages(db, procurement_record_id, supplier_po_no)
        if not fallback:
            return _empty_thread(supplier_id, procurement_record_id, supplier_po_no)
        first = fallback[0]
        signal = "GREEN"
        sname = first.supplier_name
        s_po_no = first.supplier_po_no or supplier_po_no
        s_id = supplier_id or first.supplier_id
        rec_id = first.procurement_record_id or 0

    po_group = (
        po_followup_service.get_po_group(db, sname, s_po_no)
        if sname and s_po_no
        else None
    )
    po_table_rows = _po_message_table_rows(po_group)

    messages = [
        {
            "id": m.id,
            "procurement_record_id": m.procurement_record_id,
            "supplier_id": m.supplier_id,
            "supplier_name": m.supplier_name,
            "supplier_po_no": m.supplier_po_no,
            "material_name": m.material_name,
            "to_emails": m.to_emails,
            "cc_emails": m.cc_emails,
            "bcc_emails": m.bcc_emails,
            "escalation_emails": m.escalation_emails,
            "subject": m.subject,
            "body": m.body,
            "mail_type": m.mail_type,
            "sent_status": m.sent_status,
            "created_at": m.created_at.isoformat(),
            "sent_at": m.sent_at.isoformat() if m.sent_at else None,
            "remarks": m.remarks,
            "signal": _signal_from_mail_type(m.mail_type),
            "source": "mail_history",
            "direction": "OUTGOING",
            "table_format": "PO_MATERIALS"
            if _is_po_group_mail(m) and po_table_rows
            else None,
            "table_rows": po_table_rows if _is_po_group_mail(m) else [],
        }
        for m in mails
    ]

    # Merge CommunicationMessage rows (new pipeline) for the same PO/record.
    comm_msgs = _load_comm_messages(db, rec_id, s_po_no)
    for cm in comm_msgs:
        reply_rows = _reply_message_table_rows(cm.body)
        outgoing_po_rows = (
            po_table_rows
            if cm.direction == "OUTGOING"
            and (cm.mail_type or "").strip().upper().startswith("PO_")
            else []
        )
        echoed_po_rows = (
            _merge_po_and_reply_rows(po_table_rows, reply_rows)
            if cm.direction == "INCOMING"
            and po_table_rows
            and (
                _looks_like_po_draft_echo(cm.body)
                or _reply_rows_match_po(po_table_rows, reply_rows)
            )
            else []
        )
        messages.append(
            {
                "id": f"cm-{cm.id}",
                "procurement_record_id": cm.procurement_record_id,
                "supplier_id": cm.supplier_id,
                "supplier_name": cm.supplier_name,
                "supplier_po_no": cm.supplier_po_no,
                "material_name": None,
                "to_emails": cm.to_emails,
                "cc_emails": cm.cc_emails,
                "bcc_emails": cm.bcc_emails,
                "escalation_emails": [],
                "subject": cm.subject,
                "body": cm.body,
                "mail_type": cm.mail_type,
                "sent_status": cm.status,
                "created_at": cm.created_at.isoformat(),
                "sent_at": cm.sent_at.isoformat() if cm.sent_at else None,
                "received_at": cm.received_at.isoformat() if cm.received_at else None,
                "sender_email": cm.sender_email,
                "receiver_email": cm.receiver_email,
                "remarks": None,
                "signal": _signal_from_mail_type(cm.mail_type or ""),
                "source": "communication_messages",
                "direction": cm.direction,
                "parsed": {
                    "status": cm.parsed_status,
                    "qty": float(cm.parsed_qty) if cm.parsed_qty is not None else None,
                    "date": cm.parsed_date.isoformat() if cm.parsed_date else None,
                },
                "error_message": cm.error_message,
                "table_format": "PO_MATERIALS"
                if outgoing_po_rows
                else "PO_MATERIALS"
                if echoed_po_rows
                else "SUPPLIER_REPLY"
                if reply_rows
                else None,
                "table_rows": outgoing_po_rows or echoed_po_rows or reply_rows,
            }
        )

    messages.sort(key=lambda x: x.get("created_at") or "")

    return {
        "thread_id": f"COMM-{rec_id}",
        "supplier_id": s_id,
        "supplier_name": sname,
        "procurement_record_id": rec_id,
        "supplier_po_no": s_po_no,
        "signal": signal,
        "risk_level": _RISK_LEVEL.get(signal, "MEDIUM"),
        "messages": messages,
    }


@router.post("/thread/mark-read")
def mark_thread_read(
    supplier_po_no: Optional[str] = None,
    procurement_record_id: Optional[int] = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Mark all inbound supplier mails in a thread as read (clears the unread badge)."""
    if not supplier_po_no and not procurement_record_id:
        raise HTTPException(400, "Provide supplier_po_no or procurement_record_id")
    now = datetime.utcnow()
    stmt = select(CommunicationMessage).where(
        CommunicationMessage.direction == "INCOMING",
        CommunicationMessage.read_at.is_(None),
    )
    if supplier_po_no and procurement_record_id is not None:
        stmt = stmt.where(
            or_(
                CommunicationMessage.supplier_po_no == supplier_po_no,
                CommunicationMessage.procurement_record_id == procurement_record_id,
            )
        )
    elif supplier_po_no:
        stmt = stmt.where(CommunicationMessage.supplier_po_no == supplier_po_no)
    else:
        stmt = stmt.where(
            CommunicationMessage.procurement_record_id == procurement_record_id
        )
    rows = list(db.scalars(stmt).all())
    for row in rows:
        row.read_at = now
    db.commit()
    return {"marked": len(rows), "at": now.isoformat()}


def _empty_thread(
    supplier_id: Optional[int],
    procurement_record_id: Optional[int],
    supplier_po_no: Optional[str],
) -> dict[str, Any]:
    return {
        "thread_id": "COMM-0",
        "supplier_id": supplier_id,
        "supplier_name": None,
        "procurement_record_id": procurement_record_id,
        "supplier_po_no": supplier_po_no,
        "signal": "GREEN",
        "risk_level": "LOW",
        "messages": [],
    }


def _load_comm_messages(
    db: Session,
    procurement_record_id: Optional[int],
    supplier_po_no: Optional[str],
) -> list[CommunicationMessage]:
    stmt = select(CommunicationMessage)
    if procurement_record_id is not None and supplier_po_no:
        stmt = stmt.where(
            (CommunicationMessage.procurement_record_id == procurement_record_id)
            | (CommunicationMessage.supplier_po_no == supplier_po_no)
        )
    elif procurement_record_id is not None:
        stmt = stmt.where(CommunicationMessage.procurement_record_id == procurement_record_id)
    elif supplier_po_no:
        stmt = stmt.where(CommunicationMessage.supplier_po_no == supplier_po_no)
    else:
        return []
    return list(
        db.scalars(stmt.order_by(CommunicationMessage.created_at.asc())).all()
    )


# ─────────────────────────────────────────────────────────────────────────────
# 5. Tasks (grouped by status)
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/tasks")
def get_hub_tasks(
    supplier_id: Optional[int] = None,
    procurement_record_id: Optional[int] = None,
    supplier_po_no: Optional[str] = None,
    db: Session = Depends(get_db),
) -> dict[str, list[dict[str, Any]]]:
    """Return communication tasks for the given context, grouped by status."""
    stmt = select(CommunicationTask)
    if supplier_id is not None:
        stmt = stmt.where(CommunicationTask.supplier_id == supplier_id)
    if procurement_record_id is not None:
        stmt = stmt.where(CommunicationTask.procurement_record_id == procurement_record_id)
    if supplier_po_no:
        stmt = stmt.where(CommunicationTask.supplier_po_no == supplier_po_no)

    all_tasks = db.scalars(stmt.order_by(CommunicationTask.created_at.desc())).all()

    grouped: dict[str, list[dict[str, Any]]] = {
        "todo": [],
        "waiting_supplier": [],
        "in_progress": [],
        "done": [],
    }
    for t in all_tasks:
        entry = _task_dict(t)
        s = (t.status or "TODO").upper()
        if s == "TODO":
            grouped["todo"].append(entry)
        elif s == "WAITING_SUPPLIER":
            grouped["waiting_supplier"].append(entry)
        elif s == "IN_PROGRESS":
            grouped["in_progress"].append(entry)
        else:
            grouped["done"].append(entry)
    return grouped


def _task_dict(t: CommunicationTask) -> dict[str, Any]:
    return {
        "id": t.id,
        "title": t.title,
        "description": t.description,
        "supplier_id": t.supplier_id,
        "supplier_name": t.supplier_name,
        "supplier_po_no": t.supplier_po_no,
        "procurement_record_id": t.procurement_record_id,
        "linked_mail_id": t.linked_mail_id,
        "assigned_to": t.assigned_to,
        "assigned_by": t.assigned_by,
        "watchers": t.watchers or [],
        "priority": t.priority,
        "status": t.status,
        "signal": t.signal,
        "due_date": t.due_date.isoformat() if t.due_date else None,
        "reminder_at": t.reminder_at.isoformat() if t.reminder_at else None,
        "closed_at": t.closed_at.isoformat() if t.closed_at else None,
        "comments_count": t.comments_count,
        "attachment_count": t.attachment_count,
        "created_at": t.created_at.isoformat(),
        "updated_at": t.updated_at.isoformat(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 6. Create task
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/tasks", status_code=201)
def create_hub_task(
    payload: CommunicationTaskCreate, db: Session = Depends(get_db)
) -> dict[str, Any]:
    """Create a communication task. Only writes to communication_tasks table."""
    _validate_enum("priority", payload.priority or "P2", TASK_PRIORITIES)
    _validate_enum("status", payload.status or "TODO", TASK_STATUSES)
    _validate_enum("signal", payload.signal or "YELLOW", TASK_SIGNALS)

    row = CommunicationTask(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return _task_dict(row)


# ─────────────────────────────────────────────────────────────────────────────
# 7. Update task
# ─────────────────────────────────────────────────────────────────────────────
@router.patch("/tasks/{task_id}")
def update_hub_task(
    task_id: int,
    payload: CommunicationTaskUpdate,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Update a communication task. Only touches communication_tasks table."""
    row = db.get(CommunicationTask, task_id)
    if not row:
        raise HTTPException(404, "Task not found")

    data = payload.model_dump(exclude_unset=True)
    if "priority" in data:
        _validate_enum("priority", data["priority"], TASK_PRIORITIES)
    if "status" in data:
        _validate_enum("status", data["status"], TASK_STATUSES)
    if "signal" in data:
        _validate_enum("signal", data["signal"], TASK_SIGNALS)

    for key, value in data.items():
        setattr(row, key, value)

    if data.get("status") == "DONE" and not row.closed_at:
        row.closed_at = datetime.utcnow()
    elif "status" in data and data["status"] != "DONE":
        row.closed_at = None

    db.commit()
    db.refresh(row)
    return _task_dict(row)


# ─────────────────────────────────────────────────────────────────────────────
# 8. AI Reply (uses existing follow-up engine; does NOT save a new draft)
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/ai-reply")
def ai_reply(
    procurement_record_id: int = Query(...),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """
    Generate an AI reply body from the existing follow-up engine.
    Returns subject + body for the frontend composer. Does not persist anything.
    """
    rec = db.get(ProcurementRecord, procurement_record_id)
    if not rec:
        raise HTTPException(404, "Procurement record not found")

    apply_followup_logic(rec)
    rule = get_followup_rule(rec)
    template = pick_template(db, rec)
    ctx = build_context(rec)

    _TYPE_LABELS: dict[str, str] = {
        "GREEN_PO_RELEASE": "PO Acknowledgement",
        "YELLOW_REMINDER": "Reminder",
        "RED_DAY1": "Urgent Follow-up",
        "RED_DAY2": "Strong Follow-up",
        "AI_REQUIRED": "AI Follow-up",
        "BLACK_ESCALATION": "Critical Escalation",
        "GENERAL_FOLLOWUP": "Follow-up",
    }
    label = _TYPE_LABELS.get(rule.mail_type, "Follow-up")
    subject = (
        f"{label} | PO No. {rec.supplier_po_no} | "
        f"{rec.material_name} | {rec.supplier_name or ''}"
    )
    body = (
        render(template.body_template, ctx)
        if template
        else (
            f"Dear {rec.supplier_name or 'Supplier'},\n\n"
            f"{rule.action} is required for PO No. {rec.supplier_po_no} / {rec.material_name}.\n"
            f"Signal: {rec.signal or '-'}\n"
            f"CRM No.: {rec.crm_no}\n"
            f"Qty: {rec.qty or '-'} {rec.uom or ''}\n"
            f"Shipment Date: {rec.shipment_date or '-'}\n\n"
            "Please share the current dispatch commitment, delay reason if any, "
            "and the earliest recoverable delivery date.\n\n"
            "Regards,\nProcurement"
        )
    )
    return {"subject": subject, "body": body, "mail_type": rule.mail_type}


# ─────────────────────────────────────────────────────────────────────────────
# 9. Escalation (triggers existing mail draft pipeline + creates escalation task)
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/escalate", dependencies=[Depends(require_manager)])
def escalate(
    procurement_record_id: int = Query(...),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """
    Trigger escalation via existing mail draft logic.
    Saves a BLACK_ESCALATION DRAFT to mail_history and creates a P0 communication task.
    Does not modify procurement_records signal or any other pipeline state.
    """
    rec = db.get(ProcurementRecord, procurement_record_id)
    if not rec:
        raise HTTPException(404, "Procurement record not found")

    from ..services.mail_template_service import find_supplier_email as _find_email

    supplier = None
    if rec.supplier_name:
        supplier = db.scalar(
            select(SupplierMaster).where(SupplierMaster.supplier_name == rec.supplier_name)
        )
    mapping = _find_email(db, rec.supplier_name)

    subject = (
        f"Critical Escalation | PO No. {rec.supplier_po_no} | "
        f"{rec.material_name} | {rec.supplier_name or ''}"
    )
    body = (
        f"Dear {rec.supplier_name or 'Supplier'},\n\n"
        f"This is a critical escalation for PO No. {rec.supplier_po_no} — "
        f"{rec.material_name}.\n"
        "The delay is impacting our production line and requires immediate action.\n\n"
        f"Signal: BLACK\nCRM No.: {rec.crm_no}\n\n"
        "Please respond with an updated delivery commitment within 24 hours.\n\n"
        "Regards,\nProcurement Leadership"
    )

    history = MailHistory(
        procurement_record_id=rec.id,
        supplier_id=supplier.id if supplier else None,
        supplier_name=rec.supplier_name,
        supplier_po_no=rec.supplier_po_no,
        material_name=rec.material_name,
        to_emails=mapping.to_emails if mapping else [],
        cc_emails=mapping.cc_emails if mapping else [],
        bcc_emails=mapping.bcc_emails if mapping else [],
        escalation_emails=mapping.escalation_emails if mapping else [],
        subject=subject,
        body=body,
        mail_type="BLACK_ESCALATION",
        sent_status="READY",
    )
    db.add(history)
    db.flush()
    msg_service.queue_outgoing_message(
        db,
        supplier_id=supplier.id if supplier else None,
        supplier_name=rec.supplier_name,
        procurement_record_id=rec.id,
        supplier_po_no=rec.supplier_po_no,
        subject=subject,
        body=body,
        to_emails=mapping.to_emails if mapping else [],
        cc_emails=mapping.cc_emails if mapping else [],
        bcc_emails=mapping.bcc_emails if mapping else [],
        mail_type="BLACK_ESCALATION",
        mail_history_id=history.id,
        commit=False,
    )
    rec.mail_status = "READY"

    task = CommunicationTask(
        supplier_id=supplier.id if supplier else None,
        supplier_name=rec.supplier_name,
        supplier_po_no=rec.supplier_po_no,
        procurement_record_id=rec.id,
        linked_mail_id=history.id,
        title=f"Escalation: PO #{rec.supplier_po_no} — {rec.material_name}",
        description="Auto-escalation triggered from Communication Hub.",
        priority="P0",
        status="TODO",
        signal="BLACK",
        assigned_to="Purchase Head",
        assigned_by="System",
        watchers=["Sourcing Head"],
    )
    db.add(task)
    db.commit()
    db.refresh(history)
    db.refresh(task)

    return {
        "message": "Escalation triggered",
        "mail_draft_id": history.id,
        "task_id": task.id,
        "subject": subject,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 10. Direct Send Mail (queues a draft + triggers SMTP worker immediately)
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/send-mail", dependencies=[Depends(require_manager)])
def send_mail_now(
    mail_history_id: int = Query(..., description="MailHistory row to send"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Queue the given mail draft and invoke the SMTP send worker immediately.

    Safe to call repeatedly: if a READY OUTGOING message already exists for
    this mail_history_id, no new queue row is created.
    """
    history = db.get(MailHistory, mail_history_id)
    if history is None:
        raise HTTPException(404, "MailHistory not found")

    # Ensure a READY OUTGOING message exists for this mail history.
    existing = db.scalar(
        select(CommunicationMessage).where(
            CommunicationMessage.direction == "OUTGOING",
            CommunicationMessage.status.in_(["READY", "SENT"]),
        )
    )
    matched_existing = None
    for row in db.scalars(
        select(CommunicationMessage).where(
            CommunicationMessage.direction == "OUTGOING",
            CommunicationMessage.status == "READY",
        )
    ).all():
        payload = row.raw_payload if isinstance(row.raw_payload, dict) else {}
        if payload.get("mail_history_id") == mail_history_id:
            matched_existing = row
            break

    if matched_existing is None:
        msg_service.queue_outgoing_message(
            db,
            supplier_id=history.supplier_id,
            supplier_name=history.supplier_name,
            procurement_record_id=history.procurement_record_id,
            supplier_po_no=history.supplier_po_no,
            subject=history.subject,
            body=history.body,
            to_emails=history.to_emails or [],
            cc_emails=history.cc_emails or [],
            bcc_emails=history.bcc_emails or [],
            mail_type=history.mail_type,
            mail_history_id=history.id,
            commit=True,
        )
        if history.sent_status not in {"SENT", "READY"}:
            history.sent_status = "READY"
            db.commit()

    from ..workers import mail_send_worker

    result = mail_send_worker.send_ready_messages(limit=5)
    return {
        "mail_history_id": mail_history_id,
        "send_result": result,
    }

"""Harmony Intelligence Summary — daily admin digest.

Gathers current procurement state, renders a branded HTML email, and sends it
once per local calendar day to an admin-configured recipient list. All config
lives in AppSetting key `admin_digest` (see settings_service).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..models.communication_message import CommunicationMessage
from ..models.procurement import ProcurementRecord

log = logging.getLogger(__name__)

CRITICAL_ESCALATIONS = ("CRITICAL", "LEVEL_2")
OPEN_FOLLOWUP_STATUSES = (
    "REMINDER_DUE", "URGENT_FOLLOWUP", "STRONG_FOLLOWUP",
    "AI_FOLLOWUP", "CRITICAL_ESCALATION", "PENDING_ACK",
)


def _days_late(shipment_date: datetime | None, today: datetime) -> int | None:
    if shipment_date is None:
        return None
    delta = (today.date() - shipment_date.date()).days
    return delta if delta > 0 else 0


def _po(r: Any) -> str:
    return r.supplier_po_no or "—"


def summarize_counts(active_rows, overdue_count, critical_count, new_replies) -> dict:
    signals = {"GREEN": 0, "YELLOW": 0, "RED": 0, "BLACK": 0}
    open_followups = 0
    for r in active_rows:
        if r.signal in signals:
            signals[r.signal] += 1
        if getattr(r, "followup_status", None) in OPEN_FOLLOWUP_STATUSES:
            open_followups += 1
    return {
        "active": len(active_rows),
        "open_followups": open_followups,
        "overdue": overdue_count,
        "critical": critical_count,
        "new_replies": new_replies,
        "signals": signals,
    }


def format_critical(rows, today) -> list[dict]:
    return [{
        "po": _po(r), "supplier": r.supplier_name or "—", "material": r.material_name or "",
        "signal": (r.signal or "").title(), "days_late": _days_late(r.shipment_date, today),
        "risk": r.risk_score,
    } for r in rows]


def format_overdue(rows, today) -> list[dict]:
    out = []
    for r in rows:
        late = _days_late(r.shipment_date, today)
        status = "Due today" if late == 0 else "Overdue"
        ship = r.shipment_date.strftime("%d %b") if r.shipment_date else "—"
        out.append({"po": _po(r), "supplier": r.supplier_name or "—",
                    "shipment": ship, "status": status, "days_late": late})
    return out


def format_risk(rows) -> list[dict]:
    return [{"po": _po(r), "supplier": r.supplier_name or "—",
             "reason": r.risk_reason or "", "score": r.risk_score or 0} for r in rows]


def _gather_counts(db: Session) -> dict:
    today = datetime.utcnow()
    active = list(db.scalars(select(ProcurementRecord)).all())
    overdue = sum(1 for r in active if r.shipment_date and r.shipment_date.date() < today.date())
    critical = sum(1 for r in active
                   if r.signal == "BLACK" or r.escalation_level in CRITICAL_ESCALATIONS)
    since = today - timedelta(hours=24)
    new_replies = db.scalar(
        select(func.count()).select_from(CommunicationMessage).where(
            CommunicationMessage.direction == "INCOMING",
            CommunicationMessage.received_at >= since,
        )
    ) or 0
    return summarize_counts(active, overdue, critical, new_replies)


def _gather_critical(db: Session, limit: int) -> list[dict]:
    rows = db.scalars(
        select(ProcurementRecord)
        .where(or_(ProcurementRecord.signal == "BLACK",
                   ProcurementRecord.escalation_level.in_(CRITICAL_ESCALATIONS)))
        .order_by(ProcurementRecord.risk_score.desc().nullslast())
        .limit(limit)
    ).all()
    return format_critical(rows, datetime.utcnow())


def _gather_risk(db: Session, limit: int) -> list[dict]:
    rows = db.scalars(
        select(ProcurementRecord)
        .where(ProcurementRecord.risk_band == "HIGH")
        .order_by(ProcurementRecord.risk_score.desc().nullslast())
        .limit(limit)
    ).all()
    return format_risk(rows)


def _gather_overdue(db: Session, limit: int) -> list[dict]:
    today = datetime.utcnow()
    rows = db.scalars(
        select(ProcurementRecord)
        .where(ProcurementRecord.shipment_date.isnot(None),
               ProcurementRecord.shipment_date <= today)
        .order_by(ProcurementRecord.shipment_date.asc())
        .limit(limit)
    ).all()
    return format_overdue(rows, today)

"""Harmony Intelligence Summary — daily admin digest.

Gathers current procurement state, renders a branded HTML email, and sends it
once per local calendar day to an admin-configured recipient list. All config
lives in AppSetting key `admin_digest` (see settings_service).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from ..models.communication_message import CommunicationMessage
from ..models.procurement import ProcurementRecord
from . import ai_service

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


HEAT_TONE_LABELS = {"frustrated", "tense", "angry", "calm", "neutral"}


def _fallback_summary(counts: dict) -> str:
    s = counts["signals"]
    return (
        f"{counts['critical']} critical POs need attention and "
        f"{counts['overdue']} shipments are overdue. Signal mix is "
        f"{s['GREEN']} green / {s['YELLOW']} yellow / {s['RED']} red / {s['BLACK']} black "
        f"across {counts['active']} active POs, with {counts['open_followups']} open "
        f"follow-ups and {counts['new_replies']} new supplier replies in the last 24 hours."
    )


def _ai_summary(counts: dict, critical: list[dict], heated: list[dict]) -> str:
    if not ai_service.is_enabled():
        return _fallback_summary(counts)
    try:
        crit = "; ".join(f"{c['po']} {c['supplier']} ({c['signal']}, risk {c['risk']})"
                         for c in critical[:5]) or "none"
        heat = "; ".join(f"{h['supplier']} {h['po']} ({h['tone']})" for h in heated[:5]) or "none"
        result = ai_service.complete_json(
            system=("You are Harmony Intelligence, a procurement analyst. Write ONE concise "
                    "paragraph (max 60 words) summarizing the day's supplier delivery state. "
                    "Return JSON {\"summary\": \"...\"}. No markdown, no lists."),
            user=(f"Counts: {counts}. Most critical: {crit}. Heated threads: {heat}."),
            temperature=0.3,
        )
        text = (result or {}).get("summary", "").strip()
        return text or _fallback_summary(counts)
    except Exception:  # noqa: BLE001
        log.exception("admin digest AI summary failed; using fallback")
        return _fallback_summary(counts)


def rank_heated_candidates(rows) -> list:
    """rows: objects with .recent_count, .msg_count, .escalation_level."""
    esc_weight = {"CRITICAL": 3, "LEVEL_2": 2, "LEVEL_1": 1, "NONE": 0}
    return sorted(
        rows,
        key=lambda r: (r.recent_count * 2 + r.msg_count
                       + esc_weight.get(getattr(r, "escalation_level", "NONE"), 0)),
        reverse=True,
    )


def _gather_heated(db: Session, limit: int) -> list[dict]:
    """Rank PO threads by recent activity, then LLM-score tone (fallback: heuristic)."""
    since = datetime.utcnow() - timedelta(hours=24)
    # Aggregate per-PO message activity.
    agg = db.execute(
        select(
            CommunicationMessage.supplier_po_no,
            CommunicationMessage.supplier_name,
            func.count().label("msg_count"),
            func.sum(case((CommunicationMessage.received_at >= since, 1), else_=0)
                     ).label("recent_count"),
        )
        .where(CommunicationMessage.supplier_po_no.isnot(None))
        .group_by(CommunicationMessage.supplier_po_no, CommunicationMessage.supplier_name)
        .order_by(func.count().desc())
        .limit(max(limit * 3, 6))
    ).all()
    candidates = [
        type("C", (), {"supplier_po_no": a[0], "supplier_name": a[1],
                       "msg_count": int(a[2] or 0), "recent_count": int(a[3] or 0),
                       "escalation_level": "NONE"})()
        for a in agg
    ]
    ranked = rank_heated_candidates(candidates)[:limit]
    out: list[dict] = []
    for c in ranked:
        try:
            tone, score, quote = _score_tone(db, c)
        except Exception:  # noqa: BLE001
            log.exception("_score_tone failed for %s; skipping", c.supplier_po_no)
            continue
        if tone in ("frustrated", "tense", "angry"):
            out.append({"supplier": c.supplier_name or "—", "po": c.supplier_po_no or "—",
                        "tone": tone.title(), "score": score,
                        "msg_count": c.msg_count, "recent_count": c.recent_count, "quote": quote})
    return out


def _score_tone(db: Session, candidate) -> tuple[str, float, str | None]:
    """Return (tone, score, quote). LLM if enabled, else heuristic by activity."""
    last = db.scalars(
        select(CommunicationMessage)
        .where(CommunicationMessage.supplier_po_no == candidate.supplier_po_no,
               CommunicationMessage.direction == "INCOMING")
        .order_by(CommunicationMessage.received_at.desc().nullslast())
        .limit(1)
    ).first()
    quote = (last.body or "")[:160].strip() if last and last.body else None
    if not ai_service.is_enabled() or not quote:
        # Heuristic: lots of recent back-and-forth reads as tense.
        tone = "tense" if candidate.recent_count >= 3 else "neutral"
        return tone, min(0.6, 0.2 + candidate.recent_count * 0.1), quote
    try:
        result = ai_service.complete_json(
            system=("Classify the tone of this supplier message. Return JSON "
                    "{\"tone\": one of [calm, neutral, tense, frustrated, angry], "
                    "\"score\": 0..1}."),
            user=quote,
            temperature=0.0,
        )
        tone = str((result or {}).get("tone", "neutral")).lower()
        if tone not in HEAT_TONE_LABELS:
            tone = "neutral"
        score = float((result or {}).get("score", 0.5) or 0.5)
        return tone, round(score, 2), quote
    except Exception:  # noqa: BLE001
        log.exception("admin digest tone scoring failed; using heuristic")
        tone = "tense" if candidate.recent_count >= 3 else "neutral"
        return tone, min(0.6, 0.2 + candidate.recent_count * 0.1), quote

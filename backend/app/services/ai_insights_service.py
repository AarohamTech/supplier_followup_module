"""AI / analytics insights: predictive delay risk, supplier scorecards, mail
triage persistence and thread summaries.

Risk and scorecards are deterministic heuristics (fast, no LLM, safe to run on a
cron). Triage and summaries use the LLM when enabled and fall back to keyword
heuristics so they always produce a result.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models.communication_message import CommunicationMessage
from ..models.customer_mail import CustomerMail
from ..models.procurement import ProcurementRecord
from . import ai_service

log = logging.getLogger(__name__)

_DONE_FOLLOWUP = {"CLOSED", "DONE", "COMPLETED", "RESOLVED", "CANCELLED"}
_DELIVERED_STATUS = {"DISPATCHED", "DELIVERED", "CLOSED", "COMPLETED", "RECEIVED"}
_BASE_BY_SIGNAL = {"GREEN": 5, "YELLOW": 35, "RED": 70, "BLACK": 90}


# ── Predictive delay risk (heuristic) ────────────────────────────────────────
def _days_past(when: datetime | date | None, now: datetime) -> int | None:
    if when is None:
        return None
    if isinstance(when, datetime):
        return (now - when).days
    return (now.date() - when).days


def compute_delay_risk(rec: ProcurementRecord, now: datetime) -> tuple[int, str, str]:
    """Return (score 0-100, band LOW/MEDIUM/HIGH, reason) for one record."""
    signal = (rec.signal or "GREEN").upper()
    score = _BASE_BY_SIGNAL.get(signal, 15)
    reasons: list[str] = []
    if signal in {"RED", "BLACK"}:
        reasons.append(f"{signal} signal")

    # Overdue / approaching due date (ship date first, else commitment date).
    due_over = _days_past(rec.shipment_date, now)
    if due_over is None:
        due_over = _days_past(rec.commitment_date, now)
    if due_over is not None:
        if due_over > 0:
            score += min(30, due_over * 3)
            reasons.append(f"{due_over}d past due")
        elif due_over >= -7:
            score += 12
            reasons.append("due within 7 days")

    if rec.commitment_date is None and rec.shipment_date is not None:
        if (_days_past(rec.shipment_date, now) or -99) > -14:
            score += 8
            reasons.append("no commitment date on file")

    fc = rec.followup_count or 0
    if fc >= 3:
        score += 12
        reasons.append(f"{fc} follow-ups sent")
    elif fc >= 1:
        score += 5

    if (rec.followup_status or "").upper() not in _DONE_FOLLOWUP and rec.last_followup_date:
        stale = _days_past(rec.last_followup_date, now) or 0
        if stale >= 5:
            score += 10
            reasons.append(f"no update in {stale}d")

    esc = (rec.escalation_level or "NONE").upper()
    if esc not in {"NONE", ""}:
        score += 10
        reasons.append(f"escalation {esc}")

    if rec.ai_required:
        score += 5

    score = max(0, min(100, int(round(score))))
    band = "HIGH" if score >= 66 else "MEDIUM" if score >= 33 else "LOW"
    reason = ", ".join(reasons[:4]) or "stable"
    return score, band, reason


def rescore_all(db: Session) -> dict[str, Any]:
    """Recompute risk for every procurement record. Heuristic — no LLM."""
    now = datetime.utcnow()
    records = db.scalars(select(ProcurementRecord)).all()
    by_band: dict[str, int] = {"LOW": 0, "MEDIUM": 0, "HIGH": 0}
    for rec in records:
        score, band, reason = compute_delay_risk(rec, now)
        rec.risk_score = score
        rec.risk_band = band
        rec.risk_reason = reason
        rec.risk_scored_at = now
        by_band[band] = by_band.get(band, 0) + 1
    db.commit()
    return {"updated": len(records), "by_band": by_band, "ran_at": now.isoformat()}


def list_delay_risk(
    db: Session, *, band: str | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    """Top at-risk POs (aggregated to one row per supplier+PO, highest score)."""
    stmt = select(ProcurementRecord).where(ProcurementRecord.risk_score.isnot(None))
    if band:
        stmt = stmt.where(func.upper(ProcurementRecord.risk_band) == band.upper())
    records = db.scalars(stmt).all()

    buckets: dict[tuple[str, str], dict[str, Any]] = {}
    now = datetime.utcnow()
    for rec in records:
        if not rec.supplier_po_no:
            continue
        key = ((rec.supplier_name or "").strip().upper(), rec.supplier_po_no.strip())
        item = buckets.get(key)
        due_iso = rec.shipment_date.isoformat() if rec.shipment_date else (
            rec.commitment_date.isoformat() if rec.commitment_date else None
        )
        if item is None:
            buckets[key] = {
                "supplier_name": rec.supplier_name,
                "supplier_po_no": rec.supplier_po_no,
                "risk_score": rec.risk_score or 0,
                "risk_band": rec.risk_band,
                "risk_reason": rec.risk_reason,
                "signal": (rec.signal or "GREEN").upper(),
                "earliest_due_date": due_iso,
                "material_count": 1,
                "at_risk_materials": 1 if (rec.risk_band or "") in {"HIGH", "MEDIUM"} else 0,
            }
        else:
            item["material_count"] += 1
            if (rec.risk_band or "") in {"HIGH", "MEDIUM"}:
                item["at_risk_materials"] += 1
            if (rec.risk_score or 0) > item["risk_score"]:
                item["risk_score"] = rec.risk_score or 0
                item["risk_band"] = rec.risk_band
                item["risk_reason"] = rec.risk_reason
                item["signal"] = (rec.signal or "GREEN").upper()
            if due_iso and (item["earliest_due_date"] is None or due_iso < item["earliest_due_date"]):
                item["earliest_due_date"] = due_iso

    items = sorted(buckets.values(), key=lambda x: x["risk_score"], reverse=True)
    for it in items:
        due = it.get("earliest_due_date")
        it["days_late"] = None
        if due:
            try:
                it["days_late"] = (now.date() - datetime.fromisoformat(due).date()).days
            except ValueError:
                it["days_late"] = None
    return items[:limit]


# ── Supplier performance scorecards (heuristic) ──────────────────────────────
def _grade(score: int) -> str:
    return "A" if score >= 80 else "B" if score >= 60 else "C" if score >= 40 else "D"


def supplier_scorecards(
    db: Session, *, name: str | None = None, limit: int = 100
) -> list[dict[str, Any]]:
    """Compute a performance scorecard per supplier using grouped queries."""
    now = datetime.utcnow()

    sig_stmt = (
        select(
            ProcurementRecord.supplier_name,
            func.upper(ProcurementRecord.signal),
            func.count(ProcurementRecord.id),
        )
        .where(ProcurementRecord.supplier_name.isnot(None))
        .group_by(ProcurementRecord.supplier_name, func.upper(ProcurementRecord.signal))
    )
    if name:
        sig_stmt = sig_stmt.where(func.upper(ProcurementRecord.supplier_name) == name.strip().upper())

    suppliers: dict[str, dict[str, Any]] = {}
    for sup, sig, cnt in db.execute(sig_stmt).all():
        if not sup:
            continue
        d = suppliers.setdefault(
            sup,
            {
                "supplier_name": sup,
                "by_signal": {},
                "total_records": 0,
                "overdue": 0,
                "avg_followups": 0.0,
                "incoming_msgs": 0,
                "outgoing_msgs": 0,
                "high_risk": 0,
                "last_activity": None,
            },
        )
        d["by_signal"][sig or "UNSET"] = int(cnt)
        d["total_records"] += int(cnt)

    if not suppliers:
        return []

    names_upper = {s.upper() for s in suppliers}

    # Overdue (past ship date, not delivered) per supplier.
    overdue_rows = db.execute(
        select(ProcurementRecord.supplier_name, func.count(ProcurementRecord.id))
        .where(
            ProcurementRecord.supplier_name.isnot(None),
            ProcurementRecord.shipment_date.isnot(None),
            ProcurementRecord.shipment_date < now,
        )
        .group_by(ProcurementRecord.supplier_name)
    ).all()
    for sup, cnt in overdue_rows:
        if sup and sup in suppliers:
            suppliers[sup]["overdue"] = int(cnt)

    # Average follow-ups + high-risk count per supplier.
    avg_rows = db.execute(
        select(
            ProcurementRecord.supplier_name,
            func.avg(ProcurementRecord.followup_count),
        )
        .where(ProcurementRecord.supplier_name.isnot(None))
        .group_by(ProcurementRecord.supplier_name)
    ).all()
    for sup, avg in avg_rows:
        if sup and sup in suppliers:
            suppliers[sup]["avg_followups"] = round(float(avg or 0), 1)

    hr_rows = db.execute(
        select(ProcurementRecord.supplier_name, func.count(ProcurementRecord.id))
        .where(
            ProcurementRecord.supplier_name.isnot(None),
            func.upper(ProcurementRecord.risk_band) == "HIGH",
        )
        .group_by(ProcurementRecord.supplier_name)
    ).all()
    for sup, cnt in hr_rows:
        if sup and sup in suppliers:
            suppliers[sup]["high_risk"] = int(cnt)

    # Message volume per supplier+direction.
    msg_rows = db.execute(
        select(
            CommunicationMessage.supplier_name,
            CommunicationMessage.direction,
            func.count(CommunicationMessage.id),
        )
        .where(CommunicationMessage.supplier_name.isnot(None))
        .group_by(CommunicationMessage.supplier_name, CommunicationMessage.direction)
    ).all()
    for sup, direction, cnt in msg_rows:
        if not sup:
            continue
        if sup.upper() not in names_upper:
            continue
        # supplier_name casing may differ between tables; match case-insensitively.
        target = next((s for s in suppliers if s.upper() == sup.upper()), None)
        if target is None:
            continue
        if direction == "INCOMING":
            suppliers[target]["incoming_msgs"] += int(cnt)
        elif direction == "OUTGOING":
            suppliers[target]["outgoing_msgs"] += int(cnt)

    out: list[dict[str, Any]] = []
    for d in suppliers.values():
        total = max(1, d["total_records"])
        rb = d["by_signal"].get("RED", 0) + d["by_signal"].get("BLACK", 0)
        outgoing = d["outgoing_msgs"]
        incoming = d["incoming_msgs"]
        response_rate = round(incoming / outgoing, 2) if outgoing else None

        score = 100.0
        score -= (rb / total) * 40
        score -= (d["overdue"] / total) * 30
        score -= (d["high_risk"] / total) * 15
        if outgoing >= 3 and response_rate is not None and response_rate < 0.5:
            score -= 15
        score_int = max(0, min(100, int(round(score))))

        d["red_black"] = rb
        d["response_rate"] = response_rate
        d["score"] = score_int
        d["grade"] = _grade(score_int)
        out.append(d)

    out.sort(key=lambda x: x["score"])  # worst performers first
    return out[:limit]


# ── Triage persistence ───────────────────────────────────────────────────────
def _heuristic_triage(subject: str | None, body: str | None) -> dict[str, Any]:
    blob = f"{subject or ''} {body or ''}".lower()
    if any(k in blob for k in ("complaint", "defect", "reject", "ncr", "quality", "wrong", "damage")):
        return {"category": "COMPLAINT", "urgency": "HIGH", "action": "ESCALATE",
                "summary": (subject or "Complaint/quality issue").strip()[:160]}
    if any(k in blob for k in ("urgent", "asap", "immediately", "escalat", "overdue", "delay")):
        return {"category": "CUSTOMER", "urgency": "HIGH", "action": "REPLY",
                "summary": (subject or "Urgent customer request").strip()[:160]}
    if any(k in blob for k in ("invoice", "payment", "finance", "gst", "outstanding")):
        return {"category": "FINANCE", "urgency": "MEDIUM", "action": "REPLY",
                "summary": (subject or "Finance query").strip()[:160]}
    if any(k in blob for k in ("dispatch", "shipped", "courier", "tracking")):
        return {"category": "DISPATCH", "urgency": "LOW", "action": "MONITOR",
                "summary": (subject or "Dispatch update").strip()[:160]}
    return {"category": "GENERAL", "urgency": "MEDIUM", "action": "REPLY",
            "summary": (subject or "Customer mail").strip()[:160]}


def triage_mail(db: Session, mail: CustomerMail, *, use_ai: bool = True) -> dict[str, Any]:
    """Classify a customer mail and persist the result on the row."""
    result: dict[str, Any]
    if use_ai and ai_service.is_enabled():
        try:
            result = ai_service.triage_customer_mail(
                subject=mail.subject, body=mail.body, sender=mail.from_email
            )
        except Exception:  # noqa: BLE001
            log.exception("AI triage failed; using heuristic")
            result = _heuristic_triage(mail.subject, mail.body)
    else:
        result = _heuristic_triage(mail.subject, mail.body)

    mail.ai_category = result["category"]
    mail.ai_urgency = result["urgency"]
    mail.ai_action = result["action"]
    if result.get("summary"):
        mail.ai_summary = result["summary"]
    mail.ai_triaged_at = datetime.utcnow()
    db.commit()
    db.refresh(mail)
    return result


def summarize_customer_mail(db: Session, mail_id: int) -> str | None:
    """Summarise a customer mail + its replies; persist onto ai_summary."""
    mail = db.get(CustomerMail, mail_id)
    if mail is None:
        return None
    replies = db.scalars(
        select(CommunicationMessage)
        .where(CommunicationMessage.customer_mail_id == mail_id)
        .order_by(CommunicationMessage.created_at.asc())
    ).all()

    lines = [
        f"Customer ({mail.from_name or mail.from_email or 'unknown'}) — {mail.subject or '(no subject)'}:",
        (mail.body or "").strip(),
    ]
    for r in replies:
        who = "Us" if r.direction == "OUTGOING" else (r.sender_email or "Them")
        lines.append(f"\n{who}: {(r.body or '').strip()}")
    transcript = "\n".join(lines)

    if ai_service.is_enabled():
        try:
            summary = ai_service.summarize_thread(transcript)
        except Exception:  # noqa: BLE001
            log.exception("summarize failed; using fallback")
            summary = (mail.body or "").strip()[:200]
    else:
        summary = (mail.body or "").strip()[:200]

    mail.ai_summary = summary
    db.commit()
    return summary

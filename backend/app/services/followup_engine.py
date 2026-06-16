"""Follow-up engine: derives rule, status, AI flag, and escalation from signal + day."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from ..core.config import settings
from ..models.procurement import ProcurementRecord


@dataclass(frozen=True)
class FollowupRule:
    mail_type: str
    followup_status: str
    ai_required: bool
    escalation_level: str
    action: str


def _days_since(d: datetime | date | None) -> int:
    if d is None:
        return 0
    today = date.today()
    dd = d.date() if isinstance(d, datetime) else d
    return max((today - dd).days, 0)


def red_day_index(rec: ProcurementRecord) -> int:
    """RED escalation day, counted from when the record became RED — Day 1 = first
    day late, Day 2 = second day, etc. Falls back to Day 1 if not yet stamped."""
    if rec.red_since is None:
        return 1
    return _days_since(rec.red_since) + 1


def get_followup_rule(rec: ProcurementRecord) -> FollowupRule:
    sig = (rec.signal or "").upper()

    if sig == "GREEN":
        return FollowupRule(
            mail_type="GREEN_PO_RELEASE",
            followup_status="PENDING_ACK",
            ai_required=False,
            escalation_level="NONE",
            action="PO acknowledgement mail",
        )

    if sig == "YELLOW":
        return FollowupRule(
            mail_type="YELLOW_REMINDER",
            followup_status="REMINDER_DUE",
            ai_required=False,
            escalation_level="NONE",
            action="Reminder mail",
        )

    if sig == "RED":
        day = red_day_index(rec)
        if day <= 1:
            return FollowupRule(
                mail_type="RED_DAY1",
                followup_status="URGENT_FOLLOWUP",
                ai_required=False,
                escalation_level="LEVEL_1",
                action="Urgent follow-up",
            )
        if day <= settings.RED_AI_AFTER_DAYS:
            return FollowupRule(
                mail_type="RED_DAY2",
                followup_status="STRONG_FOLLOWUP",
                ai_required=False,
                escalation_level="LEVEL_1",
                action="Strong follow-up",
            )
        return FollowupRule(
            mail_type="AI_REQUIRED",
            followup_status="AI_FOLLOWUP",
            ai_required=True,
            escalation_level="LEVEL_2",
            action="AI follow-up",
        )

    if sig == "BLACK":
        return FollowupRule(
            mail_type="BLACK_ESCALATION",
            followup_status="CRITICAL_ESCALATION",
            ai_required=True,
            escalation_level="CRITICAL",
            action="Critical escalation",
        )

    return FollowupRule(
        mail_type="GENERAL_FOLLOWUP",
        followup_status="PENDING",
        ai_required=False,
        escalation_level="NONE",
        action="Follow-up",
    )


def apply_followup_logic(rec: ProcurementRecord, db=None) -> ProcurementRecord:
    # Stamp when the record first became RED (so the escalation day is counted
    # from "when it went late"); clear it once it's no longer RED.
    if (rec.signal or "").upper() == "RED":
        if rec.red_since is None:
            rec.red_since = datetime.utcnow()
    else:
        rec.red_since = None

    rule = get_followup_rule(rec)
    rec.ai_required = rule.ai_required
    rec.escalation_level = rule.escalation_level
    rec.followup_status = rule.followup_status
    rec.mail_status = rec.mail_status or "NOT_SENT"

    hours: int | None = None
    if db is not None:
        try:
            from . import settings_service  # local import avoids cycle at startup
            intervals = settings_service.get_followup_intervals(db)
            hours = intervals.get(rule.followup_status) or intervals.get("PENDING")
        except Exception:  # noqa: BLE001
            hours = None

    if hours is None:
        # Always schedule a next follow-up — including AI/critical — so the
        # highest-risk POs keep getting chased instead of going silent.
        hours = 24

    rec.next_followup_date = datetime.utcnow() + timedelta(hours=hours)
    return rec


def is_overdue(rec: ProcurementRecord, today: date | None = None) -> bool:
    today = today or date.today()
    if not rec.shipment_date:
        return False
    sd = rec.shipment_date.date() if isinstance(rec.shipment_date, datetime) else rec.shipment_date
    return sd < today

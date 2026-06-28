"""CRUD + scheduling math for HI-agent subscriptions.

Create-only from the agent's perspective: it makes PENDING rows; a human confirm
flips them to ACTIVE; the dispatch cron reads ACTIVE rows. No agent-facing edit
or delete lives here.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.agent_subscription import AgentSubscription

_SUMMARY_HOUR = 9  # 09:00 UTC


def compute_next_run(schedule: str | None, now: datetime) -> datetime:
    """Next dispatch time for a scheduled summary, strictly after `now`."""
    base = now.replace(hour=_SUMMARY_HOUR, minute=0, second=0, microsecond=0)
    if (schedule or "daily") == "weekly":
        # Next Monday 09:00 UTC (Monday = weekday 0).
        days = (7 - now.weekday()) % 7
        candidate = base + timedelta(days=days)
        if candidate <= now:
            candidate += timedelta(days=7)
        return candidate
    # daily
    if base <= now:
        base += timedelta(days=1)
    return base


def create_pending(
    db: Session,
    *,
    kind: str,
    supplier_id: int | None,
    procurement_record_id: int | None,
    supplier_po_no: str | None,
    recipient_user_id: int | None,
    recipient_email: str | None,
    recipient_label: str | None,
    created_by_user_id: int | None,
    schedule: str | None = None,
    commit: bool = True,
) -> AgentSubscription:
    sub = AgentSubscription(
        kind=kind,
        supplier_id=supplier_id,
        procurement_record_id=procurement_record_id,
        supplier_po_no=supplier_po_no,
        recipient_user_id=recipient_user_id,
        recipient_email=recipient_email,
        recipient_label=recipient_label,
        created_by_user_id=created_by_user_id,
        status="PENDING",
        schedule=schedule,
        last_forwarded_message_id=0,
    )
    db.add(sub)
    if commit:
        db.commit()
        db.refresh(sub)
    else:
        db.flush()
    return sub


def confirm(db: Session, subscription_id: int, *, now: datetime) -> AgentSubscription | None:
    sub = db.get(AgentSubscription, subscription_id)
    if sub is None or sub.status != "PENDING":
        return None
    sub.status = "ACTIVE"
    if sub.kind == "SCHEDULED_SUMMARY":
        sub.next_run_at = compute_next_run(sub.schedule, now)
    db.commit()
    db.refresh(sub)
    return sub


def list_for_thread(
    db: Session,
    *,
    procurement_record_id: int | None,
    supplier_po_no: str | None,
    statuses: tuple[str, ...] = ("PENDING", "ACTIVE"),
) -> list[AgentSubscription]:
    stmt = select(AgentSubscription).where(AgentSubscription.status.in_(statuses))
    if procurement_record_id is not None and supplier_po_no:
        stmt = stmt.where(
            (AgentSubscription.procurement_record_id == procurement_record_id)
            | (AgentSubscription.supplier_po_no == supplier_po_no)
        )
    elif procurement_record_id is not None:
        stmt = stmt.where(AgentSubscription.procurement_record_id == procurement_record_id)
    elif supplier_po_no:
        stmt = stmt.where(AgentSubscription.supplier_po_no == supplier_po_no)
    else:
        return []
    return list(db.scalars(stmt.order_by(AgentSubscription.created_at.asc())).all())


def list_active(db: Session, kind: str) -> list[AgentSubscription]:
    return list(
        db.scalars(
            select(AgentSubscription).where(
                AgentSubscription.status == "ACTIVE", AgentSubscription.kind == kind
            )
        ).all()
    )


def due_summaries(db: Session, now: datetime) -> list[AgentSubscription]:
    return list(
        db.scalars(
            select(AgentSubscription).where(
                AgentSubscription.status == "ACTIVE",
                AgentSubscription.kind == "SCHEDULED_SUMMARY",
                AgentSubscription.next_run_at.isnot(None),
                AgentSubscription.next_run_at <= now,
            )
        ).all()
    )


def advance_followup(db: Session, sub: AgentSubscription, last_id: int, *, commit: bool = True) -> None:
    sub.last_forwarded_message_id = last_id
    if commit:
        db.commit()


def mark_summary_dispatched(db: Session, sub: AgentSubscription, now: datetime, *, commit: bool = True) -> None:
    sub.last_run_at = now
    sub.next_run_at = compute_next_run(sub.schedule, now)
    if commit:
        db.commit()

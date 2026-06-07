"""Customer mail (non-supplier inbox) helpers."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import or_, select, func
from sqlalchemy.orm import Session

from ..models.communication_task import CommunicationTask
from ..models.customer_mail import (
    CUSTOMER_MAIL_PRIORITIES,
    CUSTOMER_MAIL_STATUSES,
    CUSTOMER_MAIL_TYPES,
    CustomerMail,
)


def list_mails(
    db: Session,
    *,
    status: str | None = None,
    mail_type: str | None = None,
    assigned_to: str | None = None,
    search: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[CustomerMail], int]:
    stmt = select(CustomerMail)
    count_stmt = select(func.count(CustomerMail.id))
    if status:
        stmt = stmt.where(CustomerMail.status == status)
        count_stmt = count_stmt.where(CustomerMail.status == status)
    if mail_type:
        stmt = stmt.where(CustomerMail.mail_type == mail_type)
        count_stmt = count_stmt.where(CustomerMail.mail_type == mail_type)
    if assigned_to:
        stmt = stmt.where(CustomerMail.assigned_to == assigned_to)
        count_stmt = count_stmt.where(CustomerMail.assigned_to == assigned_to)
    if search:
        like = f"%{search}%"
        clause = or_(
            CustomerMail.subject.ilike(like),
            CustomerMail.from_email.ilike(like),
            CustomerMail.customer_name.ilike(like),
        )
        stmt = stmt.where(clause)
        count_stmt = count_stmt.where(clause)

    total = int(db.scalar(count_stmt) or 0)
    rows = list(
        db.scalars(
            stmt.order_by(CustomerMail.received_at.desc().nullslast(), CustomerMail.id.desc())
            .offset(offset)
            .limit(limit)
        ).all()
    )
    return rows, total


def get_mail(db: Session, mail_id: int) -> CustomerMail | None:
    return db.get(CustomerMail, mail_id)


def assign_mail(
    db: Session,
    mail_id: int,
    *,
    assigned_to: str | None,
    priority: str | None,
    status: str | None,
    customer_name: str | None,
    mail_type: str | None,
) -> CustomerMail | None:
    row = get_mail(db, mail_id)
    if row is None:
        return None
    if assigned_to is not None:
        row.assigned_to = assigned_to or None
    if priority is not None:
        if priority not in CUSTOMER_MAIL_PRIORITIES:
            raise ValueError(f"priority must be one of {CUSTOMER_MAIL_PRIORITIES}")
        row.priority = priority
    if status is not None:
        if status not in CUSTOMER_MAIL_STATUSES:
            raise ValueError(f"status must be one of {CUSTOMER_MAIL_STATUSES}")
        row.status = status
    if customer_name is not None:
        row.customer_name = customer_name or None
    if mail_type is not None:
        if mail_type not in CUSTOMER_MAIL_TYPES:
            raise ValueError(f"mail_type must be one of {CUSTOMER_MAIL_TYPES}")
        row.mail_type = mail_type
    db.commit()
    db.refresh(row)
    return row


def create_task_from_mail(
    db: Session,
    mail_id: int,
    *,
    title: str,
    description: str | None,
    assigned_to: str | None,
    priority: str | None,
    due_date: datetime | None,
) -> tuple[CustomerMail | None, CommunicationTask | None]:
    mail = get_mail(db, mail_id)
    if mail is None:
        return None, None

    task = CommunicationTask(
        title=title or (mail.subject or "Customer mail follow-up"),
        description=description or mail.body,
        assigned_to=assigned_to,
        priority=priority or "P2",
        signal="YELLOW",
        status="TODO",
        task_source="CUSTOMER",
        customer_mail_id=mail.id,
        due_date=due_date,
        watchers=[],
    )
    db.add(task)
    db.flush()

    mail.linked_task_id = task.id
    if mail.status == "OPEN":
        mail.status = "IN_PROGRESS"
    db.commit()
    db.refresh(mail)
    db.refresh(task)
    return mail, task


def resolve_mail(
    db: Session,
    mail_id: int,
    *,
    resolution_note: str | None,
) -> CustomerMail | None:
    row = get_mail(db, mail_id)
    if row is None:
        return None
    row.status = "RESOLVED"
    if resolution_note:
        payload = dict(row.raw_payload) if isinstance(row.raw_payload, dict) else {}
        payload["resolution_note"] = resolution_note
        payload["resolved_at"] = datetime.utcnow().isoformat()
        row.raw_payload = payload
    db.commit()
    db.refresh(row)
    return row


def stats(db: Session) -> dict[str, int]:
    def count(*conds) -> int:
        stmt = select(func.count(CustomerMail.id))
        for c in conds:
            stmt = stmt.where(c)
        return int(db.scalar(stmt) or 0)

    today = datetime.utcnow().date()
    return {
        "total": count(),
        "open": count(CustomerMail.status == "OPEN"),
        "in_progress": count(CustomerMail.status == "IN_PROGRESS"),
        "resolved": count(CustomerMail.status == "RESOLVED"),
        "closed": count(CustomerMail.status == "CLOSED"),
        "received_today": count(
            CustomerMail.received_at.isnot(None),
            func.date(CustomerMail.received_at) == today,
        ),
    }

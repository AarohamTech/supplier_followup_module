"""Customer mail inbox router."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.communication_task import CommunicationTask
from ..models.customer_mail import (
    CUSTOMER_MAIL_PRIORITIES,
    CUSTOMER_MAIL_STATUSES,
    CUSTOMER_MAIL_TYPES,
    CustomerMail,
)
from ..services import customer_mail_service

router = APIRouter(prefix="/api/customer-mails", tags=["customer-mails"])


def _task_counts_for_mail(db: Session, mail_id: int) -> dict[str, int]:
    from sqlalchemy import func, select  # local import to keep top-level clean

    total = int(
        db.scalar(
            select(func.count(CommunicationTask.id)).where(
                CommunicationTask.customer_mail_id == mail_id
            )
        )
        or 0
    )
    open_ = int(
        db.scalar(
            select(func.count(CommunicationTask.id)).where(
                CommunicationTask.customer_mail_id == mail_id,
                CommunicationTask.status != "DONE",
            )
        )
        or 0
    )
    return {"task_count": total, "open_task_count": open_}


def _serialize_mail(db: Session, row: CustomerMail) -> CustomerMailOut:
    counts = _task_counts_for_mail(db, row.id)
    base = CustomerMailOut.model_validate(row)
    base.task_count = counts["task_count"]
    base.open_task_count = counts["open_task_count"]
    return base


def _task_counts_bulk(db: Session, mail_ids: list[int]) -> dict[int, tuple[int, int]]:
    """One grouped query for (total, open) task counts across many mails."""
    from sqlalchemy import case, func, select  # local import to keep top clean

    if not mail_ids:
        return {}
    rows = db.execute(
        select(
            CommunicationTask.customer_mail_id,
            func.count(CommunicationTask.id),
            func.sum(case((CommunicationTask.status != "DONE", 1), else_=0)),
        )
        .where(CommunicationTask.customer_mail_id.in_(mail_ids))
        .group_by(CommunicationTask.customer_mail_id)
    ).all()
    return {cid: (int(total or 0), int(open_ or 0)) for cid, total, open_ in rows}


# ─────────────────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────────────────
class CustomerMailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    from_email: str | None
    from_name: str | None
    to_email: str | None
    cc_email: str | None
    subject: str | None
    body: str | None
    received_at: datetime | None
    mail_type: str
    customer_name: str | None
    status: str
    assigned_to: str | None
    priority: str
    linked_task_id: int | None
    linked_supplier_po_no: str | None
    message_uid: str | None
    ai_category: str | None = None
    ai_urgency: str | None = None
    ai_action: str | None = None
    ai_summary: str | None = None
    ai_triaged_at: datetime | None = None
    task_count: int = 0
    open_task_count: int = 0
    created_at: datetime
    updated_at: datetime


class CustomerMailListResponse(BaseModel):
    total: int
    items: list[CustomerMailOut]
    stats: dict[str, int]
    allowed_types: list[str]
    allowed_statuses: list[str]


class CustomerMailAssignPayload(BaseModel):
    assigned_to: str | None = None
    priority: str | None = None
    status: str | None = None
    customer_name: str | None = None
    mail_type: str | None = None


class CustomerMailResolvePayload(BaseModel):
    resolution_note: str | None = None


class CustomerMailTaskPayload(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    description: str | None = None
    assigned_to: str | None = None
    priority: str | None = None
    due_date: datetime | None = None


class CustomerReplyPayload(BaseModel):
    body: str = Field(min_length=1)
    subject: str | None = Field(default=None, max_length=500)


class CustomerReplyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    direction: str
    subject: str | None
    body: str | None
    status: str
    mail_type: str | None
    to_emails: list[str]
    sent_at: datetime | None
    created_at: datetime
    error_message: str | None


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────
@router.get("", response_model=CustomerMailListResponse)
def list_customer_mails(
    db: Session = Depends(get_db),
    status: str | None = Query(default=None),
    mail_type: str | None = Query(default=None),
    assigned_to: str | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> Any:
    rows, total = customer_mail_service.list_mails(
        db,
        status=status,
        mail_type=mail_type,
        assigned_to=assigned_to,
        search=search,
        limit=limit,
        offset=offset,
    )
    counts = _task_counts_bulk(db, [row.id for row in rows])
    items: list[CustomerMailOut] = []
    for row in rows:
        base = CustomerMailOut.model_validate(row)
        base.task_count, base.open_task_count = counts.get(row.id, (0, 0))
        items.append(base)
    return CustomerMailListResponse(
        total=total,
        items=items,
        stats=customer_mail_service.stats(db),
        allowed_types=list(CUSTOMER_MAIL_TYPES),
        allowed_statuses=list(CUSTOMER_MAIL_STATUSES),
    )


@router.get("/{mail_id}", response_model=CustomerMailOut)
def get_customer_mail(mail_id: int, db: Session = Depends(get_db)):
    row = customer_mail_service.get_mail(db, mail_id)
    if row is None:
        raise HTTPException(404, "Customer mail not found")
    return _serialize_mail(db, row)


@router.patch("/{mail_id}/assign", response_model=CustomerMailOut)
def assign_customer_mail(
    mail_id: int,
    payload: CustomerMailAssignPayload,
    db: Session = Depends(get_db),
):
    try:
        row = customer_mail_service.assign_mail(
            db,
            mail_id,
            assigned_to=payload.assigned_to,
            priority=payload.priority,
            status=payload.status,
            customer_name=payload.customer_name,
            mail_type=payload.mail_type,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    if row is None:
        raise HTTPException(404, "Customer mail not found")
    return _serialize_mail(db, row)


@router.post("/{mail_id}/resolve", response_model=CustomerMailOut)
def resolve_customer_mail(
    mail_id: int,
    payload: CustomerMailResolvePayload,
    db: Session = Depends(get_db),
):
    row = customer_mail_service.resolve_mail(
        db,
        mail_id,
        resolution_note=payload.resolution_note,
    )
    if row is None:
        raise HTTPException(404, "Customer mail not found")
    return _serialize_mail(db, row)


@router.post("/{mail_id}/create-task")
def create_task_for_mail(
    mail_id: int,
    payload: CustomerMailTaskPayload,
    db: Session = Depends(get_db),
):
    mail, task = customer_mail_service.create_task_from_mail(
        db,
        mail_id,
        title=payload.title or "Customer mail follow-up",
        description=payload.description,
        assigned_to=payload.assigned_to,
        priority=payload.priority,
        due_date=payload.due_date,
    )
    if mail is None or task is None:
        raise HTTPException(404, "Customer mail not found")
    return {
        "ok": True,
        "task_id": task.id,
        "customer_mail_id": mail.id,
        "linked_task_id": mail.linked_task_id,
    }


@router.post("/{mail_id}/reply")
def reply_to_customer_mail(
    mail_id: int,
    payload: CustomerReplyPayload,
    db: Session = Depends(get_db),
):
    """Queue an outbound reply to the customer (sent by the SMTP worker)."""
    try:
        mail, msg = customer_mail_service.reply_to_mail(
            db, mail_id, body=payload.body, subject=payload.subject
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    if mail is None or msg is None:
        raise HTTPException(404, "Customer mail not found")
    return {
        "ok": True,
        "message_id": msg.id,
        "status": msg.status,
        "mail_status": mail.status,
        "queued": msg.status == "READY",
    }


@router.get("/{mail_id}/replies", response_model=list[CustomerReplyOut])
def list_customer_mail_replies(mail_id: int, db: Session = Depends(get_db)):
    if customer_mail_service.get_mail(db, mail_id) is None:
        raise HTTPException(404, "Customer mail not found")
    return customer_mail_service.list_replies(db, mail_id)


@router.post("/{mail_id}/draft-reply")
def draft_customer_reply(
    mail_id: int,
    ai: bool = Query(default=False, description="Use the LLM (slower) vs the instant template"),
    db: Session = Depends(get_db),
) -> dict:
    """Suggested reply from order data. `ai=true` polishes it with the LLM; the
    default is the instant deterministic template (no LLM call)."""
    draft = customer_mail_service.build_draft_reply(db, mail_id, use_ai=ai)
    if draft is None:
        raise HTTPException(404, "Customer mail not found")
    return draft


@router.get("/meta/options")
def meta_options() -> dict:
    return {
        "types": list(CUSTOMER_MAIL_TYPES),
        "statuses": list(CUSTOMER_MAIL_STATUSES),
        "priorities": list(CUSTOMER_MAIL_PRIORITIES),
    }

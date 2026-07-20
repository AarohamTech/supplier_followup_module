"""Employee-scoped customer mails — only the customer emails that concern the
logged-in employee: linked to one of their owned POs (``owner_emp_code``) or
allocated to them by name.

Mirrors the staff `/api/customer-mails` read/reply endpoints; mounted in
main.py with ``Depends(get_current_employee)``. The customer-domain filter
(CUSTOMER_MAIL_DOMAINS) still applies via customer_mail_service.list_mails.
"""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.deps import get_current_employee
from ..database import get_db
from ..models.customer_mail import CustomerMail
from ..models.procurement import ProcurementRecord
from ..models.user import User
from ..services import customer_mail_service
from ..workers import mail_send_worker
from .customer_mails import (
    CustomerMailOut,
    CustomerReplyOut,
    CustomerReplyPayload,
    DraftReplyPayload,
    _task_counts_bulk,
)

router = APIRouter(prefix="/api/eportal/mails", tags=["eportal-mails"])


def _owned_po_set(db: Session, user: User) -> set[str]:
    rows = db.scalars(
        select(ProcurementRecord.supplier_po_no)
        .where(ProcurementRecord.owner_emp_code == user.emp_code)
        .distinct()
    ).all()
    return {po for po in rows if po}


def _assigned_names(user: User) -> list[str]:
    return [n for n in {user.full_name, user.username} if n]


def _scoped_mail(db: Session, user: User, mail_id: int) -> CustomerMail:
    mail = customer_mail_service.get_mail(db, mail_id)
    in_scope = mail is not None and (
        (mail.linked_supplier_po_no and mail.linked_supplier_po_no in _owned_po_set(db, user))
        or (mail.assigned_to or "") in set(_assigned_names(user))
    )
    if not in_scope:
        # 404 (not 403) so out-of-scope IDs don't leak existence.
        raise HTTPException(404, "Customer mail not found")
    return mail


@router.get("")
def list_mails(
    user: User = Depends(get_current_employee),
    db: Session = Depends(get_db),
    status: str | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    # Same customer / non-customer split as the admin workspace ("Other Mails"),
    # still inside the employee's own scope.
    scope: str = Query(default="customer", pattern="^(customer|other)$"),
) -> dict:
    rows, total = customer_mail_service.list_mails(
        db,
        status=status,
        search=search,
        limit=limit,
        offset=offset,
        scope=scope,
        owned_po_nos=_owned_po_set(db, user),
        assigned_names=_assigned_names(user),
    )
    counts = _task_counts_bulk(db, [row.id for row in rows])
    items = []
    for row in rows:
        base = CustomerMailOut.model_validate(row)
        base.task_count, base.open_task_count = counts.get(row.id, (0, 0))
        items.append(base)
    return {"items": items, "total": total}


@router.get("/{mail_id}", response_model=CustomerMailOut)
def get_mail(
    mail_id: int,
    user: User = Depends(get_current_employee),
    db: Session = Depends(get_db),
):
    return CustomerMailOut.model_validate(_scoped_mail(db, user, mail_id))


@router.get("/{mail_id}/replies", response_model=list[CustomerReplyOut])
def list_replies(
    mail_id: int,
    user: User = Depends(get_current_employee),
    db: Session = Depends(get_db),
):
    _scoped_mail(db, user, mail_id)
    return customer_mail_service.list_replies(db, mail_id)


@router.post("/{mail_id}/reply")
def reply(
    mail_id: int,
    payload: CustomerReplyPayload,
    user: User = Depends(get_current_employee),
    db: Session = Depends(get_db),
) -> dict:
    _scoped_mail(db, user, mail_id)
    try:
        mail, msg = customer_mail_service.reply_to_mail(
            db, mail_id, body=payload.body, subject=payload.subject
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    if mail is None or msg is None:
        raise HTTPException(404, "Customer mail not found")
    # Best-effort immediate send; on SMTP failure the send cron retries it.
    try:
        mail_send_worker.send_message_now(db, msg.id)
        db.refresh(msg)
    except Exception:  # noqa: BLE001
        pass
    return {
        "ok": True,
        "message_id": msg.id,
        "queued": msg.status != "SENT",
        "mail_status": mail.status,
    }


@router.post("/{mail_id}/draft-reply")
def draft_reply(
    mail_id: int,
    user: User = Depends(get_current_employee),
    db: Session = Depends(get_db),
    ai: bool = Query(default=False),
    payload: DraftReplyPayload | None = Body(default=None),
) -> dict:
    _scoped_mail(db, user, mail_id)
    draft = customer_mail_service.build_draft_reply(
        db, mail_id, use_ai=ai, instruction=(payload.instruction if payload else None)
    )
    if draft is None:
        raise HTTPException(404, "Customer mail not found")
    return draft

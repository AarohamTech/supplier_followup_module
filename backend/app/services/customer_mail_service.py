"""Customer mail (non-supplier inbox) helpers."""
from __future__ import annotations

import logging
from datetime import datetime
from html import escape
from typing import Any

from sqlalchemy import or_, select, func
from sqlalchemy.orm import Session

from ..models.communication_message import CommunicationMessage
from ..models.communication_task import CommunicationTask
from ..models.customer_mail import (
    CUSTOMER_MAIL_PRIORITIES,
    CUSTOMER_MAIL_STATUSES,
    CUSTOMER_MAIL_TYPES,
    CustomerMail,
)
from ..models.procurement import ProcurementRecord
from . import ai_service
from . import communication_message_service as msg_service
from . import po_followup_service

log = logging.getLogger(__name__)


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


def _reply_subject(subject: str | None) -> str:
    s = (subject or "Your enquiry").strip()
    return s if s.lower().startswith("re:") else f"Re: {s}"


def _reply_html(body: str) -> str:
    """Wrap a plain-text reply body in a clean, branded HTML email."""
    safe = (
        escape(body or "")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\n", "<br/>")
    )
    return (
        '<div style="background:#f1f5f9;padding:18px;font-family:Arial,Helvetica,sans-serif;">'
        '<div style="max-width:640px;margin:0 auto;background:#ffffff;border:1px solid #e2e8f0;'
        'border-radius:10px;overflow:hidden;">'
        '<div style="background:#0f172a;padding:14px 20px;">'
        '<span style="color:#ffffff;font-size:16px;font-weight:700;">ProcureDirect</span></div>'
        '<div style="padding:20px;color:#1e293b;font-size:14px;line-height:1.6;">'
        f"{safe}"
        "</div>"
        '<div style="background:#f8fafc;border-top:1px solid #e2e8f0;padding:10px 20px;'
        'font-size:11px;color:#94a3b8;">Sent from the Supplier Follow-up Agent.</div>'
        "</div></div>"
    )


def _humanize_date(value: Any) -> str | None:
    """Render an ISO date/datetime string as a clean customer-facing date."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)).strftime("%d %b %Y")
    except ValueError:
        return str(value)


def reply_to_mail(
    db: Session,
    mail_id: int,
    *,
    body: str,
    subject: str | None = None,
) -> tuple[CustomerMail | None, CommunicationMessage | None]:
    """Queue an outbound reply to a customer mail (sent by the SMTP worker)."""
    mail = get_mail(db, mail_id)
    if mail is None:
        return None, None
    if not mail.from_email:
        raise ValueError("This mail has no sender address to reply to")

    msg = msg_service.queue_outgoing_message(
        db,
        subject=subject or _reply_subject(mail.subject),
        body=body,
        body_html=_reply_html(body),  # send a formatted HTML email (plain-text fallback kept)
        to_emails=[mail.from_email],
        receiver_email=mail.from_email,
        mail_type="CUSTOMER_REPLY",
        customer_mail_id=mail.id,
        in_reply_to=mail.message_uid,
        commit=False,
    )
    if mail.status == "OPEN":
        mail.status = "IN_PROGRESS"
    db.commit()
    db.refresh(mail)
    db.refresh(msg)
    return mail, msg


def list_replies(db: Session, mail_id: int) -> list[CommunicationMessage]:
    return list(
        db.scalars(
            select(CommunicationMessage)
            .where(CommunicationMessage.customer_mail_id == mail_id)
            .order_by(CommunicationMessage.created_at.asc())
        ).all()
    )


def build_draft_reply(
    db: Session, mail_id: int, *, use_ai: bool = True, instruction: str | None = None
) -> dict[str, Any] | None:
    """Compose a suggested reply. Uses the LLM when enabled (grounded in the same
    order facts) and always falls back to a deterministic template.

    `instruction` is free-text the agent typed in the composer; it's passed to the
    LLM as guidance so "AI Generate" writes the reply the way the agent wants."""
    mail = get_mail(db, mail_id)
    if mail is None:
        return None

    name = mail.from_name or mail.customer_name or "there"
    subject = _reply_subject(mail.subject)
    po = (mail.linked_supplier_po_no or "").strip()

    material: str | None = None
    status: str | None = None
    date: str | None = None
    if po:
        rec = db.scalar(
            select(ProcurementRecord)
            .where(ProcurementRecord.supplier_po_no == po)
            .order_by(ProcurementRecord.created_at.desc())
        )
        commitments = po_followup_service.list_commitments(db, supplier_po_no=po)
        commitment = commitments[0] if commitments else None
        material = rec.material_name if rec else None
        status = (
            (commitment.get("supplier_status") if commitment else None)
            or (rec.po_status if rec else None)
            or "in progress"
        )
        if commitment and commitment.get("commitment_date"):
            date = commitment["commitment_date"]
        elif rec and rec.commitment_date:
            date = rec.commitment_date.isoformat()
        elif rec and rec.shipment_date:
            date = rec.shipment_date.isoformat()
        date = _humanize_date(date)

    # Deterministic fallback (also the body the LLM is grounded on).
    if po and date:
        template_body = (
            f"Hi {name},\n\n"
            f"Thank you for reaching out regarding {po}"
            f"{f' ({material})' if material else ''}. "
            f"The current committed dispatch date is {date} (status: {status}). "
            "We will share tracking details as soon as it ships.\n\n"
            "Best regards,\nProcureDirect Team"
        )
        template_source = "order-data"
    else:
        template_body = (
            f"Hi {name},\n\n"
            "Thank you for your message. We are checking the latest status with our "
            "team and will get back to you shortly.\n\n"
            "Best regards,\nProcureDirect Team"
        )
        template_source = "generic"

    # Prefer an AI-polished reply grounded in the same facts; fall back on error.
    if use_ai and ai_service.is_enabled():
        try:
            ai_body = ai_service.suggest_customer_reply(
                customer_name=name,
                subject=mail.subject,
                customer_message=mail.body,
                supplier_po_no=po or None,
                material=material,
                status=status,
                dispatch_date=date,
            )
            if ai_body:
                return {"subject": subject, "body": ai_body, "source": "ai", "supplier_po_no": po or None}
        except Exception:  # noqa: BLE001
            log.exception("AI draft failed; using deterministic template")

    return {"subject": subject, "body": template_body, "source": template_source, "supplier_po_no": po or None}


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

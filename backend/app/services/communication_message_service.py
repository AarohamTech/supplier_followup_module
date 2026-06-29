"""Helpers for creating/querying CommunicationMessage rows.

This is the only writer that other services/workers should use so that all
business invariants (linkage, status vocab, dedupe) stay in one place.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models.communication_message import (
    MESSAGE_DIRECTIONS,
    MESSAGE_STATUSES,
    CommunicationMessage,
)
from ..models.procurement import ProcurementRecord
from ..models.supplier import SupplierMaster
from ..models.supplier_email import SupplierEmail

log = logging.getLogger(__name__)


def _validate(direction: str, status: str) -> None:
    if direction not in MESSAGE_DIRECTIONS:
        raise ValueError(f"direction must be one of {MESSAGE_DIRECTIONS}")
    if status not in MESSAGE_STATUSES:
        raise ValueError(f"status must be one of {MESSAGE_STATUSES}")


def find_supplier_by_email(db: Session, email: str | None) -> tuple[int | None, str | None]:
    """Lookup supplier by an email present in to/cc/bcc/escalation arrays."""
    if not email:
        return None, None
    email_lc = email.strip().lower()
    if not email_lc:
        return None, None
    rows = db.scalars(select(SupplierEmail).where(SupplierEmail.is_active.is_(True))).all()
    for row in rows:
        emails: list[str] = []
        for arr in (row.to_emails, row.cc_emails, row.bcc_emails, row.escalation_emails):
            if arr:
                emails.extend(arr)
        if any(e and e.strip().lower() == email_lc for e in emails):
            return row.supplier_id, row.supplier_name
    return None, None


def find_procurement_record(
    db: Session,
    supplier_po_no: str | None,
    subject: str | None,
    body: str | None,
) -> Optional[ProcurementRecord]:
    """Best-effort match: supplier_po_no first; otherwise scan subject+body for any known PO no."""
    if supplier_po_no:
        rec = db.scalar(
            select(ProcurementRecord)
            .where(ProcurementRecord.supplier_po_no == supplier_po_no)
            .order_by(ProcurementRecord.created_at.desc())
        )
        if rec:
            return rec

    haystack = " ".join(filter(None, [subject or "", body or ""]))
    if not haystack:
        return None

    candidates = db.scalars(
        select(ProcurementRecord.supplier_po_no).distinct()
    ).all()
    haystack_upper = haystack.upper()
    # Longest PO first so a longer PO wins over a shorter one it contains, and
    # require a standalone-token match (not embedded inside a longer string) to
    # avoid linking a reply to the wrong PO (e.g. "PO-12" inside "PO-1234").
    for po in sorted((p for p in candidates if p), key=len, reverse=True):
        pattern = r"(?<![A-Za-z0-9])" + re.escape(po.upper()) + r"(?![A-Za-z0-9])"
        if re.search(pattern, haystack_upper):
            return db.scalar(
                select(ProcurementRecord)
                .where(ProcurementRecord.supplier_po_no == po)
                .order_by(ProcurementRecord.created_at.desc())
            )
    return None


def message_exists(db: Session, message_uid: str | None) -> bool:
    if not message_uid:
        return False
    return db.scalar(
        select(func.count(CommunicationMessage.id)).where(
            CommunicationMessage.message_uid == message_uid
        )
    ) > 0


def create_message(
    db: Session,
    *,
    direction: str,
    status: str,
    supplier_id: int | None = None,
    supplier_name: str | None = None,
    procurement_record_id: int | None = None,
    supplier_po_no: str | None = None,
    customer_mail_id: int | None = None,
    subject: str | None = None,
    body: str | None = None,
    body_html: str | None = None,
    sender_email: str | None = None,
    receiver_email: str | None = None,
    to_emails: list[str] | None = None,
    cc_emails: list[str] | None = None,
    bcc_emails: list[str] | None = None,
    mail_type: str | None = None,
    message_uid: str | None = None,
    in_reply_to: str | None = None,
    parsed_status: str | None = None,
    parsed_qty: float | None = None,
    parsed_date: datetime | None = None,
    parsed_payload: dict[str, Any] | None = None,
    raw_payload: dict[str, Any] | None = None,
    received_at: datetime | None = None,
    sent_at: datetime | None = None,
    is_supplier_inbox: bool | None = None,
    commit: bool = True,
) -> CommunicationMessage:
    _validate(direction, status)
    msg = CommunicationMessage(
        direction=direction,
        status=status,
        channel="EMAIL",
        supplier_id=supplier_id,
        supplier_name=supplier_name,
        procurement_record_id=procurement_record_id,
        supplier_po_no=supplier_po_no,
        customer_mail_id=customer_mail_id,
        subject=subject,
        body=body,
        body_html=body_html,
        sender_email=sender_email,
        receiver_email=receiver_email,
        to_emails=to_emails or [],
        cc_emails=cc_emails or [],
        bcc_emails=bcc_emails or [],
        mail_type=mail_type,
        message_uid=message_uid,
        in_reply_to=in_reply_to,
        parsed_status=parsed_status,
        parsed_qty=parsed_qty,
        parsed_date=parsed_date,
        parsed_payload=parsed_payload,
        raw_payload=raw_payload,
        received_at=received_at,
        sent_at=sent_at,
        is_supplier_inbox=is_supplier_inbox,
    )
    db.add(msg)
    if commit:
        db.commit()
        db.refresh(msg)
    else:
        db.flush()
    return msg


def queue_outgoing_message(
    db: Session,
    *,
    supplier_id: int | None = None,
    supplier_name: str | None = None,
    procurement_record_id: int | None = None,
    supplier_po_no: str | None = None,
    customer_mail_id: int | None = None,
    subject: str | None = None,
    body: str | None = None,
    body_html: str | None = None,
    receiver_email: str | None = None,
    to_emails: list[str] | None = None,
    cc_emails: list[str] | None = None,
    bcc_emails: list[str] | None = None,
    mail_type: str | None = None,
    mail_history_id: int | None = None,
    in_reply_to: str | None = None,
    commit: bool = True,
) -> CommunicationMessage:
    payload: dict[str, Any] | None = None
    if mail_history_id is not None:
        payload = {"mail_history_id": mail_history_id}

    resolved_receiver = receiver_email
    if not resolved_receiver:
        for email in to_emails or []:
            if email:
                resolved_receiver = email
                break

    return create_message(
        db,
        direction="OUTGOING",
        status="READY",
        supplier_id=supplier_id,
        supplier_name=supplier_name,
        procurement_record_id=procurement_record_id,
        supplier_po_no=supplier_po_no,
        customer_mail_id=customer_mail_id,
        subject=subject,
        body=body,
        body_html=body_html,
        receiver_email=resolved_receiver,
        to_emails=to_emails,
        cc_emails=cc_emails,
        bcc_emails=bcc_emails,
        mail_type=mail_type,
        in_reply_to=in_reply_to,
        raw_payload=payload,
        commit=commit,
    )


def mark_status(
    db: Session, message_id: int, status: str, error: str | None = None, commit: bool = True
) -> CommunicationMessage | None:
    msg = db.get(CommunicationMessage, message_id)
    if not msg:
        return None
    if status not in MESSAGE_STATUSES:
        raise ValueError(f"status must be one of {MESSAGE_STATUSES}")
    msg.status = status
    if error is not None:
        msg.error_message = error
    if status == "SENT":
        msg.sent_at = datetime.utcnow()
    if commit:
        db.commit()
        db.refresh(msg)
    return msg


def attach_supplier(
    db: Session, msg: CommunicationMessage, supplier_id: int | None, supplier_name: str | None
) -> None:
    if supplier_id and not msg.supplier_id:
        msg.supplier_id = supplier_id
    if supplier_name and not msg.supplier_name:
        msg.supplier_name = supplier_name


def resolve_supplier_id_by_name(db: Session, name: str | None) -> int | None:
    if not name:
        return None
    row = db.scalar(
        select(SupplierMaster).where(
            func.upper(SupplierMaster.supplier_name) == name.strip().upper()
        )
    )
    return row.id if row else None

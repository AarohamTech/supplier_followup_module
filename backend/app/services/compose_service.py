"""Standalone mail compose — shared by the staff hub and the employee portal.

Composes an OUTGOING CommunicationMessage to arbitrary recipients and either
sends it over SMTP now (`send=True`) or stores it as a DRAFT. Kept provider- and
scope-agnostic; callers enforce their own authorization/scoping before calling.
"""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models.procurement import ProcurementRecord
from . import ai_service
from . import communication_message_service as msg_service


def clean_emails(values: list[str] | None) -> list[str]:
    out: list[str] = []
    for v in values or []:
        e = (v or "").strip()
        if e and e not in out:
            out.append(e)
    return out


def compose_and_send(
    db: Session,
    *,
    to_emails: list[str],
    cc_emails: list[str] | None = None,
    bcc_emails: list[str] | None = None,
    subject: str,
    body: str,
    supplier_name: str | None = None,
    supplier_po_no: str | None = None,
    procurement_record_id: int | None = None,
    customer_mail_id: int | None = None,
    send: bool = True,
) -> dict[str, Any]:
    subject = (subject or "").strip()
    body = (body or "").strip()
    to = clean_emails(to_emails)
    cc = clean_emails(cc_emails)
    bcc = clean_emails(bcc_emails)
    if not to:
        raise HTTPException(422, "At least one recipient (To) is required")
    if not subject:
        raise HTTPException(422, "Subject is required")
    if not body:
        raise HTTPException(422, "Message body is required")

    supplier_id = (
        msg_service.resolve_supplier_id_by_name(db, supplier_name) if supplier_name else None
    )
    rec = db.get(ProcurementRecord, procurement_record_id) if procurement_record_id else None
    po_no = supplier_po_no or (rec.supplier_po_no if rec else None)

    common = dict(
        supplier_id=supplier_id,
        supplier_name=supplier_name,
        procurement_record_id=rec.id if rec else None,
        supplier_po_no=po_no,
        customer_mail_id=customer_mail_id,
        subject=subject,
        body=body,
        to_emails=to,
        cc_emails=cc,
        bcc_emails=bcc,
        mail_type="HUB_COMPOSE",
    )

    if not send:
        msg = msg_service.create_message(
            db, direction="OUTGOING", status="DRAFT", commit=True, **common
        )
        return {"ok": True, "message_id": msg.id, "sent": False, "status": "DRAFT"}

    msg = msg_service.queue_outgoing_message(db, commit=True, **common)
    from ..workers import mail_send_worker

    result = mail_send_worker.send_message_now(db, msg.id)
    if result.get("enabled") is False:
        raise HTTPException(503, f"SMTP disabled: {result.get('reason', 'check settings')}")
    return {
        "ok": True,
        "message_id": msg.id,
        "sent": bool(result.get("sent")),
        "status": result.get("status", "QUEUED"),
        "emailed_to": to,
    }


def _fallback_body(
    *, instruction: str, recipient_name: str | None, supplier_name: str | None,
    supplier_po_no: str | None,
) -> str:
    who = recipient_name or supplier_name or "Team"
    ref = f" regarding PO {supplier_po_no}" if supplier_po_no else ""
    ask = (instruction or "share the latest status at your earliest convenience").strip()
    return (
        f"Dear {who},\n\n{ask.rstrip('.')}{ref}.\n\n"
        "Kindly revert with an update at the earliest.\n\nBest regards,\nProcurement Team"
    )


def draft_body(
    *,
    audience: str = "supplier",
    instruction: str = "",
    subject: str | None = None,
    supplier_name: str | None = None,
    supplier_po_no: str | None = None,
    recipient_name: str | None = None,
) -> dict[str, Any]:
    fb = _fallback_body(
        instruction=instruction, recipient_name=recipient_name,
        supplier_name=supplier_name, supplier_po_no=supplier_po_no,
    )
    if not ai_service.any_enabled():
        return {"body": fb, "source": "template"}

    ctx = [f"Audience: {'customer' if audience == 'customer' else 'supplier'}"]
    if recipient_name:
        ctx.append(f"Recipient: {recipient_name}")
    if supplier_name:
        ctx.append(f"Counterparty: {supplier_name}")
    if supplier_po_no:
        ctx.append(f"PO number: {supplier_po_no}")
    if subject:
        ctx.append(f"Subject: {subject}")
    user = "\n".join(ctx) + (
        f"\n\nInstruction: {instruction or 'Write a concise, professional email.'}"
    )
    system = (
        "You are a procurement officer drafting a concise, professional business "
        "email. Return ONLY the email body (greeting, body, sign-off) — no subject "
        "line, no markdown, no placeholders in brackets."
    )
    try:
        out = ai_service.chat([{"role": "user", "content": user}], system=system)
        return {"body": (out or "").strip() or fb, "source": "ai"}
    except Exception:  # noqa: BLE001
        return {"body": fb, "source": "template"}

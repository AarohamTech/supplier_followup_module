"""Mailbox supplier-reply fetch worker.

Safe by default: if `MAIL_INBOX_ENABLED=false` or any IMAP setting is missing,
the worker returns a no-op result without raising — the app keeps running.

Each fetched mail is stored as an INCOMING `CommunicationMessage`, parsed via
`mail_parser_service`, linked to a supplier (by sender email) and a procurement
record (by PO no in subject/body), and finally reconciled with
`status_change_service` so downstream UI sees the updates.
"""
from __future__ import annotations

import email
import imaplib
import logging
import poplib
from datetime import datetime
from email.header import decode_header
from email.message import Message as EmailMessage
from email.utils import parseaddr, parsedate_to_datetime
from typing import Any

from sqlalchemy.orm import Session

from ..core.config import settings
from ..database import SessionLocal
from ..models.customer_mail import CustomerMail
from ..services import (
    ai_insights_service,
    communication_message_service as msg_service,
    knowledge_indexer,
    mail_parser_service,
    status_change_service,
)

log = logging.getLogger(__name__)


def _decode(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        try:
            return value.decode(errors="replace")
        except Exception:  # noqa: BLE001
            return ""
    parts = decode_header(value)
    out: list[str] = []
    for text, enc in parts:
        if isinstance(text, bytes):
            out.append(text.decode(enc or "utf-8", errors="replace"))
        else:
            out.append(text)
    return "".join(out)


def _extract_body(msg: EmailMessage) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition") or "")
            if ctype == "text/plain" and "attachment" not in disp:
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace")
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace")
        return ""
    payload = msg.get_payload(decode=True)
    if payload:
        charset = msg.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace")
    return msg.get_payload() or ""


def _config_ready() -> tuple[bool, str]:
    if not getattr(settings, "MAIL_INBOX_ENABLED", False):
        return False, "MAIL_INBOX_ENABLED is false"
    if not settings.IMAP_HOST or not settings.IMAP_USER or not settings.IMAP_PASSWORD:
        return False, "Mailbox credentials are missing"
    return True, ""


def _classify_customer_mail(subject: str | None, body: str | None) -> str:
    blob = f"{subject or ''} {body or ''}".lower()
    if any(kw in blob for kw in ("dispatch", "shipped", "shipment", "courier")):
        return "DISPATCH"
    if any(kw in blob for kw in ("quality", "defect", "rejected", "ncr")):
        return "QUALITY"
    if any(kw in blob for kw in ("invoice", "payment", "finance", "credit note", "gst", "outstanding")):
        return "FINANCE"
    if any(kw in blob for kw in ("complaint", "issue", "problem")):
        return "COMPLAINT"
    if any(kw in blob for kw in ("supplier", "vendor", "purchase order", " po ")):
        return "SUPPLIER"
    if any(kw in blob for kw in ("customer", "order", "enquiry", "inquiry", "quotation", "rfq")):
        return "CUSTOMER"
    return "GENERAL"


def _connect_imap() -> imaplib.IMAP4:
    if settings.MAIL_INBOX_USE_SSL:
        return imaplib.IMAP4_SSL(settings.IMAP_HOST, settings.IMAP_PORT)
    return imaplib.IMAP4(settings.IMAP_HOST, settings.IMAP_PORT)


def _connect_pop3() -> poplib.POP3:
    if settings.MAIL_INBOX_USE_SSL:
        return poplib.POP3_SSL(settings.IMAP_HOST, settings.IMAP_PORT, timeout=30)
    return poplib.POP3(settings.IMAP_HOST, settings.IMAP_PORT, timeout=30)


def _process_one(
    db: Session,
    raw_uid: bytes,
    raw_msg: bytes,
) -> dict[str, Any]:
    parsed_msg = email.message_from_bytes(raw_msg)
    subject = _decode(parsed_msg.get("Subject"))
    from_header = _decode(parsed_msg.get("From"))
    to_header = _decode(parsed_msg.get("To"))
    message_id = (parsed_msg.get("Message-ID") or raw_uid.decode(errors="replace")).strip()
    in_reply_to = parsed_msg.get("In-Reply-To")
    date_header = parsed_msg.get("Date")
    received_at: datetime | None = None
    if date_header:
        try:
            received_at = parsedate_to_datetime(date_header).replace(tzinfo=None)
        except Exception:  # noqa: BLE001
            received_at = None

    body = _extract_body(parsed_msg)
    sender_email = parseaddr(from_header)[1] or None

    if msg_service.message_exists(db, message_id):
        return {"message_uid": message_id, "skipped": True, "reason": "duplicate"}

    supplier_id, supplier_name = msg_service.find_supplier_by_email(db, sender_email)
    sender_domain = (
        sender_email.rsplit("@", 1)[-1].lower() if sender_email and "@" in sender_email else ""
    )
    is_supplier_domain = sender_domain in settings.supplier_mail_domains
    parsed = mail_parser_service.parse_email(db, subject, body, supplier_id=supplier_id)

    rec = msg_service.find_procurement_record(
        db,
        supplier_po_no=parsed.get("supplier_po_no"),
        subject=subject,
        body=body,
    )

    # Mails from unknown senders (no supplier mapping AND no PO match) are
    # routed into the Customer Mail inbox instead of the supplier comm hub —
    # UNLESS the sender domain is a configured supplier domain (Supplier Inbox),
    # in which case they fall through to the supplier pipeline below.
    if supplier_id is None and rec is None and not is_supplier_domain:
        existing_customer = (
            db.query(CustomerMail).filter(CustomerMail.message_uid == message_id).first()
            if message_id
            else None
        )
        if existing_customer is None:
            classified_type = _classify_customer_mail(subject, body)
            customer = CustomerMail(
                from_email=sender_email,
                from_name=parseaddr(from_header)[0] or None,
                to_email=parseaddr(to_header)[1] or settings.IMAP_USER,
                cc_email=parsed_msg.get("Cc") or None,
                subject=subject,
                body=body,
                received_at=received_at,
                mail_type=classified_type,
                customer_name=parseaddr(from_header)[0] or sender_email,
                status="OPEN",
                priority="P2",
                # Link to the related order when a PO/CRM number was parsed, so the
                # customer mail shows its order context instead of being orphaned.
                linked_supplier_po_no=parsed.get("supplier_po_no"),
                message_uid=message_id,
                raw_payload={"headers": dict(parsed_msg.items())},
            )
            db.add(customer)
            db.commit()
            # Best-effort AI enrichment — never block or fail the fetch.
            triaged: dict[str, Any] | None = None
            if settings.AI_TRIAGE_ENABLED:
                try:
                    triaged = ai_insights_service.triage_mail(db, customer, use_ai=True)
                except Exception:  # noqa: BLE001
                    log.exception("auto-triage failed for customer_mail %s", customer.id)
            try:
                knowledge_indexer.index_customer_mail(db, customer)
            except Exception:  # noqa: BLE001
                log.exception("indexing failed for customer_mail %s", customer.id)
            return {
                "message_uid": message_id,
                "skipped": False,
                "routed_to": "customer_mail",
                "customer_mail_id": customer.id,
                "triaged": triaged,
            }
        return {
            "message_uid": message_id,
            "skipped": True,
            "reason": "duplicate-customer",
        }

    msg = msg_service.create_message(
        db,
        direction="INCOMING",
        status="RECEIVED",
        supplier_id=supplier_id,
        supplier_name=(rec.supplier_name if rec else None)
        or supplier_name
        or (parseaddr(from_header)[0] or None)
        or (sender_domain or None),
        procurement_record_id=rec.id if rec else None,
        supplier_po_no=parsed.get("supplier_po_no") or (rec.supplier_po_no if rec else None),
        subject=subject,
        body=body,
        sender_email=sender_email,
        receiver_email=parseaddr(to_header)[1] or settings.IMAP_USER,
        is_supplier_inbox=True,
        message_uid=message_id,
        in_reply_to=in_reply_to,
        parsed_status=parsed.get("status"),
        parsed_qty=parsed.get("quantity"),
        parsed_date=parsed.get("_expected_dispatch_date_dt"),
        parsed_payload={k: v for k, v in parsed.items() if not k.startswith("_")},
        raw_payload={"headers": dict(parsed_msg.items())},
        received_at=received_at,
        commit=True,
    )

    applied = False
    if rec:
        log_entry = status_change_service.apply_parsed_reply(db, rec, msg, parsed)
        applied = log_entry is not None

    commitments_upserted: list[int] = []
    if msg and msg.supplier_po_no:
        try:
            commitments_upserted = status_change_service.apply_material_reply_table(
                db, msg, body=body, commit=True
            )
        except Exception:  # noqa: BLE001
            log.exception(
                "apply_material_reply_table failed for message_uid=%s", message_id
            )

    # Best-effort: add the supplier reply to the semantic memory.
    if msg is not None:
        try:
            knowledge_indexer.index_supplier_reply(db, msg)
        except Exception:  # noqa: BLE001
            log.exception("indexing failed for supplier reply %s", getattr(msg, "id", None))

    return {
        "message_uid": message_id,
        "skipped": False,
        "supplier_id": supplier_id,
        "procurement_record_id": rec.id if rec else None,
        "status_change_applied": applied,
        "commitments_upserted": commitments_upserted,
    }


def _fetch_imap_messages(
    db: Session,
    client: imaplib.IMAP4,
    limit: int,
) -> dict[str, Any]:
    client.login(settings.IMAP_USER, settings.IMAP_PASSWORD)
    client.select(settings.IMAP_FOLDER or "INBOX")

    typ, data = client.search(None, "UNSEEN")
    if typ != "OK":
        log.warning("IMAP search failed: %s", typ)
        return {"enabled": True, "protocol": "IMAP", "fetched": 0, "processed": []}

    ids = data[0].split()
    if limit:
        ids = ids[-limit:]

    processed: list[dict[str, Any]] = []
    for raw_uid in ids:
        try:
            typ, msg_data = client.fetch(raw_uid, "(RFC822)")
            if typ != "OK" or not msg_data or not msg_data[0]:
                continue
            raw_msg = msg_data[0][1]
            if not isinstance(raw_msg, (bytes, bytearray)):
                continue
            result = _process_one(db, raw_uid, bytes(raw_msg))
            processed.append(result)
        except Exception:  # noqa: BLE001
            log.exception("Failed to process IMAP message uid=%s", raw_uid)

    return {
        "enabled": True,
        "protocol": "IMAP",
        "fetched": len(ids),
        "processed": processed,
    }


def _fetch_pop3_messages(
    db: Session,
    client: poplib.POP3,
    limit: int,
) -> dict[str, Any]:
    client.user(settings.IMAP_USER)
    client.pass_(settings.IMAP_PASSWORD)

    message_count, _ = client.stat()
    if message_count <= 0:
        return {"enabled": True, "protocol": "POP3", "fetched": 0, "processed": []}

    uid_map: dict[int, bytes] = {}
    try:
        _, uid_lines, _ = client.uidl()
        for line in uid_lines:
            parts = line.split()
            if len(parts) >= 2:
                try:
                    uid_map[int(parts[0])] = parts[1]
                except ValueError:
                    continue
    except Exception:  # noqa: BLE001
        log.exception("POP3 UIDL listing failed; falling back to sequence numbers")

    start = max(1, message_count - limit + 1) if limit else 1
    message_numbers = list(range(start, message_count + 1))

    processed: list[dict[str, Any]] = []
    for msg_no in message_numbers:
        try:
            _, lines, _ = client.retr(msg_no)
            raw_uid = uid_map.get(msg_no, str(msg_no).encode())
            raw_msg = b"\r\n".join(lines)
            result = _process_one(db, raw_uid, raw_msg)
            result["mailbox_seq"] = msg_no
            processed.append(result)
        except Exception:  # noqa: BLE001
            log.exception("Failed to process POP3 message seq=%s", msg_no)

    return {
        "enabled": True,
        "protocol": "POP3",
        "fetched": len(message_numbers),
        "processed": processed,
    }


def fetch_supplier_mails(limit: int = 50) -> dict[str, Any]:
    """Connect to the configured mailbox, fetch mails, persist + parse them.

    Returns a structured summary. Never raises if disabled/misconfigured —
    caller can treat that as a no-op.
    """
    ready, reason = _config_ready()
    if not ready:
        log.info("Mail fetch worker disabled: %s", reason)
        return {
            "enabled": False,
            "reason": reason,
            "protocol": settings.MAIL_FETCH_PROTOCOL,
            "fetched": 0,
            "processed": [],
        }

    db: Session = SessionLocal()
    client: imaplib.IMAP4 | poplib.POP3 | None = None
    try:
        if settings.MAIL_FETCH_PROTOCOL == "POP3":
            client = _connect_pop3()
            return _fetch_pop3_messages(db, client, limit)

        client = _connect_imap()
        return _fetch_imap_messages(db, client, limit)
    except Exception as exc:  # noqa: BLE001
        log.exception("Mail fetch worker error")
        return {
            "enabled": True,
            "protocol": settings.MAIL_FETCH_PROTOCOL,
            "fetched": 0,
            "processed": [],
            "error": str(exc),
        }
    finally:
        if client is not None:
            try:
                if isinstance(client, poplib.POP3):
                    client.quit()
                else:
                    client.logout()
            except Exception:  # noqa: BLE001
                pass
        db.close()


def test_inbox_connection() -> dict[str, Any]:
    """Quick connectivity + auth check for the configured inbox."""
    ready, reason = _config_ready()
    if not ready:
        return {
            "enabled": False,
            "ok": False,
            "protocol": settings.MAIL_FETCH_PROTOCOL,
            "reason": reason,
        }

    client: imaplib.IMAP4 | poplib.POP3 | None = None
    try:
        if settings.MAIL_FETCH_PROTOCOL == "POP3":
            client = _connect_pop3()
            client.user(settings.IMAP_USER)
            client.pass_(settings.IMAP_PASSWORD)
            count, _ = client.stat()
            return {
                "enabled": True,
                "ok": True,
                "protocol": "POP3",
                "host": settings.IMAP_HOST,
                "port": int(settings.IMAP_PORT or 0),
                "mailbox_count": int(count),
            }
        client = _connect_imap()
        client.login(settings.IMAP_USER, settings.IMAP_PASSWORD)
        client.select(settings.IMAP_FOLDER or "INBOX")
        return {
            "enabled": True,
            "ok": True,
            "protocol": "IMAP",
            "host": settings.IMAP_HOST,
            "port": int(settings.IMAP_PORT or 0),
            "folder": settings.IMAP_FOLDER or "INBOX",
        }
    except Exception as exc:  # noqa: BLE001
        log.exception("Inbox connection test failed")
        return {
            "enabled": True,
            "ok": False,
            "protocol": settings.MAIL_FETCH_PROTOCOL,
            "host": settings.IMAP_HOST,
            "port": int(settings.IMAP_PORT or 0),
            "error": str(exc),
        }
    finally:
        if client is not None:
            try:
                if isinstance(client, poplib.POP3):
                    client.quit()
                else:
                    client.logout()
            except Exception:  # noqa: BLE001
                pass

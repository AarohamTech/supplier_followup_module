"""SMTP outbound worker.

Picks `CommunicationMessage` rows where direction=OUTGOING and status=READY
and sends them through SMTP. Safe by default: if `SMTP_ENABLED=false` or any
SMTP setting is missing, the worker returns a no-op result without raising.
"""
from __future__ import annotations

import concurrent.futures
import logging
import smtplib
import re
from datetime import datetime
from email.message import EmailMessage
from html import unescape
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.config import settings
from ..database import SessionLocal
from ..models.communication_message import CommunicationMessage
from ..models.mail_history import MailHistory
from ..models.procurement import ProcurementRecord
from ..services import communication_message_service as msg_service

log = logging.getLogger(__name__)

_TAG_RE = re.compile(r"<[^>]+>")


def _html_to_text(html: str | None) -> str:
    """Cheap HTML→text fallback for the plain-text MIME part."""
    if not html:
        return ""
    text = re.sub(r"(?i)</(p|div|tr|table|h[1-6])>", "\n", html)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = _TAG_RE.sub("", text)
    text = unescape(text)
    lines = [ln.strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln).strip()


def _config_ready() -> tuple[bool, str]:
    if not getattr(settings, "SMTP_ENABLED", False):
        return False, "SMTP_ENABLED is false"
    if not settings.SMTP_HOST or not settings.SMTP_FROM:
        return False, "SMTP_HOST/SMTP_FROM are missing"
    if bool(settings.SMTP_USER) != bool(settings.SMTP_PASSWORD):
        return False, "SMTP_USER and SMTP_PASSWORD must both be set"
    return True, ""


def _open_client() -> smtplib.SMTP:
    host = settings.SMTP_HOST
    port = int(settings.SMTP_PORT or 587)
    user = settings.SMTP_USER
    password = settings.SMTP_PASSWORD

    if port == 465:
        client = smtplib.SMTP_SSL(host, port, timeout=30)
        if user:
            client.login(user, password or "")
        return client

    client = smtplib.SMTP(host, port, timeout=30)
    client.ehlo()
    try:
        client.starttls()
        client.ehlo()
    except smtplib.SMTPException:
        pass
    if user:
        client.login(user, password or "")
    return client


def _build_email(msg: CommunicationMessage) -> EmailMessage:
    em = EmailMessage()
    em["From"] = settings.SMTP_FROM
    em["To"] = ", ".join(msg.to_emails or ([msg.receiver_email] if msg.receiver_email else []))
    if msg.cc_emails:
        em["Cc"] = ", ".join(msg.cc_emails)
    if msg.bcc_emails:
        em["Bcc"] = ", ".join(msg.bcc_emails)
    em["Subject"] = msg.subject or "(no subject)"

    body_html = getattr(msg, "body_html", None)
    # Always set a plain-text part for fallback; attach HTML as the rich alternative
    # so email clients render the formatted tables instead of raw markdown.
    em.set_content(msg.body or _html_to_text(body_html) or "")
    if body_html:
        em.add_alternative(body_html, subtype="html")
    return em


def _send_one(em: EmailMessage) -> None:
    with _open_client() as client:
        client.send_message(em)


def _linked_mail_history_id(msg: CommunicationMessage) -> int | None:
    payload = msg.raw_payload if isinstance(msg.raw_payload, dict) else None
    value = payload.get("mail_history_id") if payload else None
    return value if isinstance(value, int) else None


MAX_SEND_RETRIES = 3


def _bump_retry(msg: CommunicationMessage, error: str | None) -> int:
    """Increment retry counter inside `raw_payload` and return the new value."""
    payload = dict(msg.raw_payload) if isinstance(msg.raw_payload, dict) else {}
    retries = int(payload.get("retries", 0) or 0) + 1
    payload["retries"] = retries
    payload["last_error"] = error
    payload["last_error_at"] = datetime.utcnow().isoformat()
    msg.raw_payload = payload
    return retries


def _target_procurement_rows(
    db: Session,
    msg: CommunicationMessage,
    history: MailHistory | None,
) -> list[ProcurementRecord]:
    if history is not None:
        is_po_mail = (history.material_name or "").strip().upper().startswith("ALL MATERIALS") or (
            history.mail_type or ""
        ).strip().upper().startswith("PO_")
        if is_po_mail and history.supplier_po_no:
            stmt = select(ProcurementRecord).where(
                ProcurementRecord.supplier_po_no == history.supplier_po_no
            )
            if history.supplier_name:
                stmt = stmt.where(ProcurementRecord.supplier_name == history.supplier_name)
            rows = list(db.scalars(stmt).all())
            if rows:
                return rows

    if msg.procurement_record_id is None:
        return []
    rec = db.get(ProcurementRecord, msg.procurement_record_id)
    return [rec] if rec else []


def _sync_delivery_state(
    db: Session,
    msg: CommunicationMessage,
    *,
    status: str,
    error: str | None = None,
) -> None:
    msg_service.mark_status(db, msg.id, status, error=error, commit=False)
    history_id = _linked_mail_history_id(msg)
    history = db.get(MailHistory, history_id) if history_id is not None else None

    if history is not None:
        history.sent_status = status
        if status == "SENT":
            history.sent_at = msg.sent_at or datetime.utcnow()
            history.remarks = None
        elif error is not None:
            history.remarks = error

    for rec in _target_procurement_rows(db, msg, history):
        old_status = (rec.mail_status or "").upper()
        rec.mail_status = status
        if status == "SENT":
            rec.last_followup_date = msg.sent_at or datetime.utcnow()
            # One follow-up per record per mail — skip if already in a sent state
            # (prevents double-count with a later manual "mark sent").
            if old_status not in {"SENT", "SENT_MANUALLY"}:
                rec.followup_count = (rec.followup_count or 0) + 1


def test_smtp_connection() -> dict[str, Any]:
    ready, reason = _config_ready()
    if not ready:
        log.info("SMTP connection test skipped: %s", reason)
        return {"enabled": False, "ok": False, "reason": reason}

    try:
        with _open_client():
            return {
                "enabled": True,
                "ok": True,
                "host": settings.SMTP_HOST,
                "port": int(settings.SMTP_PORT or 587),
                "authenticated": bool(settings.SMTP_USER),
            }
    except Exception as exc:  # noqa: BLE001
        log.exception("SMTP connection test failed")
        return {
            "enabled": True,
            "ok": False,
            "host": settings.SMTP_HOST,
            "port": int(settings.SMTP_PORT or 587),
            "authenticated": bool(settings.SMTP_USER),
            "error": str(exc),
        }


def _send_bucket(message_ids: list[int]) -> list[dict[str, Any]]:
    """Send a disjoint slice of messages over a SINGLE reused SMTP connection.

    Runs in its own thread with its own DB session. Reusing one connection for the
    whole slice (instead of reconnecting per message) is the main throughput win;
    several buckets run in parallel for additional speed.
    """
    results: list[dict[str, Any]] = []
    db: Session = SessionLocal()
    client: smtplib.SMTP | None = None
    try:
        for mid in message_ids:
            msg = db.get(CommunicationMessage, mid)
            # Re-check status: a user-initiated immediate send may have claimed it.
            if msg is None or msg.direction != "OUTGOING" or msg.status != "READY":
                continue
            try:
                if client is None:
                    client = _open_client()
                em = _build_email(msg)
                client.send_message(em)
                _sync_delivery_state(db, msg, status="SENT")
                db.commit()
                results.append({"message_id": mid, "status": "SENT"})
            except Exception as exc:  # noqa: BLE001
                log.exception("Failed to send message id=%s", mid)
                db.rollback()
                # The connection may be dead — drop it so the next message reconnects.
                if client is not None:
                    try:
                        client.quit()
                    except Exception:  # noqa: BLE001
                        pass
                    client = None
                msg = db.get(CommunicationMessage, mid)
                if msg is None:
                    continue
                retries = _bump_retry(msg, str(exc))
                if retries >= MAX_SEND_RETRIES:
                    _sync_delivery_state(db, msg, status="FAILED", error=str(exc))
                    results.append(
                        {"message_id": mid, "status": "FAILED", "retries": retries, "error": str(exc)}
                    )
                else:
                    msg.error_message = str(exc)
                    results.append(
                        {"message_id": mid, "status": "RETRY", "retries": retries, "error": str(exc)}
                    )
                db.commit()
    finally:
        if client is not None:
            try:
                client.quit()
            except Exception:  # noqa: BLE001
                pass
        db.close()
    return results


def send_ready_messages(limit: int | None = None) -> dict[str, Any]:
    ready, reason = _config_ready()
    if not ready:
        log.info("Mail send worker disabled: %s", reason)
        return {"enabled": False, "reason": reason, "attempted": 0, "results": []}

    if limit is None:
        limit = int(getattr(settings, "MAIL_SEND_BATCH_LIMIT", 50) or 50)

    db: Session = SessionLocal()
    try:
        ids = list(
            db.scalars(
                select(CommunicationMessage.id)
                .where(
                    CommunicationMessage.direction == "OUTGOING",
                    CommunicationMessage.status == "READY",
                )
                .order_by(CommunicationMessage.created_at.asc())
                .limit(limit)
            ).all()
        )
    finally:
        db.close()

    if not ids:
        return {"enabled": True, "attempted": 0, "sent": 0, "results": [], "ran_at": datetime.utcnow().isoformat()}

    # Partition into disjoint round-robin buckets so no two workers touch the same
    # message (no double-send), then send buckets in parallel.
    workers = max(1, min(int(getattr(settings, "SMTP_SEND_WORKERS", 4) or 4), len(ids)))
    results: list[dict[str, Any]] = []
    if workers == 1:
        results = _send_bucket(ids)
    else:
        buckets = [b for b in (ids[i::workers] for i in range(workers)) if b]
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(buckets)) as ex:
            for res in ex.map(_send_bucket, buckets):
                results.extend(res)

    sent = sum(1 for r in results if r.get("status") == "SENT")
    return {
        "enabled": True,
        "attempted": len(ids),
        "sent": sent,
        "workers": workers,
        "results": results,
        "ran_at": datetime.utcnow().isoformat(),
    }


def send_message_now(db: Session, message_id: int) -> dict[str, Any]:
    """Send a single queued (READY) outgoing message immediately.

    Used by user-initiated actions (e.g. a customer reply) so the mail goes out
    at once instead of waiting for the send cron. Best-effort: on SMTP failure
    the message is left READY (retry counter bumped) for the cron to pick up,
    and this never raises. Uses the caller's session.
    """
    ready, reason = _config_ready()
    if not ready:
        return {"enabled": False, "reason": reason, "sent": False}
    msg = db.get(CommunicationMessage, message_id)
    if msg is None or msg.direction != "OUTGOING" or msg.status != "READY":
        return {"enabled": True, "sent": False, "reason": "not a queued outgoing message"}
    try:
        em = _build_email(msg)
        _send_one(em)
        _sync_delivery_state(db, msg, status="SENT")
        db.commit()
        return {"enabled": True, "sent": True, "status": "SENT", "message_id": msg.id}
    except Exception as exc:  # noqa: BLE001
        log.exception("Immediate send failed for message id=%s (left READY for cron)", message_id)
        _bump_retry(msg, str(exc))
        db.commit()
        return {"enabled": True, "sent": False, "status": "READY", "error": str(exc)}

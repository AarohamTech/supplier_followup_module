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
from email.utils import make_msgid, parseaddr
from html import unescape
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.tenant import use_company, get_current_schema
from ..database import SessionLocal
from ..models.communication_message import CommunicationMessage
from ..models.mail_history import MailHistory
from ..models.procurement import ProcurementRecord
from ..services import brand_email
from ..services import communication_message_service as msg_service
from ..services import mail_config_service, mail_identity_service
from ..services.mail_config_service import SmtpConfig

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


def _open_client(cfg: SmtpConfig | None = None) -> smtplib.SMTP:
    cfg = cfg or mail_config_service.env_smtp_config()
    host = cfg.host
    port = int(cfg.port or 587)
    user = cfg.user
    password = cfg.password

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


def _from_domain(from_addr: str | None = None) -> str:
    """Domain to stamp generated Message-IDs with, derived from the From address."""
    _, addr = parseaddr(from_addr or settings.SMTP_FROM or "")
    domain = addr.split("@", 1)[1].strip() if "@" in addr else ""
    return domain or "localhost"


def _is_message_id(value: str | None) -> bool:
    """A real RFC 5322 Message-ID contains an "@"; bare IMAP UIDs do not."""
    return bool(value) and "@" in value


def _build_email(msg: CommunicationMessage, from_addr: str | None = None) -> EmailMessage:
    from_addr = from_addr or settings.SMTP_FROM
    em = EmailMessage()
    em["From"] = from_addr
    em["To"] = ", ".join(msg.to_emails or ([msg.receiver_email] if msg.receiver_email else []))
    if msg.cc_emails:
        em["Cc"] = ", ".join(msg.cc_emails)
    if msg.bcc_emails:
        em["Bcc"] = ", ".join(msg.bcc_emails)
    em["Subject"] = msg.subject or "(no subject)"

    # Always stamp a Message-ID so recipients (and our own future ingests) can
    # thread on it. When this is a reply, point In-Reply-To / References at the
    # original message so Gmail/Outlook nest it under the existing conversation.
    em["Message-ID"] = make_msgid(domain=_from_domain(from_addr))
    in_reply_to = getattr(msg, "in_reply_to", None)
    if _is_message_id(in_reply_to):
        em["In-Reply-To"] = in_reply_to
        em["References"] = in_reply_to

    body_html = getattr(msg, "body_html", None)
    # Every outgoing mail leaves the platform as HTML. Templated follow-ups already
    # carry an authored `body_html`; messages composed as plain text (hub replies,
    # acknowledgements, escalations) do not, so wrap their text in the branded shell
    # here. This is the single send choke point, so it covers all sources.
    if not body_html and (msg.body or "").strip():
        body_html = brand_email.text_email_html(msg.body)
    # Always set a plain-text part for fallback; attach HTML as the rich alternative
    # so email clients render the formatted tables instead of raw markdown.
    em.set_content(msg.body or _html_to_text(body_html) or "")
    if body_html:
        em.add_alternative(body_html, subtype="html")
    return em


def _send_one(em: EmailMessage, cfg: SmtpConfig | None = None) -> None:
    with _open_client(cfg) as client:
        client.send_message(em)


def send_html_email(
    to_emails: list[str],
    subject: str,
    html: str,
    *,
    text: str | None = None,
) -> dict:
    """Send a standalone branded HTML email (not tied to a CommunicationMessage).

    Used by the admin digest. Returns a status dict; never raises on SMTP-disabled.
    """
    ok, reason = _config_ready()
    if not ok:
        return {"sent": False, "recipients": 0, "reason": reason}
    recipients = [e for e in (to_emails or []) if e]
    if not recipients:
        return {"sent": False, "recipients": 0, "reason": "no recipients"}

    em = EmailMessage()
    em["From"] = settings.SMTP_FROM
    em["To"] = ", ".join(recipients)
    em["Subject"] = subject or "(no subject)"
    em.set_content(text or _html_to_text(html) or "")
    em.add_alternative(html, subtype="html")
    try:
        _send_one(em)
    except Exception as exc:  # noqa: BLE001
        return {"sent": False, "recipients": len(recipients), "reason": str(exc)}
    return {"sent": True, "recipients": len(recipients), "reason": ""}


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


def test_smtp_connection(cfg: SmtpConfig | None = None) -> dict[str, Any]:
    """Probe SMTP connectivity. With no `cfg`, tests the env config (legacy). The
    settings API passes the effective per-company config, or a draft to test before
    saving."""
    if cfg is None:
        ready, reason = _config_ready()
        host, port, user = settings.SMTP_HOST, int(settings.SMTP_PORT or 587), bool(settings.SMTP_USER)
    else:
        ready, reason = cfg.ready()
        host, port, user = cfg.host, int(cfg.port or 587), bool(cfg.user)

    if not ready:
        log.info("SMTP connection test skipped: %s", reason)
        return {"enabled": False, "ok": False, "reason": reason}

    try:
        with _open_client(cfg):
            return {"enabled": True, "ok": True, "host": host, "port": port, "authenticated": user}
    except Exception as exc:  # noqa: BLE001
        log.exception("SMTP connection test failed")
        return {"enabled": True, "ok": False, "host": host, "port": port,
                "authenticated": user, "error": str(exc)}


def _pick_send_config(db: Session, msg: CommunicationMessage, main_cfg: SmtpConfig) -> tuple[SmtpConfig, bool]:
    """Which SMTP identity should this message go out as? A personal identity for
    the message's owning user (when enabled and usable), else the company main
    mailbox. Returns (config, is_personal)."""
    personal = mail_identity_service.resolve_personal_smtp(db, msg)
    if personal is not None:
        return personal, True
    return main_cfg, False


def _fail_or_retry(db: Session, mid: int, error: str, results: list[dict[str, Any]]) -> None:
    msg = db.get(CommunicationMessage, mid)
    if msg is None:
        return
    retries = _bump_retry(msg, error)
    if retries >= MAX_SEND_RETRIES:
        _sync_delivery_state(db, msg, status="FAILED", error=error)
        results.append({"message_id": mid, "status": "FAILED", "retries": retries, "error": error})
    else:
        msg.error_message = error
        results.append({"message_id": mid, "status": "RETRY", "retries": retries, "error": error})
    db.commit()


def _send_bucket(message_ids: list[int], schema: str) -> list[dict[str, Any]]:
    """Send a disjoint slice of messages, reusing one SMTP connection per distinct
    sending identity. Each message goes out through its owning user's personal
    mailbox when one is mapped, else the company main mailbox; a personal-mailbox
    failure falls back once to the main mailbox so delivery still happens.

    Runs in its own thread with its own DB session. The tenant schema is passed in
    explicitly and re-established here because ContextVars do not cross thread
    boundaries — without this the thread's SessionLocal would target the default
    (public) schema."""
    with use_company(schema):
        results: list[dict[str, Any]] = []
        db: Session = SessionLocal()
        main_cfg = mail_config_service.get_smtp_config(db)
        clients: dict[tuple, smtplib.SMTP] = {}

        def _client_for(cfg: SmtpConfig) -> smtplib.SMTP:
            key = (cfg.host, int(cfg.port or 587), cfg.user)
            client = clients.get(key)
            if client is None:
                client = _open_client(cfg)
                clients[key] = client
            return client

        def _drop(cfg: SmtpConfig) -> None:
            key = (cfg.host, int(cfg.port or 587), cfg.user)
            client = clients.pop(key, None)
            if client is not None:
                try:
                    client.quit()
                except Exception:  # noqa: BLE001
                    pass

        try:
            for mid in message_ids:
                msg = db.get(CommunicationMessage, mid)
                # Re-check status: a user-initiated immediate send may have claimed it.
                if msg is None or msg.direction != "OUTGOING" or msg.status != "READY":
                    continue

                send_cfg, is_personal = _pick_send_config(db, msg, main_cfg)
                ok, reason = send_cfg.ready()
                if not ok and is_personal:
                    # Personal identity unusable → fall back to the main mailbox.
                    send_cfg, is_personal = main_cfg, False
                    ok, reason = send_cfg.ready()
                if not ok:
                    _fail_or_retry(db, mid, f"No usable SMTP config: {reason}", results)
                    continue

                try:
                    _client_for(send_cfg).send_message(_build_email(msg, send_cfg.from_addr))
                    _sync_delivery_state(db, msg, status="SENT")
                    db.commit()
                    results.append({"message_id": mid, "status": "SENT",
                                    "via": "personal" if is_personal else "main"})
                    continue
                except Exception as exc:  # noqa: BLE001
                    log.exception("Failed to send message id=%s", mid)
                    db.rollback()
                    _drop(send_cfg)  # connection may be dead — force a reconnect
                    # `exc` is cleared when the except block exits, so capture it.
                    err = str(exc)
                    personal_err = err if is_personal else None

                # A personal-mailbox failure retries once through the main mailbox.
                if is_personal and main_cfg.ready()[0]:
                    try:
                        _client_for(main_cfg).send_message(_build_email(msg, main_cfg.from_addr))
                        _sync_delivery_state(db, msg, status="SENT")
                        db.commit()
                        results.append({"message_id": mid, "status": "SENT", "via": "main_fallback",
                                        "personal_error": personal_err})
                        continue
                    except Exception as exc2:  # noqa: BLE001
                        log.exception("Main-mailbox fallback failed for id=%s", mid)
                        db.rollback()
                        _drop(main_cfg)
                        err = str(exc2)

                _fail_or_retry(db, mid, err, results)
        finally:
            for client in clients.values():
                try:
                    client.quit()
                except Exception:  # noqa: BLE001
                    pass
            db.close()
        return results


def send_ready_messages(limit: int | None = None, *, schema: str | None = None) -> dict[str, Any]:
    active_schema = schema or get_current_schema()

    # Gate: proceed if the company main mailbox is usable OR any user has a personal
    # sending identity (their mail can go out even when the main mailbox is off).
    db: Session = SessionLocal()
    try:
        main_ready, reason = mail_config_service.get_smtp_config(db).ready()
        any_personal = mail_identity_service.has_enabled_identities(db)
    finally:
        db.close()
    if not main_ready and not any_personal:
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
        results = _send_bucket(ids, active_schema)
    else:
        buckets = [b for b in (ids[i::workers] for i in range(workers)) if b]
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(buckets)) as ex:
            for res in ex.map(lambda b: _send_bucket(b, active_schema), buckets):
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

    Sends as the message's owning user when they have a personal identity, falling
    back to the company main mailbox (both when no identity exists and when a
    personal send fails).
    """
    msg = db.get(CommunicationMessage, message_id)
    if msg is None or msg.direction != "OUTGOING" or msg.status != "READY":
        return {"enabled": True, "sent": False, "reason": "not a queued outgoing message"}

    main_cfg = mail_config_service.get_smtp_config(db)
    send_cfg, is_personal = _pick_send_config(db, msg, main_cfg)
    ok, reason = send_cfg.ready()
    if not ok and is_personal:
        send_cfg, is_personal = main_cfg, False
        ok, reason = send_cfg.ready()
    if not ok:
        return {"enabled": False, "reason": reason, "sent": False}

    try:
        _send_one(_build_email(msg, send_cfg.from_addr), send_cfg)
        _sync_delivery_state(db, msg, status="SENT")
        db.commit()
        return {"enabled": True, "sent": True, "status": "SENT", "message_id": msg.id,
                "via": "personal" if is_personal else "main"}
    except Exception as exc:  # noqa: BLE001
        log.exception("Immediate send failed for message id=%s", message_id)
        db.rollback()
        err = str(exc)  # `exc` is cleared when the except block exits
        personal_err = err if is_personal else None
        # Personal-mailbox failure → try once through the main mailbox.
        if is_personal and main_cfg.ready()[0]:
            try:
                _send_one(_build_email(msg, main_cfg.from_addr), main_cfg)
                _sync_delivery_state(db, msg, status="SENT")
                db.commit()
                return {"enabled": True, "sent": True, "status": "SENT", "message_id": msg.id,
                        "via": "main_fallback", "personal_error": personal_err}
            except Exception as exc2:  # noqa: BLE001
                log.exception("Main-mailbox fallback failed for id=%s", message_id)
                db.rollback()
                err = str(exc2)
        msg = db.get(CommunicationMessage, message_id)
        if msg is not None:
            _bump_retry(msg, err)
            db.commit()
        return {"enabled": True, "sent": False, "status": "READY", "error": err}

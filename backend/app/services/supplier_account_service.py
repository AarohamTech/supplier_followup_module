"""Supplier portal login provisioning.

When an admin maps a supplier to one or more TO email addresses (Email Master),
each TO address gets a *supplier* login (`User.role = "supplier"`, scoped by
`supplier_id`). A temporary password is generated, the credentials are emailed,
and the account is flagged `must_change_password` so the first login forces a
change. Removing an address from the mapping deactivates its login (never deleted
— audit trail). Pure service layer: no FastAPI imports.
"""
from __future__ import annotations

import logging
import secrets
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.roles import Role
from ..models.user import User
from . import brand_email
from . import communication_message_service as msg_service
from . import user_service
from .user_service import EmailTakenError

log = logging.getLogger(__name__)


def generate_temp_password(length: int = 12) -> str:
    """A short, URL-safe temporary password (no ambiguous separators)."""
    return secrets.token_urlsafe(16)[:length]


def _normalize_emails(emails: list[str] | None) -> list[str]:
    """Lowercase, strip, drop blanks/dupes while preserving order."""
    seen: set[str] = set()
    out: list[str] = []
    for raw in emails or []:
        if not raw:
            continue
        email = raw.strip().lower()
        if not email or email in seen:
            continue
        seen.add(email)
        out.append(email)
    return out


def list_supplier_logins(db: Session, supplier_id: int) -> list[User]:
    return list(
        db.scalars(
            select(User)
            .where(User.supplier_id == supplier_id)
            .order_by(User.email)
        ).all()
    )


def _app_base_url() -> str:
    base = (settings.APP_BASE_URL or "").strip()
    if not base and settings.CORS_ORIGINS:
        base = str(settings.CORS_ORIGINS[0]).strip()
    return base.rstrip("/")


def send_credentials_email(
    db: Session,
    *,
    email: str,
    temp_password: str,
    supplier_name: str | None,
    supplier_id: int | None = None,
    is_reset: bool = False,
) -> bool:
    """Queue + immediately send a branded credentials email. Best-effort:
    returns True if it was sent now, False if queued/skipped (SMTP off etc.).
    Never raises — the temp password is also returned to the admin as a fallback.
    """
    portal_url = f"{_app_base_url()}/login" if _app_base_url() else "the supplier portal"
    heading = "Password reset" if is_reset else "Welcome to the Supplier Portal"
    intro = (
        "Your supplier portal password has been reset."
        if is_reset
        else f"A supplier portal account has been created for {supplier_name or 'your company'}."
    )
    inner = (
        brand_email.header_html("Supplier Portal access")
        + '<div style="padding:20px 22px;color:#1f2937;font-size:14px;line-height:1.6;">'
        f"<h2 style='margin:0 0 10px;font-size:18px;color:#111827;'>{heading}</h2>"
        f"<p style='margin:0 0 14px;'>{intro}</p>"
        "<table role='presentation' cellpadding='0' cellspacing='0' "
        "style='border-collapse:collapse;margin:0 0 14px;font-size:14px;'>"
        f"<tr><td style='padding:4px 16px 4px 0;color:#6B7280;'>Login email</td>"
        f"<td style='padding:4px 0;font-weight:600;'>{email}</td></tr>"
        f"<tr><td style='padding:4px 16px 4px 0;color:#6B7280;'>Temporary password</td>"
        f"<td style='padding:4px 0;font-weight:600;font-family:monospace;'>{temp_password}</td></tr>"
        "</table>"
        f"<p style='margin:0 0 14px;'>Sign in at <a href='{portal_url}' "
        f"style='color:#E11D2E;font-weight:600;'>{portal_url}</a>. "
        "For your security, you'll be asked to set a new password on first login.</p>"
        "</div>"
        + brand_email.footer_html(
            "This is an automated message from the Harmony × Hariom Supplier Follow-up system."
        )
    )
    body_html = brand_email.shell(inner)
    body_text = (
        f"{intro}\n\n"
        f"Login email: {email}\n"
        f"Temporary password: {temp_password}\n\n"
        f"Sign in at {portal_url}. You'll be asked to set a new password on first login."
    )
    subject = (
        "Your Supplier Portal password has been reset"
        if is_reset
        else "Your Supplier Portal login details"
    )

    try:
        msg = msg_service.queue_outgoing_message(
            db,
            supplier_id=supplier_id,
            supplier_name=supplier_name,
            subject=subject,
            body=body_text,
            body_html=body_html,
            to_emails=[email],
            receiver_email=email,
            mail_type="SUPPLIER_PORTAL_CREDENTIALS",
        )
    except Exception:  # noqa: BLE001
        log.exception("Failed to queue credentials email for %s", email)
        return False

    # Send immediately so the supplier gets credentials right away; if SMTP is
    # off/unavailable the message stays READY for the send cron to retry.
    try:
        from ..workers import mail_send_worker

        result = mail_send_worker.send_message_now(db, msg.id)
        return bool(result.get("sent"))
    except Exception:  # noqa: BLE001
        log.exception("Immediate credentials send failed for %s (left queued)", email)
        return False


def sync_supplier_logins(
    db: Session,
    *,
    supplier_id: int,
    supplier_name: str | None,
    to_emails: list[str] | None,
    send_email: bool = True,
) -> dict[str, Any]:
    """Reconcile the supplier's TO emails with their portal logins.

    - missing login for a TO email → create (temp password, must_change=True) + email
    - existing login for this supplier → ensure active (reactivate if disabled)
    - login no longer in TO emails → deactivate (keep the row)
    - a TO email already owned by a *staff* user or a *different* supplier → skip
      it and record a conflict (never hijack an existing account)

    Returns a summary the admin UI surfaces (incl. temp passwords as an
    SMTP-off fallback).
    """
    wanted = _normalize_emails(to_emails)
    created: list[dict[str, Any]] = []
    reactivated: list[str] = []
    deactivated: list[str] = []
    conflicts: list[dict[str, str]] = []

    wanted_set = set(wanted)

    for email in wanted:
        existing = user_service.get_by_email(db, email)
        if existing is not None:
            if existing.supplier_id == supplier_id:
                if not existing.is_active:
                    existing.is_active = True
                    reactivated.append(email)
            else:
                reason = (
                    "belongs to a staff account"
                    if existing.supplier_id is None
                    else "belongs to another supplier"
                )
                conflicts.append({"email": email, "reason": reason})
            continue

        temp_password = generate_temp_password()
        try:
            user_service.create_user(
                db,
                email=email,
                password=temp_password,
                full_name=supplier_name,
                role=Role.SUPPLIER,
                is_active=True,
                supplier_id=supplier_id,
                must_change_password=True,
                commit=False,
            )
        except EmailTakenError:
            # Raced with another create — treat as a conflict rather than crash.
            conflicts.append({"email": email, "reason": "account already exists"})
            continue
        created.append({"email": email, "temp_password": temp_password})

    # Deactivate logins that are no longer mapped as TO addresses.
    for login in list_supplier_logins(db, supplier_id):
        if login.email not in wanted_set and login.is_active:
            login.is_active = False
            deactivated.append(login.email)

    db.commit()

    emailed: list[str] = []
    if send_email:
        for item in created:
            sent = send_credentials_email(
                db,
                email=item["email"],
                temp_password=item["temp_password"],
                supplier_name=supplier_name,
                supplier_id=supplier_id,
            )
            if sent:
                emailed.append(item["email"])

    return {
        "created": created,
        "reactivated": reactivated,
        "deactivated": deactivated,
        "conflicts": conflicts,
        "emailed": emailed,
    }


def deactivate_supplier_logins(db: Session, supplier_id: int) -> list[str]:
    """Disable all logins for a supplier (mapping deleted / deactivated)."""
    disabled: list[str] = []
    for login in list_supplier_logins(db, supplier_id):
        if login.is_active:
            login.is_active = False
            disabled.append(login.email)
    if disabled:
        db.commit()
    return disabled


def reset_supplier_login_password(
    db: Session, user: User, *, send_email: bool = True
) -> dict[str, Any]:
    """Admin reset: new temp password, force change, email it. Returns the temp
    password (admin sees it as a fallback when SMTP is off)."""
    temp_password = generate_temp_password()
    user_service.set_password(db, user, temp_password, must_change=True)
    supplier_name = user.full_name
    emailed = False
    if send_email:
        emailed = send_credentials_email(
            db,
            email=user.email,
            temp_password=temp_password,
            supplier_name=supplier_name,
            supplier_id=user.supplier_id,
            is_reset=True,
        )
    return {"email": user.email, "temp_password": temp_password, "emailed": emailed}

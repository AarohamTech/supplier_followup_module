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

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.roles import Role
from ..models.supplier import SupplierMaster
from ..models.supplier_email import SupplierEmail
from ..models.user import User
from . import brand_email
from . import communication_message_service as msg_service
from . import company_service
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


def _company_scope(db: Session) -> tuple[int | None, int | None]:
    """(active company id, default company id). `users` is shared by every
    company while a supplier_id only means something inside one company, so
    every supplier-login lookup is scoped to the company the admin is in.
    Logins with company_id NULL are legacy default-company (102) logins."""
    company_id = company_service.current_company_id(db)
    default = company_service.get_default(db)
    return company_id, (default.id if default is not None else None)


def _effective_company_id(user: User, default_id: int | None) -> int | None:
    return user.company_id if user.company_id is not None else default_id


def _company_filter(company_id: int | None, default_id: int | None):
    if company_id == default_id:
        return or_(User.company_id == company_id, User.company_id.is_(None))
    return User.company_id == company_id


def list_supplier_logins(db: Session, supplier_id: int) -> list[User]:
    """The supplier's portal logins in the active company only. Supplier ids
    overlap across companies (each has its own supplier_master), so an
    unscoped lookup would list -- and the sync would deactivate -- another
    company's logins."""
    company_id, default_id = _company_scope(db)
    return list(
        db.scalars(
            select(User)
            .where(User.supplier_id == supplier_id, _company_filter(company_id, default_id))
            .order_by(User.email)
        ).all()
    )


def active_company_filter(db: Session):
    """SQL filter: accounts that belong to the company the admin is in."""
    return _company_filter(*_company_scope(db))


def login_in_active_company(db: Session, user: User) -> bool:
    """True when this supplier login belongs to the company the admin is in."""
    company_id, default_id = _company_scope(db)
    return _effective_company_id(user, default_id) == company_id


def _norm_name(name: str | None) -> str:
    return " ".join((name or "").upper().split())


def _owner_claims_email(db: Session, owner_supplier_id: int, email: str) -> bool:
    """True when the owning supplier still has an active mapping that lists
    this email as a TO address (i.e. the login is genuinely in use)."""
    rows = db.scalars(
        select(SupplierEmail).where(
            SupplierEmail.supplier_id == owner_supplier_id,
            SupplierEmail.is_active.is_(True),
        )
    ).all()
    return any(email in _normalize_emails(list(r.to_emails or [])) for r in rows)


def _classify_other_supplier_login(
    db: Session, login: User, *, email: str, supplier_name: str | None
) -> tuple[bool, str]:
    """A login in this company with this email points at another supplier_id.
    Returns (relink, conflict_reason).

    Re-link (move the login to the supplier being saved) when the old link is
    stale: the owning supplier no longer exists, it is the same supplier under
    another id (same name, e.g. a re-created master row), or no active mapping
    of the owner lists this email any more. Otherwise it is a genuine conflict:
    two different suppliers in one company cannot share one login.
    """
    owner = db.get(SupplierMaster, login.supplier_id) if login.supplier_id is not None else None
    if owner is None:
        return True, ""
    if _norm_name(owner.supplier_name) and _norm_name(owner.supplier_name) == _norm_name(supplier_name):
        return True, ""
    if not _owner_claims_email(db, owner.id, email):
        return True, ""
    return False, (
        f"already the portal login of supplier '{owner.supplier_name}' (id {owner.id}) "
        "in this company; remove it from that supplier's TO emails first"
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
    audience: str = "supplier",
    login_id: str | None = None,
) -> bool:
    """Queue + immediately send a branded credentials email. Best-effort:
    returns True if it was sent now, False if queued/skipped (SMTP off etc.).
    Never raises — the temp password is also returned to the admin as a fallback.

    ``audience="employee"`` words it for the employee portal, where people sign
    in with a username (``login_id``) rather than their email.
    """
    employee = audience == "employee"
    portal = "Employee Portal" if employee else "Supplier Portal"
    portal_url = f"{_app_base_url()}/login" if _app_base_url() else f"the {portal.lower()}"
    login_label = "Username" if employee and login_id else "Login email"
    login_value = login_id if employee and login_id else email
    heading = "Password reset" if is_reset else f"Welcome to the {portal}"
    if is_reset:
        intro = f"Your {portal.lower()} password has been reset."
    elif employee:
        intro = f"An employee portal account has been created for {supplier_name or 'you'}."
    else:
        intro = f"A supplier portal account has been created for {supplier_name or 'your company'}."
    inner = (
        brand_email.header_html(f"{portal} access")
        + '<div style="padding:20px 22px;color:#1f2937;font-size:14px;line-height:1.6;">'
        f"<h2 style='margin:0 0 10px;font-size:18px;color:#111827;'>{heading}</h2>"
        f"<p style='margin:0 0 14px;'>{intro}</p>"
        "<table role='presentation' cellpadding='0' cellspacing='0' "
        "style='border-collapse:collapse;margin:0 0 14px;font-size:14px;'>"
        f"<tr><td style='padding:4px 16px 4px 0;color:#6B7280;'>{login_label}</td>"
        f"<td style='padding:4px 0;font-weight:600;'>{login_value}</td></tr>"
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
        f"{login_label}: {login_value}\n"
        f"Temporary password: {temp_password}\n\n"
        f"Sign in at {portal_url}. You'll be asked to set a new password on first login."
    )
    subject = (
        f"Your {portal} password has been reset"
        if is_reset
        else f"Your {portal} login details"
    )
    mail_type = "EMPLOYEE_PORTAL_CREDENTIALS" if employee else "SUPPLIER_PORTAL_CREDENTIALS"

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
            mail_type=mail_type,
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
    """Reconcile the supplier's TO emails with their portal logins in the
    active company.

    - missing login for a TO email (in this company) -> create (temp password,
      must_change=True) + email. A login with the same email in ANOTHER company
      does not block: email is unique per company (each login is pinned to one).
    - existing login for this supplier -> ensure active (reactivate if disabled)
    - existing login in this company that points at a stale/same-named supplier
      -> re-link it to this supplier (reported as `relinked`)
    - login no longer in TO emails -> deactivate (keep the row)
    - a TO email owned by a staff/employee account, or by a different live
      supplier in this company -> skip it and record a conflict that names the
      owner (never hijack an account that is in use)

    Returns a summary the admin UI surfaces (incl. temp passwords as an
    SMTP-off fallback).
    """
    wanted = _normalize_emails(to_emails)
    created: list[dict[str, Any]] = []
    reactivated: list[str] = []
    relinked: list[str] = []
    deactivated: list[str] = []
    conflicts: list[dict[str, str]] = []

    wanted_set = set(wanted)
    company_id, default_id = _company_scope(db)

    for email in wanted:
        accounts = user_service.get_all_by_email(db, email)

        internal = next((u for u in accounts if u.supplier_id is None), None)
        if internal is not None and (
            internal.emp_code is None  # staff accounts span every company
            or _effective_company_id(internal, default_id) == company_id
        ):
            kind = "an employee account" if internal.emp_code is not None else "a staff account"
            label = internal.username or internal.full_name or internal.email
            conflicts.append({"email": email, "reason": f"belongs to {kind} ({label})"})
            continue

        existing = next(
            (u for u in accounts
             if u.supplier_id is not None
             and _effective_company_id(u, default_id) == company_id),
            None,
        )
        if existing is not None:
            if existing.supplier_id == supplier_id:
                if not existing.is_active:
                    existing.is_active = True
                    reactivated.append(email)
                continue
            relink, reason = _classify_other_supplier_login(
                db, existing, email=email, supplier_name=supplier_name
            )
            if not relink:
                conflicts.append({"email": email, "reason": reason})
                continue
            log.info(
                "[supplier-login] re-linking %s from supplier_id=%s to %s (company_id=%s)",
                email, existing.supplier_id, supplier_id, company_id,
            )
            existing.supplier_id = supplier_id
            existing.full_name = supplier_name or existing.full_name
            if existing.company_id is None and company_id is not None:
                existing.company_id = company_id
            existing.is_active = True
            relinked.append(email)
            continue

        temp_password = generate_temp_password()
        try:
            with db.begin_nested():
                user_service.create_user(
                    db,
                    email=email,
                    password=temp_password,
                    full_name=supplier_name,
                    role=Role.SUPPLIER,
                    is_active=True,
                    supplier_id=supplier_id,
                    must_change_password=True,
                    # Pin to the company the admin is switched into (a supplier_id
                    # only means something inside that company's schema).
                    company_id=company_id,
                    commit=False,
                    # The company-scoped rule above replaces the global email check.
                    check_email=False,
                )
        except (EmailTakenError, IntegrityError):
            # Raced with another create, or the DB still has the old global
            # unique email index: report it rather than crash.
            log.warning("[supplier-login] could not create login for %s", email, exc_info=True)
            conflicts.append({
                "email": email,
                "reason": "a login with this email already exists in another company "
                          "and the database still enforces one login per email",
            })
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
        "relinked": relinked,
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

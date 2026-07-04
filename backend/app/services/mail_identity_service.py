"""Per-user "send as" identities: resolution for the send worker + admin CRUD.

A :class:`UserMailIdentity` maps a user to their personal SMTP server. When an
outgoing message can be attributed to a user who has an *enabled* identity, the
send worker sends it through that mailbox (From = the user's address); otherwise
it uses the company main mailbox.

Attribution order for an outgoing message:
  1. ``sender_email`` → active user with that email, else
  2. the owner of the linked PO (``procurement_records.owner_emp_code``) → active
     employee user with that emp_code.
"""
from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..core import secret_crypto
from ..models.procurement import ProcurementRecord
from ..models.user import User
from ..models.user_mail_identity import UserMailIdentity
from .mail_config_service import SmtpConfig


# ── resolution (used by the send worker) ─────────────────────────────────────
def _user_by_email(db: Session, email: str | None) -> User | None:
    if not email or not email.strip():
        return None
    return db.scalar(
        select(User).where(
            func.lower(User.email) == email.strip().lower(),
            User.is_active.is_(True),
        )
    )


def _owner_user_for_message(db: Session, msg) -> User | None:
    rec: ProcurementRecord | None = None
    if getattr(msg, "procurement_record_id", None):
        rec = db.get(ProcurementRecord, msg.procurement_record_id)
    if rec is None and getattr(msg, "supplier_po_no", None):
        stmt = select(ProcurementRecord).where(
            ProcurementRecord.supplier_po_no == msg.supplier_po_no
        )
        if getattr(msg, "supplier_name", None):
            stmt = stmt.where(ProcurementRecord.supplier_name == msg.supplier_name)
        rec = db.scalars(stmt.limit(1)).first()
    if rec is None or not rec.owner_emp_code:
        return None
    return db.scalar(
        select(User).where(
            User.emp_code == rec.owner_emp_code,
            User.is_active.is_(True),
        )
    )


def owning_user(db: Session, msg) -> User | None:
    """The user this outgoing message should be sent *as*, if any."""
    return _user_by_email(db, getattr(msg, "sender_email", None)) or _owner_user_for_message(db, msg)


def to_smtp_config(identity: UserMailIdentity, user_email: str | None = None) -> SmtpConfig:
    from_addr = identity.from_email or identity.smtp_user or user_email or ""
    return SmtpConfig(
        enabled=True,
        host=identity.smtp_host or "",
        port=int(identity.smtp_port or 587),
        user=identity.smtp_user or "",
        password=secret_crypto.decrypt(identity.smtp_password_enc),
        from_addr=from_addr,
    )


def resolve_personal_smtp(db: Session, msg) -> SmtpConfig | None:
    """The personal SMTP config to send this message through, or None to use main."""
    user = owning_user(db, msg)
    if user is None:
        return None
    ident = db.scalar(select(UserMailIdentity).where(UserMailIdentity.user_id == user.id))
    if ident is None or not ident.enabled:
        return None
    cfg = to_smtp_config(ident, user.email)
    ok, _ = cfg.ready()
    return cfg if ok else None


def has_enabled_identities(db: Session) -> bool:
    """Cheap gate: is there any enabled personal identity at all? Lets the send
    worker keep its clean no-op when the main mailbox is disabled but a user still
    has personal credentials."""
    count = db.scalar(
        select(func.count(UserMailIdentity.id)).where(UserMailIdentity.enabled.is_(True))
    )
    return bool(count)


# ── admin CRUD ───────────────────────────────────────────────────────────────
def list_sender_users(db: Session) -> list[User]:
    """Internal accounts that can send mail (staff + employees; suppliers excluded)."""
    return list(
        db.scalars(
            select(User)
            .where(User.supplier_id.is_(None))
            .order_by(User.full_name, User.email)
        ).all()
    )

def get_identity(db: Session, user_id: int) -> UserMailIdentity | None:
    return db.scalar(select(UserMailIdentity).where(UserMailIdentity.user_id == user_id))


def upsert_identity(
    db: Session,
    user_id: int,
    *,
    enabled: bool,
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    from_email: str,
    use_ssl: bool,
    password: str | None = None,
) -> UserMailIdentity:
    ident = get_identity(db, user_id)
    if ident is None:
        ident = UserMailIdentity(user_id=user_id)
        db.add(ident)
    ident.enabled = bool(enabled)
    ident.smtp_host = (smtp_host or "").strip()
    ident.smtp_port = int(smtp_port or 587)
    ident.smtp_user = (smtp_user or "").strip()
    ident.from_email = (from_email or "").strip()
    ident.use_ssl = bool(use_ssl)
    if password:
        ident.smtp_password_enc = secret_crypto.encrypt(password)
    db.commit()
    db.refresh(ident)
    return ident


def delete_identity(db: Session, user_id: int) -> bool:
    ident = get_identity(db, user_id)
    if ident is None:
        return False
    db.delete(ident)
    db.commit()
    return True


def _mask(value: str | None) -> str:
    if not value:
        return ""
    if len(value) <= 2:
        return "*" * len(value)
    return value[0] + "*" * (len(value) - 2) + value[-1]


def identity_masked(ident: UserMailIdentity | None) -> dict | None:
    if ident is None:
        return None
    return {
        "enabled": ident.enabled,
        "smtp_host": ident.smtp_host,
        "smtp_port": ident.smtp_port,
        "smtp_user": ident.smtp_user,
        "from_email": ident.from_email,
        "use_ssl": ident.use_ssl,
        "password_masked": _mask(secret_crypto.decrypt(ident.smtp_password_enc)),
        "password_set": bool(ident.smtp_password_enc),
        "updated_at": ident.updated_at.isoformat() if ident.updated_at else None,
    }

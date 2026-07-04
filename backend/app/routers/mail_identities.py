"""Admin router: per-user personal SMTP identities ("send as" credentials).

An admin maps a user's own outgoing mail server here. Once mapped and enabled,
all outgoing mail attributed to that user is sent through their mailbox as them
(see ``services.mail_identity_service`` + ``workers.mail_send_worker``). Passwords
are stored encrypted and only ever returned masked.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..core.deps import require_admin
from ..database import get_db
from ..models.user import User
from ..services import mail_identity_service
from ..workers import mail_send_worker

# Router-level guard: admin only for the whole prefix.
router = APIRouter(
    prefix="/api/mail-identities",
    tags=["mail-identities"],
    dependencies=[Depends(require_admin)],
)


class IdentityPayload(BaseModel):
    enabled: bool = True
    smtp_host: str = ""
    smtp_port: int = Field(default=587, ge=0)
    smtp_user: str = ""
    from_email: str = ""
    use_ssl: bool = False
    # Blank/omitted keeps the stored password.
    password: str | None = None


def _user_row(db: Session, user: User) -> dict:
    ident = mail_identity_service.get_identity(db, user.id)
    return {
        "user_id": user.id,
        "email": user.email,
        "username": user.username,
        "full_name": user.full_name,
        "role": user.role,
        "emp_code": user.emp_code,
        "is_active": user.is_active,
        "identity": mail_identity_service.identity_masked(ident),
    }


@router.get("")
def list_identities(db: Session = Depends(get_db)) -> dict:
    """Every sender-capable user (staff + employees) with their identity status."""
    users = mail_identity_service.list_sender_users(db)
    return {"users": [_user_row(db, u) for u in users]}


@router.put("/{user_id}")
def upsert_identity(user_id: int, payload: IdentityPayload, db: Session = Depends(get_db)) -> dict:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    if user.supplier_id is not None:
        raise HTTPException(400, "Supplier accounts cannot have a personal sending identity")
    mail_identity_service.upsert_identity(
        db,
        user_id,
        enabled=payload.enabled,
        smtp_host=payload.smtp_host,
        smtp_port=payload.smtp_port,
        smtp_user=payload.smtp_user,
        from_email=payload.from_email or user.email,
        use_ssl=payload.use_ssl,
        password=payload.password,
    )
    return _user_row(db, user)


@router.delete("/{user_id}")
def delete_identity(user_id: int, db: Session = Depends(get_db)) -> dict:
    if not mail_identity_service.delete_identity(db, user_id):
        raise HTTPException(404, "No identity for this user")
    return {"ok": True, "user_id": user_id}


@router.post("/{user_id}/test")
def test_identity(user_id: int, db: Session = Depends(get_db)) -> dict:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    ident = mail_identity_service.get_identity(db, user_id)
    if ident is None:
        raise HTTPException(404, "No identity for this user")
    cfg = mail_identity_service.to_smtp_config(ident, user.email)
    return mail_send_worker.test_smtp_connection(cfg)

"""User persistence + authentication. No FastAPI imports — pure service layer."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.roles import DEFAULT_ROLE, Role, normalize_role
from ..core.security import hash_password, verify_password
from ..models.user import User


class EmailTakenError(ValueError):
    """Raised when creating/updating a user with an email already in use."""


class LastAdminError(ValueError):
    """Raised when an action would leave the system with no active admin."""


# ── Reads ────────────────────────────────────────────────────────────────────
def get(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


def get_by_email(db: Session, email: str) -> User | None:
    if not email:
        return None
    return db.scalar(select(User).where(func.lower(User.email) == email.strip().lower()))


def list_users(
    db: Session,
    *,
    role: str | None = None,
    is_active: bool | None = None,
    search: str | None = None,
) -> list[User]:
    stmt = select(User)
    if role:
        stmt = stmt.where(User.role == normalize_role(role))
    if is_active is not None:
        stmt = stmt.where(User.is_active.is_(is_active))
    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.where((User.email.ilike(like)) | (User.full_name.ilike(like)))
    stmt = stmt.order_by(User.created_at.asc())
    return list(db.scalars(stmt).all())


def count_active_admins(db: Session, *, exclude_id: int | None = None) -> int:
    stmt = select(func.count(User.id)).where(
        User.role == Role.ADMIN, User.is_active.is_(True)
    )
    if exclude_id is not None:
        stmt = stmt.where(User.id != exclude_id)
    return int(db.scalar(stmt) or 0)


# ── Writes ───────────────────────────────────────────────────────────────────
def create_user(
    db: Session,
    *,
    email: str,
    password: str,
    full_name: str | None = None,
    role: str = DEFAULT_ROLE,
    is_active: bool = True,
    commit: bool = True,
) -> User:
    if get_by_email(db, email) is not None:
        raise EmailTakenError(f"A user with email '{email}' already exists")
    user = User(
        email=email.strip().lower(),
        full_name=(full_name or None),
        hashed_password=hash_password(password),
        role=normalize_role(role),
        is_active=is_active,
    )
    db.add(user)
    if commit:
        db.commit()
        db.refresh(user)
    else:
        db.flush()
    return user


def update_user(
    db: Session,
    user_id: int,
    *,
    full_name: str | None = None,
    role: str | None = None,
    is_active: bool | None = None,
) -> User | None:
    user = db.get(User, user_id)
    if user is None:
        return None

    # Guard: never demote/deactivate the last active admin.
    demoting_admin = (
        user.role == Role.ADMIN
        and (
            (role is not None and normalize_role(role) != Role.ADMIN)
            or (is_active is False)
        )
    )
    if demoting_admin and count_active_admins(db, exclude_id=user.id) == 0:
        raise LastAdminError("Cannot remove the last active admin")

    if full_name is not None:
        user.full_name = full_name or None
    if role is not None:
        user.role = normalize_role(role)
    if is_active is not None:
        user.is_active = is_active

    db.commit()
    db.refresh(user)
    return user


def set_password(db: Session, user: User, new_password: str) -> User:
    user.hashed_password = hash_password(new_password)
    db.commit()
    db.refresh(user)
    return user


def authenticate(db: Session, email: str, password: str) -> User | None:
    user = get_by_email(db, email)
    if user is None or not user.is_active:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    user.last_login_at = datetime.utcnow()
    db.commit()
    db.refresh(user)
    return user


def ensure_seed_admin(
    db: Session, *, email: str, password: str, full_name: str | None
) -> bool:
    """Create the bootstrap admin if no users exist yet. Returns True if created."""
    has_any = db.scalar(select(func.count(User.id))) or 0
    if has_any:
        return False
    create_user(
        db,
        email=email,
        password=password,
        full_name=full_name,
        role=Role.ADMIN,
        is_active=True,
    )
    return True

"""Resolve task assignees against real user accounts.

Assignable = active staff or employee accounts (suppliers excluded).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.user import User


def display_name(user: User) -> str:
    return user.full_name or user.username or user.email or f"user#{user.id}"


def _account_type(user: User) -> str:
    return "employee" if user.emp_code else "staff"


def list_assignees(db: Session) -> list[dict]:
    rows = db.scalars(
        select(User)
        .where(User.is_active.is_(True), User.supplier_id.is_(None))
        .order_by(User.full_name, User.username)
    ).all()
    return [
        {"id": u.id, "label": display_name(u), "role": u.role, "type": _account_type(u)}
        for u in rows
    ]


def resolve_assignee(db: Session, user_id: int) -> tuple[User, str]:
    user = db.get(User, user_id)
    if user is None or not user.is_active or user.supplier_id is not None:
        raise ValueError("User is not an assignable staff/employee account")
    return user, display_name(user)

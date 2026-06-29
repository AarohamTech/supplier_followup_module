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


def list_mention_targets(db: Session, *, customer_limit: int = 50) -> list[dict]:
    """@-mention candidates for the /hi assistant: assignable users PLUS recent
    customers (distinct sender emails from customer_mails).

    Customer rows carry `id: 0` (no user account) and an `email` field. They are
    safe to *mention* (the UI inserts by label) but must NEVER be fed to the
    assignee/watcher pickers, which require real user ids — those keep using
    `list_assignees`.
    """
    from ..models.customer_mail import CustomerMail

    targets = list(list_assignees(db))

    rows = db.execute(
        select(CustomerMail.from_email, CustomerMail.customer_name, CustomerMail.from_name)
        .where(CustomerMail.from_email.isnot(None))
        .order_by(CustomerMail.received_at.desc().nullslast())
    ).all()
    seen: set[str] = set()
    for from_email, customer_name, from_name in rows:
        email = (from_email or "").strip()
        key = email.lower()
        if not email or key in seen:
            continue
        seen.add(key)
        label = (customer_name or from_name or email).strip()
        targets.append(
            {"id": 0, "label": label, "email": email, "role": "customer", "type": "customer"}
        )
        if len(seen) >= customer_limit:
            break
    return targets

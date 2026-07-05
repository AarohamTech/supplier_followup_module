"""Supplier -> app-user assignments.

An admin/manager maps each supplier to the people responsible for it. When a
supplier's email is fetched, the mail fetch worker routes it (assigns + notifies)
to those users. Assignees are internal *staff* users (not portal accounts), since
they can open the mail in the Communication Hub.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..models.supplier import SupplierMaster
from ..models.supplier_assignment import SupplierAssignment
from ..models.user import User


def user_brief(user: User) -> dict[str, Any]:
    return {
        "user_id": user.id,
        "full_name": user.full_name,
        "email": user.email,
        "role": user.role,
        "username": user.username,
        "emp_code": user.emp_code,
    }


def assignable_users(db: Session) -> list[User]:
    """Every active internal account (staff + employees). Only external supplier
    portal logins are excluded — a supplier can't be assigned its own mail."""
    return list(
        db.scalars(
            select(User)
            .where(
                User.is_active.is_(True),
                User.supplier_id.is_(None),
            )
            .order_by(User.full_name, User.email)
        ).all()
    )


def get_assignee_ids(db: Session, supplier_id: int) -> list[int]:
    return list(
        db.scalars(
            select(SupplierAssignment.user_id).where(
                SupplierAssignment.supplier_id == supplier_id
            )
        ).all()
    )


def _valid_user_ids(db: Session, user_ids: list[int]) -> list[int]:
    """Dedupe and keep only real, assignable user ids, preserving order."""
    if not user_ids:
        return []
    allowed = {u.id for u in assignable_users(db)}
    seen: set[int] = set()
    out: list[int] = []
    for raw in user_ids:
        try:
            uid = int(raw)
        except (TypeError, ValueError):
            continue
        if uid in allowed and uid not in seen:
            seen.add(uid)
            out.append(uid)
    return out


def set_assignees(db: Session, supplier_id: int, user_ids: list[int]) -> list[int]:
    """Replace a supplier's assignees with the given user ids. Returns the stored set."""
    valid = _valid_user_ids(db, user_ids)
    db.execute(delete(SupplierAssignment).where(SupplierAssignment.supplier_id == supplier_id))
    for uid in valid:
        db.add(SupplierAssignment(supplier_id=supplier_id, user_id=uid))
    db.commit()
    return valid


def list_page(
    db: Session, *, search: str | None = None, page: int | None = None, size: int | None = None
) -> tuple[list[dict[str, Any]], int]:
    """One page of suppliers with their assignees. Returns (rows, total). Omit
    page+size for all suppliers."""
    stmt = select(SupplierMaster)
    if search and search.strip():
        stmt = stmt.where(SupplierMaster.supplier_name.ilike(f"%{search.strip()}%"))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    stmt = stmt.order_by(SupplierMaster.supplier_name)
    if page and size:
        stmt = stmt.limit(size).offset((page - 1) * size)
    suppliers = list(db.scalars(stmt).all())

    sids = [s.id for s in suppliers]
    by_supplier: dict[int, list[int]] = {}
    if sids:
        for supplier_id, user_id in db.execute(
            select(SupplierAssignment.supplier_id, SupplierAssignment.user_id)
            .where(SupplierAssignment.supplier_id.in_(sids))
        ).all():
            by_supplier.setdefault(supplier_id, []).append(user_id)

    uids = {uid for ids in by_supplier.values() for uid in ids}
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_(uids))).all()} if uids else {}

    rows: list[dict[str, Any]] = []
    for s in suppliers:
        ids = by_supplier.get(s.id, [])
        rows.append({
            "supplier_id": s.id,
            "supplier_name": s.supplier_name,
            "assignees": [user_brief(users[uid]) for uid in ids if uid in users],
        })
    return rows, int(total)


def list_all(db: Session) -> list[dict[str, Any]]:
    """Every supplier with its assignees (unpaginated)."""
    rows, _ = list_page(db)
    return rows


def assignees_detail(db: Session, user_ids: list[int]) -> list[dict[str, Any]]:
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_(user_ids))).all()}
    return [user_brief(users[uid]) for uid in user_ids if uid in users]

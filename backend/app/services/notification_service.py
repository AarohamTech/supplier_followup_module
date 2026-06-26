"""Create + read in-app notifications. Pure service layer (no FastAPI).

Fan-out helpers target an audience and write one row per recipient user:
  - notify_staff    → every active internal (non-supplier) user
  - notify_supplier → every active login for a given supplier_id

Best-effort by design: notification failures must never break the action that
triggered them, so callers wrap these in try/except (or use the safe wrappers).
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models.notification import Notification
from ..models.user import User

log = logging.getLogger(__name__)


# ── Writes ────────────────────────────────────────────────────────────────────
def notify_users(db: Session, user_ids: list[int], **fields: Any) -> int:
    """Create the same notification for each user id. Returns rows created."""
    seen: set[int] = set()
    created = 0
    for uid in user_ids:
        if uid is None or uid in seen:
            continue
        seen.add(uid)
        db.add(Notification(user_id=uid, **fields))
        created += 1
    if created:
        db.commit()
    return created


def _active_staff_ids(db: Session, *, exclude_user_id: int | None = None) -> list[int]:
    stmt = select(User.id).where(User.is_active.is_(True), User.supplier_id.is_(None))
    if exclude_user_id is not None:
        stmt = stmt.where(User.id != exclude_user_id)
    return list(db.scalars(stmt).all())


def _active_supplier_ids(db: Session, supplier_id: int) -> list[int]:
    return list(
        db.scalars(
            select(User.id).where(
                User.is_active.is_(True), User.supplier_id == supplier_id
            )
        ).all()
    )


def notify_staff(db: Session, *, exclude_user_id: int | None = None, **fields: Any) -> int:
    return notify_users(db, _active_staff_ids(db, exclude_user_id=exclude_user_id), **fields)


def notify_supplier(db: Session, for_supplier_id: int | None, **fields: Any) -> int:
    """Notify every active login of a supplier. `for_supplier_id` is the audience;
    a `supplier_id=` in **fields is the notification's own context column.
    """
    if for_supplier_id is None:
        return 0
    return notify_users(db, _active_supplier_ids(db, for_supplier_id), **fields)


def safe(fn, *args, **kwargs) -> int:
    """Run a notify_* call swallowing any error (never breaks the caller)."""
    try:
        return fn(*args, **kwargs)
    except Exception:  # noqa: BLE001
        log.exception("Notification fan-out failed (ignored)")
        return 0


# ── Reads ─────────────────────────────────────────────────────────────────────
def list_for_user(
    db: Session, user_id: int, *, only_unread: bool = False, limit: int = 30
) -> list[Notification]:
    stmt = select(Notification).where(Notification.user_id == user_id)
    if only_unread:
        stmt = stmt.where(Notification.is_read.is_(False))
    stmt = stmt.order_by(Notification.created_at.desc()).limit(limit)
    return list(db.scalars(stmt).all())


def unread_count(db: Session, user_id: int) -> int:
    return int(
        db.scalar(
            select(func.count(Notification.id)).where(
                Notification.user_id == user_id, Notification.is_read.is_(False)
            )
        )
        or 0
    )


def mark_read(db: Session, user_id: int, notification_id: int) -> bool:
    row = db.get(Notification, notification_id)
    if row is None or row.user_id != user_id:
        return False
    if not row.is_read:
        row.is_read = True
        row.read_at = datetime.utcnow()
        db.commit()
    return True


def mark_all_read(db: Session, user_id: int) -> int:
    rows = db.scalars(
        select(Notification).where(
            Notification.user_id == user_id, Notification.is_read.is_(False)
        )
    ).all()
    now = datetime.utcnow()
    for row in rows:
        row.is_read = True
        row.read_at = now
    if rows:
        db.commit()
    return len(rows)

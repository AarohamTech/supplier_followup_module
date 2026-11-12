"""Task notifications — sent ONLY to the people involved in the task.

Recipients are ``task_visibility.involved_user_ids`` (creator, assigner,
assignee, watchers) minus the person who acted, so nobody is told about a task
they cannot open. Never a staff-wide broadcast.

Fan-out runs off the request path: routers pass FastAPI's ``BackgroundTasks``
and the rows are written after the response has gone out, in a fresh DB session
bound to the same company schema. Without ``BackgroundTasks`` (direct calls,
tests) it runs inline on the caller's session. Best-effort either way — a
notification failure never fails the task action.
"""
from __future__ import annotations

import logging
from typing import Any, Iterable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.tenant import get_current_schema, use_company
from ..models.communication_task import CommunicationTask
from ..models.notification import Notification
from ..models.user import User
from . import task_visibility

log = logging.getLogger(__name__)

STAFF_LINK = "/tasks"
EMPLOYEE_LINK = "/eportal/tasks"


def _link_for(user: User, task_id: int) -> str:
    base = EMPLOYEE_LINK if user.emp_code else STAFF_LINK
    return f"{base}?task={task_id}"


def _short(text: Optional[str], n: int = 80) -> str:
    text = (text or "").strip()
    return text if len(text) <= n else text[: n - 1] + "…"


def _message(kind: str, task: CommunicationTask, recipient_id: int, actor: str, ctx: dict) -> tuple[str, str, str | None]:
    """(type, title, body) for one recipient."""
    title = _short(task.title)
    is_assignee = task.assigned_to_user_id == recipient_id
    if kind == "CREATED":
        if is_assignee:
            return "TASK_ASSIGNED", f"{actor} assigned you a task", title
        return "TASK_CREATED", f"{actor} added you to a task", title
    if kind == "ASSIGNED":
        if is_assignee:
            return "TASK_ASSIGNED", f"{actor} assigned you a task", title
        who = task.assigned_to or "someone else"
        return "TASK_UPDATED", f"Task reassigned to {who}", title
    if kind == "WATCHER_ADDED":
        return "TASK_CREATED", f"{actor} added you to a task", title
    if kind == "STATUS":
        return "TASK_UPDATED", f"{actor} moved a task to {ctx.get('status') or task.status}", title
    if kind == "COMMENT":
        return "TASK_COMMENT", f"{actor} commented on “{title}”", _short(ctx.get("comment"), 140)
    return "TASK_UPDATED", f"{actor} updated a task", title


def notify(
    db: Session,
    task: CommunicationTask,
    *,
    kind: str,
    actor_id: Optional[int],
    actor_name: str,
    only_ids: Optional[Iterable[int]] = None,
    ctx: Optional[dict[str, Any]] = None,
) -> int:
    """Write one notification per involved user (minus the actor). Returns rows."""
    recipients = task_visibility.involved_user_ids(task)
    if only_ids is not None:
        recipients &= {int(i) for i in only_ids if i is not None}
    recipients.discard(actor_id)  # type: ignore[arg-type]
    if not recipients:
        return 0
    users = db.scalars(
        select(User).where(
            User.id.in_(recipients),
            User.is_active.is_(True),
            User.supplier_id.is_(None),  # suppliers never get internal task pings
        )
    ).all()
    created = 0
    for u in users:
        type_, title, body = _message(kind, task, u.id, actor_name, ctx or {})
        db.add(
            Notification(
                user_id=u.id,
                type=type_,
                title=title[:255],
                body=body,
                link=_link_for(u, task.id),
                supplier_id=task.supplier_id,
                supplier_po_no=task.supplier_po_no,
                procurement_record_id=task.procurement_record_id,
            )
        )
        created += 1
    if created:
        db.commit()
    return created


def _safe_notify(db: Session, task: CommunicationTask, **kw: Any) -> int:
    try:
        return notify(db, task, **kw)
    except Exception:  # noqa: BLE001
        log.exception("Task notification failed (ignored)")
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return 0


def _run_in_background(schema: str, task_id: int, kw: dict[str, Any]) -> None:
    from ..database import SessionLocal

    with use_company(schema):
        db = SessionLocal()
        try:
            task = db.get(CommunicationTask, task_id)
            if task is not None:
                _safe_notify(db, task, **kw)
        except Exception:  # noqa: BLE001
            log.exception("Background task notification failed (ignored)")
        finally:
            db.close()


def dispatch(background_tasks: Any, db: Session, task: CommunicationTask, **kw: Any) -> None:
    """Queue the fan-out after the response (or run inline without a queue)."""
    if background_tasks is None:
        _safe_notify(db, task, **kw)
        return
    background_tasks.add_task(_run_in_background, get_current_schema(), task.id, kw)

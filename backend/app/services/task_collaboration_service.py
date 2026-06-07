"""Service helpers for task comments and the immutable task activity log."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.communication_task import CommunicationTask
from ..models.task_collaboration import TaskActivityLog, TaskComment


def log_activity(
    db: Session,
    *,
    task_id: int,
    activity_type: str,
    old_value: Any = None,
    new_value: Any = None,
    created_by: str | None = None,
    commit: bool = False,
) -> TaskActivityLog:
    entry = TaskActivityLog(
        task_id=task_id,
        activity_type=activity_type,
        old_value=None if old_value is None else str(old_value)[:500],
        new_value=None if new_value is None else str(new_value)[:500],
        created_by=created_by,
    )
    db.add(entry)
    if commit:
        db.commit()
        db.refresh(entry)
    return entry


def record_task_changes(
    db: Session,
    task: CommunicationTask,
    changes: dict[str, Any],
    *,
    created_by: str | None = None,
) -> list[TaskActivityLog]:
    """Translate a dict of changed fields into activity-log rows.

    Caller passes {field: (old, new)} or just compares before/after.
    """
    field_map = {
        "status": "STATUS_CHANGED",
        "assigned_to": "ASSIGNEE_CHANGED",
        "priority": "PRIORITY_CHANGED",
        "due_date": "DUE_DATE_CHANGED",
        "escalation_level": "ESCALATED",
    }
    entries: list[TaskActivityLog] = []
    for field, (old, new) in changes.items():
        activity_type = field_map.get(field)
        if not activity_type or old == new:
            continue
        entries.append(
            log_activity(
                db,
                task_id=task.id,
                activity_type=activity_type,
                old_value=old,
                new_value=new,
                created_by=created_by,
            )
        )
    return entries


def add_comment(
    db: Session,
    *,
    task_id: int,
    comment: str,
    created_by: str | None = None,
    commit: bool = True,
) -> TaskComment:
    task = db.get(CommunicationTask, task_id)
    if task is None:
        raise ValueError("Task not found")
    row = TaskComment(task_id=task_id, comment=comment, created_by=created_by)
    db.add(row)
    db.flush()
    task.comments_count = (task.comments_count or 0) + 1
    log_activity(
        db,
        task_id=task_id,
        activity_type="COMMENT_ADDED",
        new_value=comment[:120],
        created_by=created_by,
    )
    if commit:
        db.commit()
        db.refresh(row)
    return row


def list_comments(db: Session, task_id: int) -> list[TaskComment]:
    return list(
        db.scalars(
            select(TaskComment)
            .where(TaskComment.task_id == task_id)
            .order_by(TaskComment.created_at.asc())
        ).all()
    )


def list_activity(db: Session, task_id: int, limit: int = 100) -> list[TaskActivityLog]:
    return list(
        db.scalars(
            select(TaskActivityLog)
            .where(TaskActivityLog.task_id == task_id)
            .order_by(TaskActivityLog.created_at.desc())
            .limit(limit)
        ).all()
    )

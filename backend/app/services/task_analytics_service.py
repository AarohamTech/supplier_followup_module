"""Aggregate task metrics + an Excel export, computed from the task table
and the append-only activity log."""
from __future__ import annotations

import io
from collections import Counter
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.communication_task import CommunicationTask
from ..models.task_collaboration import TaskActivityLog


def compute_analytics(db: Session) -> dict:
    tasks = list(db.scalars(select(CommunicationTask)).all())
    now = datetime.utcnow()
    today = now.date()

    by_status: Counter = Counter()
    by_priority: Counter = Counter()
    by_source: Counter = Counter()
    assignee: dict[int, dict] = {}
    cycle_hours: list[float] = []
    open_count = overdue = done = due_today = 0

    for t in tasks:
        by_status[t.status] += 1
        by_priority[t.priority] += 1
        by_source[t.task_source] += 1
        is_done = t.status == "DONE"
        if is_done:
            done += 1
            if t.closed_at and t.created_at:
                cycle_hours.append((t.closed_at - t.created_at).total_seconds() / 3600.0)
        else:
            open_count += 1
        is_overdue = (not is_done) and t.due_date is not None and t.due_date < now
        if is_overdue:
            overdue += 1
        if (not is_done) and t.due_date is not None and t.due_date.date() == today:
            due_today += 1

        if t.assigned_to_user_id:
            row = assignee.setdefault(
                t.assigned_to_user_id,
                {"user_id": t.assigned_to_user_id, "name": t.assigned_to or f"user#{t.assigned_to_user_id}",
                 "open": 0, "overdue": 0, "done": 0},
            )
            if is_done:
                row["done"] += 1
            else:
                row["open"] += 1
            if is_overdue:
                row["overdue"] += 1

    return {
        "totals": {
            "total": len(tasks), "open": open_count, "overdue": overdue,
            "done": done, "due_today": due_today,
        },
        "by_status": dict(by_status),
        "by_priority": dict(by_priority),
        "by_source": dict(by_source),
        "by_assignee": sorted(assignee.values(), key=lambda r: r["name"].lower()),
        "avg_cycle_hours": round(sum(cycle_hours) / len(cycle_hours), 1) if cycle_hours else None,
        "throughput": _throughput(tasks),
    }


def _throughput(tasks: list[CommunicationTask]) -> list[dict]:
    created: Counter = Counter()
    completed: Counter = Counter()
    for t in tasks:
        if t.created_at:
            created[t.created_at.date().isoformat()] += 1
        if t.status == "DONE" and t.closed_at:
            completed[t.closed_at.date().isoformat()] += 1
    days = sorted(set(created) | set(completed))
    return [{"date": d, "created": created.get(d, 0), "completed": completed.get(d, 0)} for d in days]


_TASK_COLUMNS = (
    "id", "title", "status", "priority", "signal", "task_source",
    "supplier_name", "supplier_po_no", "material_name",
    "assigned_to_user_id", "assigned_to", "progress_percent",
    "comments_count", "escalation_level", "due_date", "closed_at",
    "created_at", "updated_at",
)


def export_workbook(db: Session) -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Tasks"
    ws.append(list(_TASK_COLUMNS))
    for t in db.scalars(select(CommunicationTask).order_by(CommunicationTask.id)).all():
        ws.append([_cell(getattr(t, c)) for c in _TASK_COLUMNS])

    ws2 = wb.create_sheet("Activity")
    ws2.append(["id", "task_id", "activity_type", "old_value", "new_value",
                "created_by", "created_by_id", "created_at"])
    for a in db.scalars(select(TaskActivityLog).order_by(TaskActivityLog.id)).all():
        ws2.append([a.id, a.task_id, a.activity_type, a.old_value, a.new_value,
                    a.created_by, a.created_by_id, _cell(a.created_at)])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _cell(value):
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    return value

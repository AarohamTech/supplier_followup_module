from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.deps import get_current_staff
from ..database import get_db
from ..models.communication_task import (
    TASK_PRIORITIES,
    TASK_SIGNALS,
    TASK_SOURCES,
    TASK_STATUSES,
    CommunicationTask,
)
from ..models.user import User
from ..schemas.communication_task import (
    CommunicationTaskCreate,
    CommunicationTaskOut,
    CommunicationTaskUpdate,
)
from ..services import ai_service
from ..services import task_assignment_service as assign
from ..services import task_collaboration_service as collab

router = APIRouter(prefix="/api/communication", tags=["communication"])
tasks_router = APIRouter(prefix="/api/tasks", tags=["tasks"])


# ──────────────────────────────────────────────────────────────────────────────
# Tasks CRUD
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/tasks", response_model=list[CommunicationTaskOut])
def list_tasks(
    db: Session = Depends(get_db),
    supplier_name: Optional[str] = None,
    supplier_po_no: Optional[str] = None,
    linked_mail_id: Optional[int] = None,
    status: Optional[str] = None,
    assigned_to: Optional[str] = None,
    task_source: Optional[str] = None,
    customer_mail_id: Optional[int] = None,
    limit: int = Query(200, ge=1, le=1000),
):
    stmt = select(CommunicationTask)
    if supplier_name:
        stmt = stmt.where(CommunicationTask.supplier_name.ilike(f"%{supplier_name}%"))
    if supplier_po_no:
        stmt = stmt.where(CommunicationTask.supplier_po_no == supplier_po_no)
    if linked_mail_id is not None:
        stmt = stmt.where(CommunicationTask.linked_mail_id == linked_mail_id)
    if status:
        stmt = stmt.where(CommunicationTask.status == status)
    if assigned_to:
        stmt = stmt.where(CommunicationTask.assigned_to == assigned_to)
    if task_source:
        stmt = stmt.where(CommunicationTask.task_source == task_source)
    if customer_mail_id is not None:
        stmt = stmt.where(CommunicationTask.customer_mail_id == customer_mail_id)
    return db.scalars(stmt.order_by(CommunicationTask.created_at.desc()).limit(limit)).all()


@router.get("/tasks/{task_id}", response_model=CommunicationTaskOut)
def get_task(task_id: int, db: Session = Depends(get_db)):
    row = db.get(CommunicationTask, task_id)
    if not row:
        raise HTTPException(404, "Task not found")
    return row


@router.get("/assignees")
def list_assignees(db: Session = Depends(get_db)):
    """Active staff + employee accounts selectable as task assignees/watchers."""
    return assign.list_assignees(db)


@router.post("/tasks", response_model=CommunicationTaskOut, status_code=201)
def create_task(
    payload: CommunicationTaskCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_staff),
):
    _validate_enum("priority", payload.priority, TASK_PRIORITIES)
    _validate_enum("status", payload.status, TASK_STATUSES)
    _validate_enum("signal", payload.signal, TASK_SIGNALS)
    if payload.task_source:
        _validate_enum("task_source", payload.task_source, TASK_SOURCES)

    data = payload.model_dump()
    if data.get("assigned_to_user_id") is not None:
        try:
            _, name = assign.resolve_assignee(db, data["assigned_to_user_id"])
        except ValueError as e:
            raise HTTPException(422, str(e))
        data["assigned_to"] = name
        data["assigned_at"] = datetime.utcnow()
    data["assigned_by"] = assign.display_name(actor)

    row = CommunicationTask(**data)
    db.add(row)
    db.flush()
    collab.log_activity(
        db,
        task_id=row.id,
        activity_type="CREATED",
        new_value=row.title,
        created_by=assign.display_name(actor),
        created_by_id=actor.id,
    )
    db.commit()
    db.refresh(row)
    return row


@router.patch("/tasks/{task_id}", response_model=CommunicationTaskOut)
def update_task(
    task_id: int,
    payload: CommunicationTaskUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_staff),
):
    row = db.get(CommunicationTask, task_id)
    if not row:
        raise HTTPException(404, "Task not found")

    data = payload.model_dump(exclude_unset=True)
    if "priority" in data:
        _validate_enum("priority", data["priority"], TASK_PRIORITIES)
    if "status" in data:
        _validate_enum("status", data["status"], TASK_STATUSES)
    if "signal" in data:
        _validate_enum("signal", data["signal"], TASK_SIGNALS)
    if "task_source" in data and data["task_source"] is not None:
        _validate_enum("task_source", data["task_source"], TASK_SOURCES)

    actor_name = assign.display_name(actor)

    # Resolve a new assignee (FK → denormalized name + timestamp).
    if "assigned_to_user_id" in data and data["assigned_to_user_id"] is not None:
        try:
            _, name = assign.resolve_assignee(db, data["assigned_to_user_id"])
        except ValueError as e:
            raise HTTPException(422, str(e))
        data["assigned_to"] = name
        data["assigned_at"] = datetime.utcnow()

    # Progress convenience rules.
    if data.get("status") == "DONE":
        data["progress_percent"] = 100
    elif data.get("status") == "BACKLOG":
        data["progress_percent"] = 0

    tracked = (
        "status", "assigned_to_user_id", "priority", "due_date",
        "progress_percent", "escalation_level",
    )
    changes = {
        key: (getattr(row, key), data[key])
        for key in tracked
        if key in data and getattr(row, key) != data[key]
    }

    for key, value in data.items():
        setattr(row, key, value)

    if data.get("status") == "DONE" and not row.closed_at:
        row.closed_at = datetime.utcnow()
    elif "status" in data and data["status"] != "DONE":
        row.closed_at = None

    if changes:
        collab.record_task_changes(
            db, row, changes, created_by=actor_name, created_by_id=actor.id
        )

    db.commit()
    db.refresh(row)
    return row


@router.delete("/tasks/{task_id}", status_code=204)
def delete_task(task_id: int, db: Session = Depends(get_db)):
    row = db.get(CommunicationTask, task_id)
    if not row:
        raise HTTPException(404, "Task not found")
    db.delete(row)
    db.commit()


# ──────────────────────────────────────────────────────────────────────────────
# Dashboard counters for KPI strip (legacy + unified)
# ──────────────────────────────────────────────────────────────────────────────
def _task_counts(db: Session) -> dict[str, int]:
    def count_where(*conds):
        stmt = select(func.count(CommunicationTask.id))
        for c in conds:
            stmt = stmt.where(c)
        return int(db.execute(stmt).scalar_one() or 0)

    now = datetime.utcnow()
    today = now.date()
    return {
        "total_tasks": count_where(),
        "todo": count_where(CommunicationTask.status == "TODO"),
        "waiting": count_where(CommunicationTask.status == "WAITING_SUPPLIER"),
        "in_progress": count_where(CommunicationTask.status == "IN_PROGRESS"),
        "done": count_where(CommunicationTask.status == "DONE"),
        "overdue": count_where(
            CommunicationTask.status != "DONE",
            CommunicationTask.due_date.isnot(None),
            CommunicationTask.due_date < now,
        ),
        "due_today": count_where(
            CommunicationTask.status != "DONE",
            CommunicationTask.due_date.isnot(None),
            func.date(CommunicationTask.due_date) == today,
        ),
        "critical": count_where(CommunicationTask.signal == "BLACK"),
        "supplier_tasks": count_where(CommunicationTask.task_source == "SUPPLIER"),
        "customer_tasks": count_where(CommunicationTask.task_source == "CUSTOMER"),
        "internal_tasks": count_where(CommunicationTask.task_source == "INTERNAL"),
        "escalation_tasks": count_where(CommunicationTask.task_source == "ESCALATION"),
    }


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db)):
    return _task_counts(db)


# Unified task management endpoints under /api/tasks/...
@tasks_router.get("/dashboard")
def tasks_dashboard(db: Session = Depends(get_db)):
    return _task_counts(db)


@tasks_router.get("", response_model=list[CommunicationTaskOut])
def tasks_index(
    db: Session = Depends(get_db),
    task_source: Optional[str] = None,
    status: Optional[str] = None,
    assigned_to: Optional[str] = None,
    supplier_name: Optional[str] = None,
    supplier_po_no: Optional[str] = None,
    customer_mail_id: Optional[int] = None,
    overdue: bool = Query(default=False),
    limit: int = Query(default=200, ge=1, le=1000),
):
    stmt = select(CommunicationTask)
    if task_source:
        stmt = stmt.where(CommunicationTask.task_source == task_source)
    if status:
        stmt = stmt.where(CommunicationTask.status == status)
    if assigned_to:
        stmt = stmt.where(CommunicationTask.assigned_to == assigned_to)
    if supplier_name:
        stmt = stmt.where(CommunicationTask.supplier_name.ilike(f"%{supplier_name}%"))
    if supplier_po_no:
        stmt = stmt.where(CommunicationTask.supplier_po_no == supplier_po_no)
    if customer_mail_id is not None:
        stmt = stmt.where(CommunicationTask.customer_mail_id == customer_mail_id)
    if overdue:
        now = datetime.utcnow()
        stmt = stmt.where(
            CommunicationTask.status != "DONE",
            CommunicationTask.due_date.isnot(None),
            CommunicationTask.due_date < now,
        )
    return db.scalars(stmt.order_by(CommunicationTask.created_at.desc()).limit(limit)).all()


# ──────────────────────────────────────────────────────────────────────────────
# Task comments + activity log
# ──────────────────────────────────────────────────────────────────────────────
def _comment_out(c) -> dict:
    return {
        "id": c.id,
        "task_id": c.task_id,
        "comment": c.comment,
        "created_by": c.created_by,
        "created_at": c.created_at,
    }


def _activity_out(a) -> dict:
    return {
        "id": a.id,
        "task_id": a.task_id,
        "activity_type": a.activity_type,
        "old_value": a.old_value,
        "new_value": a.new_value,
        "created_by": a.created_by,
        "created_at": a.created_at,
    }


@tasks_router.get("/{task_id}/comments")
def task_comments(task_id: int, db: Session = Depends(get_db)):
    if db.get(CommunicationTask, task_id) is None:
        raise HTTPException(404, "Task not found")
    return [_comment_out(c) for c in collab.list_comments(db, task_id)]


@tasks_router.post("/{task_id}/comments", status_code=201)
def add_task_comment(
    task_id: int,
    body: dict = None,  # type: ignore[assignment]
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_staff),
):
    payload = body or {}
    text = (payload.get("comment") or "").strip()
    if not text:
        raise HTTPException(422, "comment is required")
    try:
        row = collab.add_comment(
            db,
            task_id=task_id,
            comment=text,
            created_by=assign.display_name(actor),
            created_by_id=actor.id,
        )
    except ValueError:
        raise HTTPException(404, "Task not found")
    return _comment_out(row)


@tasks_router.get("/{task_id}/activity")
def task_activity(task_id: int, db: Session = Depends(get_db)):
    if db.get(CommunicationTask, task_id) is None:
        raise HTTPException(404, "Task not found")
    return [_activity_out(a) for a in collab.list_activity(db, task_id)]


@tasks_router.post("/{task_id}/ai-summary", response_model=CommunicationTaskOut)
def generate_ai_summary(
    task_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_staff),
):
    row = db.get(CommunicationTask, task_id)
    if not row:
        raise HTTPException(404, "Task not found")
    if not ai_service.is_enabled():
        raise HTTPException(503, "AI is not enabled")
    transcript = collab.build_transcript(db, row)
    try:
        summary = ai_service.summarize_thread(transcript)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"AI summary failed: {e}")
    row.ai_summary = (summary or "").strip()
    row.ai_summary_at = datetime.utcnow()
    row.ai_summary_by = assign.display_name(actor)
    collab.log_activity(
        db,
        task_id=row.id,
        activity_type="AI_SUMMARY_GENERATED",
        new_value=row.ai_summary[:120],
        created_by=row.ai_summary_by,
        created_by_id=actor.id,
    )
    db.commit()
    db.refresh(row)
    return row


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────
def _validate_enum(field: str, value: str, allowed: tuple[str, ...]) -> None:
    if value not in allowed:
        raise HTTPException(422, f"{field} must be one of: {', '.join(allowed)}")

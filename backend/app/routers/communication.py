from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Body, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from ..core.deps import get_current_staff, require_admin
from ..database import get_db
from ..models.communication_task import (
    TASK_PRIORITIES,
    TASK_SIGNALS,
    TASK_SOURCES,
    TASK_STATUSES,
    CommunicationTask,
)
from ..models.communication_message import CommunicationMessage
from ..models.message_attachment import MessageAttachment
from ..models.user import User
from ..schemas.communication_task import (
    CommunicationTaskCreate,
    CommunicationTaskOut,
    CommunicationTaskUpdate,
)
from ..services import ai_service
from ..services import attachment_service
from ..services import bridge_service as bridge
from ..services import task_analytics_service as analytics
from ..services import task_assignment_service as assign
from ..services import task_board_service as board
from ..services import task_collaboration_service as collab
from ..services import task_events
from ..services import task_visibility as vis

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
    viewer: User = Depends(get_current_staff),
):
    stmt = vis.scope_stmt(select(CommunicationTask), viewer)
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
    rows = db.scalars(stmt.order_by(CommunicationTask.created_at.desc()).limit(limit)).all()
    return vis.filter_visible(rows, viewer)


@router.get("/tasks/{task_id}", response_model=CommunicationTaskOut)
def get_task(
    task_id: int,
    db: Session = Depends(get_db),
    viewer: User = Depends(get_current_staff),
):
    return _visible_task_or_404(db, task_id, viewer)


@router.get("/assignees")
def list_assignees(db: Session = Depends(get_db)):
    """Active staff + employee accounts selectable as task assignees/watchers."""
    return assign.list_assignees(db)


@router.get("/mention-targets")
def list_mention_targets(db: Session = Depends(get_db)):
    """@-mention candidates for the /hi assistant: assignable users + recent
    customers. NOT for assignee/watcher pickers (those use /assignees)."""
    return assign.list_mention_targets(db)


@router.post("/tasks", response_model=CommunicationTaskOut, status_code=201)
def create_task(
    payload: CommunicationTaskCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_staff),
    background_tasks: BackgroundTasks = None,  # type: ignore[assignment]
):
    """Create a task. Kept lean on purpose (client: "tasks too slow"): one
    insert + the CREATED activity row in a single commit. Notifications to the
    involved people are written AFTER the response via BackgroundTasks."""
    _validate_enum("priority", payload.priority, TASK_PRIORITIES)
    _validate_enum("status", payload.status, board.valid_status_keys(db))
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
    data["assigned_by_user_id"] = actor.id
    data["created_by_user_id"] = actor.id
    _apply_source_message(db, data)

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
    task_events.dispatch(
        background_tasks, db, row,
        kind="CREATED", actor_id=actor.id, actor_name=assign.display_name(actor),
    )
    return row


@router.patch("/tasks/{task_id}", response_model=CommunicationTaskOut)
def update_task(
    task_id: int,
    payload: CommunicationTaskUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_staff),
    background_tasks: BackgroundTasks = None,  # type: ignore[assignment]
):
    row = _visible_task_or_404(db, task_id, actor)

    data = payload.model_dump(exclude_unset=True)
    if "priority" in data:
        _validate_enum("priority", data["priority"], TASK_PRIORITIES)
    if "status" in data:
        _validate_enum("status", data["status"], board.valid_status_keys(db))
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
        if data["assigned_to_user_id"] != row.assigned_to_user_id:
            # Whoever hands the task to someone becomes its assigner.
            data["assigned_by"] = actor_name
            data["assigned_by_user_id"] = actor.id

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

    old_watchers = vis.watcher_ids(row)
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

    # Involved-people notifications, off the request path.
    if "assigned_to_user_id" in changes:
        task_events.dispatch(
            background_tasks, db, row,
            kind="ASSIGNED", actor_id=actor.id, actor_name=actor_name,
        )
    elif "status" in changes:
        task_events.dispatch(
            background_tasks, db, row,
            kind="STATUS", actor_id=actor.id, actor_name=actor_name,
            ctx={"status": row.status},
        )
    new_watchers = vis.watcher_ids(row) - old_watchers
    if new_watchers and "assigned_to_user_id" not in changes:
        task_events.dispatch(
            background_tasks, db, row,
            kind="WATCHER_ADDED", actor_id=actor.id, actor_name=actor_name,
            only_ids=sorted(new_watchers),
        )

    # If this task is mirroring a ZanFlow material line, tell ZanFlow. One hook
    # covers the staff board, the employee portal and the supplier portal,
    # because all three delegate their PATCH here. Best effort by construction —
    # `safe_notify` never raises, so a ZanFlow outage cannot fail this request.
    if "status" in changes or "progress_percent" in changes:
        bridge.safe_notify(
            db, row,
            event="STATUS_CHANGED" if "status" in changes else "PROGRESS_CHANGED",
            status=row.status,
            progress_percent=row.progress_percent,
            actor=actor_name,
            actor_user_id=actor.id,
        )
    return row


@router.delete("/tasks/{task_id}", status_code=204)
def delete_task(
    task_id: int,
    db: Session = Depends(get_db),
    viewer: User = Depends(get_current_staff),
):
    row = _visible_task_or_404(db, task_id, viewer)
    db.delete(row)
    db.commit()


# ──────────────────────────────────────────────────────────────────────────────
# Dashboard counters for KPI strip (legacy + unified)
# ──────────────────────────────────────────────────────────────────────────────
def _task_counts(db: Session, viewer: Optional[User] = None) -> dict[str, int]:
    """KPI strip counters in ONE aggregate query (was 12 round trips).

    Scoped exactly like the task list: admins count everything; anyone else
    counts only the open tasks they are involved in (so "done" is 0 for them —
    completed tasks are admin-only)."""
    T = CommunicationTask
    if viewer is not None and not vis.is_task_admin(viewer):
        # Watcher matching needs an exact Python pass, so count the scoped rows.
        rows = vis.filter_visible(db.scalars(vis.scope_stmt(select(T), viewer)).all(), viewer)
        return count_task_rows(rows)

    now = datetime.utcnow()
    start_of_day = datetime.combine(now.date(), datetime.min.time())
    end_of_day = datetime.combine(now.date(), datetime.max.time())
    not_done = T.status != "DONE"
    has_due = T.due_date.isnot(None)

    def n(cond):
        return func.sum(case((cond, 1), else_=0))

    row = db.execute(
        select(
            func.count(T.id),
            n(T.status == "TODO"),
            n(T.status == "WAITING_SUPPLIER"),
            n(T.status == "IN_PROGRESS"),
            n(T.status == "DONE"),
            n(not_done & has_due & (T.due_date < now)),
            n(not_done & has_due & (T.due_date >= start_of_day) & (T.due_date <= end_of_day)),
            n(T.signal == "BLACK"),
            n(T.task_source == "SUPPLIER"),
            n(T.task_source == "CUSTOMER"),
            n(T.task_source == "INTERNAL"),
            n(T.task_source == "ESCALATION"),
        )
    ).one()
    return {k: int(v or 0) for k, v in zip(_COUNT_KEYS, row)}


_COUNT_KEYS = (
    "total_tasks", "todo", "waiting", "in_progress", "done", "overdue", "due_today",
    "critical", "supplier_tasks", "customer_tasks", "internal_tasks", "escalation_tasks",
)


def count_task_rows(rows: list[CommunicationTask]) -> dict[str, int]:
    """Same counters as `_task_counts`, over already-loaded (scoped) rows."""
    now = datetime.utcnow()
    today = now.date()

    def c(pred) -> int:
        return sum(1 for t in rows if pred(t))

    return {
        "total_tasks": len(rows),
        "todo": c(lambda t: t.status == "TODO"),
        "waiting": c(lambda t: t.status == "WAITING_SUPPLIER"),
        "in_progress": c(lambda t: t.status == "IN_PROGRESS"),
        "done": c(lambda t: t.status == "DONE"),
        "overdue": c(lambda t: t.status != "DONE" and t.due_date is not None and t.due_date < now),
        "due_today": c(
            lambda t: t.status != "DONE" and t.due_date is not None and t.due_date.date() == today
        ),
        "critical": c(lambda t: t.signal == "BLACK"),
        "supplier_tasks": c(lambda t: t.task_source == "SUPPLIER"),
        "customer_tasks": c(lambda t: t.task_source == "CUSTOMER"),
        "internal_tasks": c(lambda t: t.task_source == "INTERNAL"),
        "escalation_tasks": c(lambda t: t.task_source == "ESCALATION"),
    }


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), viewer: User = Depends(get_current_staff)):
    return _task_counts(db, viewer)


@router.get("/analytics")
def task_analytics_summary(db: Session = Depends(get_db), viewer: User = Depends(get_current_staff)):
    return analytics.compute_analytics(db, viewer=viewer)


@router.get("/analytics/export")
def task_analytics_export(db: Session = Depends(get_db), viewer: User = Depends(get_current_staff)):
    data = analytics.export_workbook(db, viewer=viewer)
    headers = {"Content-Disposition": 'attachment; filename="task-analytics.xlsx"'}
    return StreamingResponse(
        iter([data]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )


# Unified task management endpoints under /api/tasks/...
@tasks_router.get("/dashboard")
def tasks_dashboard(db: Session = Depends(get_db), viewer: User = Depends(get_current_staff)):
    return _task_counts(db, viewer)


@tasks_router.get("/export/mine")
def export_my_tasks(db: Session = Depends(get_db), viewer: User = Depends(get_current_staff)):
    """"My tasks" as .xlsx — the tasks the caller is involved in (created,
    assigned to, assigned by, watching). Same visibility as the board: admins
    also get their completed tasks, everyone else open tasks only."""
    return my_tasks_xlsx_response(db, viewer)


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
    viewer: User = Depends(get_current_staff),
):
    stmt = vis.scope_stmt(select(CommunicationTask), viewer)
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
    rows = db.scalars(stmt.order_by(CommunicationTask.created_at.desc()).limit(limit)).all()
    return vis.filter_visible(rows, viewer)


# ──────────────────────────────────────────────────────────────────────────────
# Board columns (a column == a task status; admins customise the layout)
# ──────────────────────────────────────────────────────────────────────────────
@tasks_router.get("/board-columns")
def board_columns(db: Session = Depends(get_db)):
    return {"columns": board.get_columns(db), "colors": list(board.COLORS)}


@tasks_router.put("/board-columns")
def update_board_columns(
    body: dict = Body(...),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    columns = body.get("columns")
    if not isinstance(columns, list):
        raise HTTPException(422, "columns must be a list")
    try:
        cols = board.set_columns(db, columns)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return {"columns": cols, "colors": list(board.COLORS)}


# ──────────────────────────────────────────────────────────────────────────────
# Task attachments (files on the task itself, stored like chat attachments)
# ──────────────────────────────────────────────────────────────────────────────
def _uploader_kind(user: User) -> str:
    return "employee" if user.emp_code else "staff"


def list_task_attachments(db: Session, task_id: int) -> list[dict]:
    return [attachment_service.task_out(a) for a in attachment_service.for_task(db, task_id)]


async def add_task_attachment(db: Session, task: CommunicationTask, file: UploadFile, actor: User) -> dict:
    """Upload + bind in one step (a task has no "send" moment to bind on)."""
    if not attachment_service.storage_enabled():
        raise HTTPException(503, attachment_service.disabled_reason())
    data = await file.read()
    try:
        att = attachment_service.save_upload(
            db,
            data=data,
            filename=file.filename,
            content_type=file.content_type,
            uploaded_by_kind=_uploader_kind(actor),
            uploaded_by_id=actor.id,
            uploaded_by_label=assign.display_name(actor),
            supplier_id=task.supplier_id,
            commit=False,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    att.task_id = task.id
    task.attachment_count = (task.attachment_count or 0) + 1
    collab.log_activity(
        db,
        task_id=task.id,
        activity_type="ATTACHMENT_ADDED",
        new_value=att.filename,
        created_by=assign.display_name(actor),
        created_by_id=actor.id,
    )
    db.commit()
    db.refresh(att)
    return attachment_service.task_out(att)


def remove_task_attachment(db: Session, task: CommunicationTask, attachment_id: int, actor: User) -> None:
    from ..core import roles as roles_mod
    from ..core.roles import Role

    att = db.get(MessageAttachment, attachment_id)
    if att is None or att.task_id != task.id:
        raise HTTPException(404, "Attachment not found")
    own = att.uploaded_by_kind == _uploader_kind(actor) and att.uploaded_by_id == actor.id
    if not own and not roles_mod.role_at_least(actor.role, Role.ADMIN):
        raise HTTPException(403, "Only the uploader or an admin can remove this file")
    task.attachment_count = max(0, (task.attachment_count or 0) - 1)
    collab.log_activity(
        db,
        task_id=task.id,
        activity_type="ATTACHMENT_REMOVED",
        old_value=att.filename,
        created_by=assign.display_name(actor),
        created_by_id=actor.id,
    )
    attachment_service.delete(db, att)


def _task_or_404(db: Session, task_id: int) -> CommunicationTask:
    row = db.get(CommunicationTask, task_id)
    if row is None:
        raise HTTPException(404, "Task not found")
    return row


def _visible_task_or_404(db: Session, task_id: int, viewer: User) -> CommunicationTask:
    """The task, if `viewer` may open it (admin, or involved). 404 otherwise —
    same answer as "does not exist", so ids of other people's tasks don't leak."""
    row = db.get(CommunicationTask, task_id)
    if row is None or not vis.can_see(viewer, row):
        raise HTTPException(404, "Task not found")
    return row


@tasks_router.get("/{task_id}/attachments")
def task_attachments(
    task_id: int,
    db: Session = Depends(get_db),
    viewer: User = Depends(get_current_staff),
):
    _visible_task_or_404(db, task_id, viewer)
    return list_task_attachments(db, task_id)


@tasks_router.post("/{task_id}/attachments", status_code=201)
async def upload_task_attachment(
    task_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_staff),
):
    return await add_task_attachment(db, _visible_task_or_404(db, task_id, actor), file, actor)


@tasks_router.delete("/{task_id}/attachments/{attachment_id}", status_code=204)
def delete_task_attachment(
    task_id: int,
    attachment_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_staff),
):
    remove_task_attachment(db, _visible_task_or_404(db, task_id, actor), attachment_id, actor)


# ──────────────────────────────────────────────────────────────────────────────
# Source mail context (task assigned from a Communication Hub message)
# ──────────────────────────────────────────────────────────────────────────────
_EXCERPT_CHARS = 1500


def _apply_source_message(db: Session, data: dict) -> None:
    """Validate `source_message_id` and fill linkage the message already knows
    (supplier / PO / record) when the form left it blank. Unknown id → dropped,
    so a stale client can't break task creation."""
    mid = data.get("source_message_id")
    if mid is None:
        return
    cm = db.get(CommunicationMessage, mid)
    if cm is None:
        data["source_message_id"] = None
        return
    for key in ("supplier_id", "supplier_name", "supplier_po_no", "procurement_record_id"):
        if not data.get(key) and getattr(cm, key, None):
            data[key] = getattr(cm, key)


def source_message_context(db: Session, task: CommunicationTask) -> Optional[dict]:
    """Subject / sender / date / body excerpt + attachments of the mail the
    task was assigned from. Attachments are the message's own rows (referenced,
    not copied), downloadable through the normal attachment endpoints.

    Falls back to the legacy `linked_mail_id` (mail_history, outgoing system
    mails — no attachments) when there is no hub message."""
    if task.source_message_id:
        cm = db.get(CommunicationMessage, task.source_message_id)
        if cm is not None:
            body = (cm.body or "").strip()
            incoming = (cm.direction or "").upper() == "INCOMING"
            return {
                "kind": "message",
                "message_id": cm.id,
                "direction": cm.direction,
                "subject": cm.subject,
                "sender": cm.sender_email if incoming else (cm.sender_email or "H-Connect"),
                "to": cm.receiver_email or ", ".join(cm.to_emails or []) or None,
                "supplier_name": cm.supplier_name,
                "supplier_po_no": cm.supplier_po_no,
                "date": cm.received_at or cm.sent_at or cm.created_at,
                "body_excerpt": body[:_EXCERPT_CHARS],
                "truncated": len(body) > _EXCERPT_CHARS,
                "attachments": attachment_service.for_messages(db, [cm.id]).get(cm.id, []),
            }
    if task.linked_mail_id:
        from ..models.mail_history import MailHistory

        mh = db.get(MailHistory, task.linked_mail_id)
        if mh is not None:
            body = (mh.body or "").strip()
            return {
                "kind": "mail_history",
                "message_id": None,
                "direction": "OUTGOING",
                "subject": mh.subject,
                "sender": "H-Connect",
                "to": ", ".join(getattr(mh, "to_emails", None) or []) or None,
                "supplier_name": mh.supplier_name,
                "supplier_po_no": mh.supplier_po_no,
                "date": mh.sent_at or mh.created_at,
                "body_excerpt": body[:_EXCERPT_CHARS],
                "truncated": len(body) > _EXCERPT_CHARS,
                "attachments": [],
            }
    return None


@tasks_router.get("/{task_id}/source-message")
def task_source_message(
    task_id: int,
    db: Session = Depends(get_db),
    viewer: User = Depends(get_current_staff),
):
    """The source mail block for the task detail view ({"source": null} if none)."""
    task = _visible_task_or_404(db, task_id, viewer)
    return {"source": source_message_context(db, task)}


# ──────────────────────────────────────────────────────────────────────────────
# "My tasks" export (.xlsx, same openpyxl pattern as the workload exports)
# ──────────────────────────────────────────────────────────────────────────────
MY_TASK_HEADERS = [
    "Task ID", "Title", "Status", "Priority", "Signal", "Source", "Supplier", "PO No",
    "Material", "Assigned To", "Assigned By", "My Role", "Due Date", "Overdue",
    "Progress %", "Created", "Closed",
]


def my_tasks_rows(db: Session, user: User) -> list[CommunicationTask]:
    """Tasks `user` is involved in. Admins also get their completed tasks;
    everyone else open tasks only (completed tasks are admin-only)."""
    include_done = vis.is_task_admin(user)
    T = CommunicationTask
    # Involvement-only for everyone (admins too: this is *my* tasks, not all).
    stmt = select(T).where(vis.involved_clause(user.id))
    if not include_done:
        stmt = stmt.where(T.status != "DONE")
    rows = [t for t in db.scalars(stmt.order_by(T.due_date.is_(None), T.due_date, T.id)).all()
            if vis.is_involved(user, t)]
    return rows


def _my_role(user: User, t: CommunicationTask) -> str:
    roles = []
    if t.assigned_to_user_id == user.id:
        roles.append("Assignee")
    if t.created_by_user_id == user.id or t.assigned_by_user_id == user.id:
        roles.append("Assigner")
    if user.id in vis.watcher_ids(t):
        roles.append("Watcher")
    return ", ".join(roles)


def my_tasks_workbook(db: Session, user: User) -> bytes:
    import io

    from openpyxl import Workbook
    from openpyxl.styles import Font

    now = datetime.utcnow()
    wb = Workbook()
    ws = wb.active
    ws.title = "My tasks"
    ws.append(MY_TASK_HEADERS)
    for c in ws[1]:
        c.font = Font(bold=True)
    for t in my_tasks_rows(db, user):
        overdue = t.status != "DONE" and t.due_date is not None and t.due_date < now
        ws.append([
            t.id, t.title, t.status, t.priority, t.signal, t.task_source,
            t.supplier_name, t.supplier_po_no, t.material_name,
            t.assigned_to, t.assigned_by, _my_role(user, t),
            t.due_date.strftime("%Y-%m-%d %H:%M") if t.due_date else None,
            "Yes" if overdue else "",
            t.progress_percent,
            t.created_at.strftime("%Y-%m-%d %H:%M") if t.created_at else None,
            t.closed_at.strftime("%Y-%m-%d %H:%M") if t.closed_at else None,
        ])
    ws.freeze_panes = "A2"
    for idx, h in enumerate(MY_TASK_HEADERS, start=1):
        ws.column_dimensions[ws.cell(row=1, column=idx).column_letter].width = max(len(h) + 2, 12 if idx != 2 else 40)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def my_tasks_xlsx_response(db: Session, user: User) -> StreamingResponse:
    data = my_tasks_workbook(db, user)
    filename = f"my-tasks-{datetime.utcnow().date().isoformat()}.xlsx"
    return StreamingResponse(
        iter([data]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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
def task_comments(
    task_id: int,
    db: Session = Depends(get_db),
    viewer: User = Depends(get_current_staff),
):
    _visible_task_or_404(db, task_id, viewer)
    return [_comment_out(c) for c in collab.list_comments(db, task_id)]


@tasks_router.post("/{task_id}/comments", status_code=201)
def add_task_comment(
    task_id: int,
    body: dict = None,  # type: ignore[assignment]
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_staff),
    background_tasks: BackgroundTasks = None,  # type: ignore[assignment]
):
    _visible_task_or_404(db, task_id, actor)
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

    # The other chokepoint: the employee portal posts its comments through this
    # same function, so a bridged task's discussion reaches the material line
    # whichever surface it was typed into.
    task = db.get(CommunicationTask, task_id)
    bridge.safe_notify(
        db, task,
        event="COMMENT_ADDED",
        comment=text,
        actor=assign.display_name(actor),
        actor_user_id=actor.id,
    )
    if task is not None:
        task_events.dispatch(
            background_tasks, db, task,
            kind="COMMENT", actor_id=actor.id, actor_name=assign.display_name(actor),
            ctx={"comment": text},
        )
    return _comment_out(row)


@tasks_router.get("/{task_id}/activity")
def task_activity(
    task_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),  # change log is admin-only
):
    if db.get(CommunicationTask, task_id) is None:
        raise HTTPException(404, "Task not found")
    return [_activity_out(a) for a in collab.list_activity(db, task_id)]


@tasks_router.post("/{task_id}/ai-summary", response_model=CommunicationTaskOut)
def generate_ai_summary(
    task_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_staff),
):
    row = _visible_task_or_404(db, task_id, actor)
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
def _validate_enum(field: str, value: str | None, allowed: tuple[str, ...]) -> None:
    if value not in allowed:
        raise HTTPException(422, f"{field} must be one of: {', '.join(allowed)}")

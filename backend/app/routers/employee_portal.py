"""Employee portal API — scoped to the logged-in employee account.

Mounted in main.py with `Depends(get_current_employee)`, so every handler can
trust `user.emp_code`. Employees only ever see POs whose `owner_emp_code` matches
their employee code. For Tasks they get the full staff Task Manager (create /
assign / escalate / comment) but every endpoint is scoped to tasks they own or
are assigned to, and delegates to the shared logic in `routers.communication`.
"""
from __future__ import annotations

import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..core.deps import get_current_employee
from ..database import get_db
from ..models.communication_message import CommunicationMessage
from ..models.communication_task import CommunicationTask
from ..models.procurement import ProcurementRecord
from ..models.supplier import SupplierMaster
from ..models.user import User
from ..schemas.communication_task import (
    CommunicationTaskCreate,
    CommunicationTaskOut,
    CommunicationTaskUpdate,
)
from ..schemas.employee_portal import (
    EmployeePo,
    EmployeePoListResponse,
    EmployeePoMaterial,
    EmployeeSummary,
)
from ..schemas.portal import PortalMessage, PortalMessageCreate
from ..services import communication_message_service as msg_service
from ..services import notification_service as notif
from ..services import task_assignment_service as assign
from . import communication as comm  # reuse the staff task logic (one source of truth)

router = APIRouter(prefix="/api/eportal", tags=["employee-portal"])

_SIGNAL_RANK = {"GREEN": 1, "YELLOW": 2, "RED": 3, "BLACK": 4}
# Outgoing statuses visible in a thread (internal DRAFTs awaiting approval hidden).
_VISIBLE_OUTGOING = {"SENT", "SENT_MANUALLY", "READY", "COPIED", "MAILTO_OPENED"}
_TAG_RE = re.compile(r"<[^>]+>")


def _emp_records(db: Session, emp_code: str | None) -> list[ProcurementRecord]:
    if not emp_code:
        return []
    return list(
        db.scalars(
            select(ProcurementRecord).where(ProcurementRecord.owner_emp_code == emp_code)
        ).all()
    )


def _worst_signal(signals: list[str | None]) -> str | None:
    worst, worst_rank = None, 0
    for sig in signals:
        s = (sig or "").upper()
        r = _SIGNAL_RANK.get(s, 0)
        if r > worst_rank:
            worst_rank, worst = r, s
    return worst


def _as_dt(d) -> datetime | None:
    if d is None:
        return None
    return d if isinstance(d, datetime) else datetime.combine(d, datetime.min.time())


@router.get("/me")
def me(user: User = Depends(get_current_employee)) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "full_name": user.full_name,
        "emp_code": user.emp_code,
        "must_change_password": user.must_change_password,
    }


@router.get("/summary", response_model=EmployeeSummary)
def summary(
    user: User = Depends(get_current_employee), db: Session = Depends(get_db)
) -> EmployeeSummary:
    records = _emp_records(db, user.emp_code)
    now = datetime.utcnow()
    counts = {"GREEN": 0, "YELLOW": 0, "RED": 0, "BLACK": 0}
    po_signals: dict[str, list[str | None]] = {}
    po_escalated: dict[str, bool] = {}
    po_overdue: dict[str, bool] = {}
    for r in records:
        sig = (r.signal or "").upper()
        if sig in counts:
            counts[sig] += 1
        po = r.supplier_po_no or ""
        po_signals.setdefault(po, []).append(r.signal)
        if (r.escalation_level or "NONE").upper() != "NONE":
            po_escalated[po] = True
        sd = _as_dt(r.shipment_date)
        if sd is not None and sd < now:
            po_overdue[po] = True
    return EmployeeSummary(
        emp_code=user.emp_code,
        full_name=user.full_name,
        total_pos=len(po_signals),
        total_materials=len(records),
        green=counts["GREEN"],
        yellow=counts["YELLOW"],
        red=counts["RED"],
        black=counts["BLACK"],
        escalated_pos=sum(1 for v in po_escalated.values() if v),
        overdue_pos=sum(1 for v in po_overdue.values() if v),
    )


@router.get("/pos", response_model=EmployeePoListResponse)
def list_pos(
    user: User = Depends(get_current_employee), db: Session = Depends(get_db)
) -> EmployeePoListResponse:
    records = _emp_records(db, user.emp_code)
    groups: dict[str, dict] = {}
    for r in records:
        po = r.supplier_po_no
        if not po:
            continue
        g = groups.setdefault(po, {
            "crm_no": r.crm_no,
            "supplier_name": r.supplier_name,
            "signals": [],
            "po_status": r.po_status,
            "earliest": None,
            "count": 0,
            "escalated": False,
        })
        g["count"] += 1
        g["signals"].append(r.signal)
        if (r.escalation_level or "NONE").upper() != "NONE":
            g["escalated"] = True
        sd = _as_dt(r.shipment_date)
        if sd and (g["earliest"] is None or sd < g["earliest"]):
            g["earliest"] = sd

    # Unread supplier replies (INCOMING, not yet read) per PO.
    unread_counts: dict[str, int] = {}
    po_nos = [po for po in groups.keys() if po]
    if po_nos:
        for po_no, cnt in db.execute(
            select(CommunicationMessage.supplier_po_no, func.count(CommunicationMessage.id))
            .where(
                CommunicationMessage.direction == "INCOMING",
                CommunicationMessage.read_at.is_(None),
                CommunicationMessage.supplier_po_no.in_(po_nos),
            )
            .group_by(CommunicationMessage.supplier_po_no)
        ).all():
            if po_no:
                unread_counts[po_no] = int(cnt or 0)

    items = [
        EmployeePo(
            supplier_po_no=po,
            crm_no=g["crm_no"],
            supplier_name=g["supplier_name"],
            material_count=g["count"],
            overall_signal=_worst_signal(g["signals"]),
            po_status=g["po_status"],
            earliest_shipment_date=g["earliest"],
            escalated=g["escalated"],
            unread_inbound=unread_counts.get(po, 0),
        )
        for po, g in groups.items()
    ]
    items.sort(
        key=lambda p: (
            0 if p.escalated else 1,
            -_SIGNAL_RANK.get((p.overall_signal or "").upper(), 0),
            p.supplier_po_no,
        )
    )
    return EmployeePoListResponse(count=len(items), items=items)


@router.get("/pos/{supplier_po_no}/materials", response_model=list[EmployeePoMaterial])
def po_materials(
    supplier_po_no: str,
    user: User = Depends(get_current_employee),
    db: Session = Depends(get_db),
) -> list[EmployeePoMaterial]:
    rows = db.scalars(
        select(ProcurementRecord).where(
            ProcurementRecord.owner_emp_code == user.emp_code,
            ProcurementRecord.supplier_po_no == supplier_po_no,
        )
    ).all()
    return [
        EmployeePoMaterial(
            procurement_record_id=r.id,
            crm_no=r.crm_no,
            material_name=r.material_name,
            uom=r.uom,
            qty=float(r.qty) if r.qty is not None else None,
            supplier_name=r.supplier_name,
            shipment_date=_as_dt(r.shipment_date),
            signal=r.signal,
            po_status=r.po_status,
            rate=float(r.rate) if r.rate is not None else None,
            lead_time=r.lead_time,
            commitment_date=_as_dt(r.commitment_date),
        )
        for r in rows
    ]


# ── PO communication thread (shared with staff hub + supplier portal) ──────────
def _owned_po(db: Session, user: User, supplier_po_no: str) -> ProcurementRecord | None:
    return db.scalar(
        select(ProcurementRecord).where(
            ProcurementRecord.owner_emp_code == user.emp_code,
            ProcurementRecord.supplier_po_no == supplier_po_no,
        )
    )


def _msg_text(cm: CommunicationMessage) -> str:
    if cm.body and cm.body.strip():
        return cm.body.strip()
    if cm.body_html:
        return re.sub(r"\s+", " ", _TAG_RE.sub(" ", cm.body_html)).strip()
    return ""


def _msg_out(cm: CommunicationMessage, me: str | None) -> PortalMessage:
    mine = cm.direction == "OUTGOING"  # internal-authored (employee/staff/system)
    author = (me or "You") if mine else (cm.supplier_name or "Supplier")
    return PortalMessage(
        id=cm.id,
        direction=cm.direction,
        mine=mine,
        author=author,
        subject=cm.subject,
        body=_msg_text(cm),
        mail_type=cm.mail_type,
        status=cm.status,
        at=cm.sent_at or cm.received_at or cm.created_at,
    )


@router.get("/pos/{supplier_po_no}/messages", response_model=list[PortalMessage])
def list_messages(
    supplier_po_no: str,
    user: User = Depends(get_current_employee),
    db: Session = Depends(get_db),
) -> list[PortalMessage]:
    if not _owned_po(db, user, supplier_po_no):
        raise HTTPException(404, "PO not found for your account")
    rows = db.scalars(
        select(CommunicationMessage)
        .where(CommunicationMessage.supplier_po_no == supplier_po_no)
        .order_by(CommunicationMessage.created_at.asc())
    ).all()
    visible = [m for m in rows if m.direction == "INCOMING" or m.status in _VISIBLE_OUTGOING]
    return [_msg_out(m, user.full_name) for m in visible]


@router.post("/pos/{supplier_po_no}/messages", response_model=PortalMessage, status_code=201)
def post_message(
    supplier_po_no: str,
    payload: PortalMessageCreate,
    user: User = Depends(get_current_employee),
    db: Session = Depends(get_db),
) -> PortalMessage:
    rec = _owned_po(db, user, supplier_po_no)
    if rec is None:
        raise HTTPException(404, "PO not found for your account")
    supplier = (
        db.scalar(
            select(SupplierMaster).where(
                func.upper(SupplierMaster.supplier_name) == (rec.supplier_name or "").upper()
            )
        )
        if rec.supplier_name
        else None
    )
    subject = (payload.subject or "").strip() or f"Message · PO {supplier_po_no}"
    # OUTGOING + SENT_MANUALLY → appears in the staff Communication Hub and the
    # supplier's own portal thread; supplier replies come back as INCOMING.
    cm = msg_service.create_message(
        db,
        direction="OUTGOING",
        status="SENT_MANUALLY",
        supplier_id=supplier.id if supplier else None,
        supplier_name=rec.supplier_name,
        procurement_record_id=rec.id,
        supplier_po_no=supplier_po_no,
        subject=subject,
        body=payload.body.strip(),
        sender_email=user.username or user.email,
        mail_type="EMPLOYEE_MESSAGE",
        sent_at=datetime.utcnow(),
    )
    notif.safe(
        notif.notify_po_owners, db,
        supplier_po_no=supplier_po_no,
        exclude_user_id=user.id,  # don't notify the employee who just messaged
        type="EMPLOYEE_MESSAGE",
        title=f"{user.full_name or user.username} messaged on PO {supplier_po_no}",
        body=payload.body.strip()[:140],
        link="/mail-history",
        supplier_id=supplier.id if supplier else None,
        procurement_record_id=rec.id,
    )
    return _msg_out(cm, user.full_name)


@router.post("/pos/{supplier_po_no}/messages/mark-read")
def mark_messages_read(
    supplier_po_no: str,
    user: User = Depends(get_current_employee),
    db: Session = Depends(get_db),
) -> dict:
    """Clear the employee's unread badge for a PO (marks supplier replies read)."""
    if not _owned_po(db, user, supplier_po_no):
        raise HTTPException(404, "PO not found for your account")
    now = datetime.utcnow()
    rows = db.scalars(
        select(CommunicationMessage).where(
            CommunicationMessage.supplier_po_no == supplier_po_no,
            CommunicationMessage.direction == "INCOMING",
            CommunicationMessage.read_at.is_(None),
        )
    ).all()
    for cm in rows:
        cm.read_at = now
    if rows:
        db.commit()
    return {"marked": len(rows)}


# ── Tasks (full Task Manager, scoped to the employee's POs) ───────────────────
def _owned_po_numbers(db: Session, emp_code: str | None) -> list[str]:
    if not emp_code:
        return []
    return [
        po
        for po in db.scalars(
            select(ProcurementRecord.supplier_po_no)
            .where(
                ProcurementRecord.owner_emp_code == emp_code,
                ProcurementRecord.supplier_po_no.isnot(None),
            )
            .distinct()
        ).all()
        if po
    ]


def _task_in_scope(user: User, owned: list[str], task: CommunicationTask) -> bool:
    """A task belongs to an employee if it's assigned to them or on a PO they own."""
    if task.assigned_to_user_id == user.id:
        return True
    return bool(task.supplier_po_no and task.supplier_po_no in owned)


def _scoped_task_or_404(db: Session, user: User, task_id: int) -> CommunicationTask:
    row = db.get(CommunicationTask, task_id)
    owned = _owned_po_numbers(db, user.emp_code)
    if row is None or not _task_in_scope(user, owned, row):
        raise HTTPException(404, "Task not found for your account")
    return row


def _scope_counts(rows: list[CommunicationTask]) -> dict:
    now = datetime.utcnow()
    today = now.date()

    def c(pred) -> int:
        return sum(1 for t in rows if pred(t))

    return {
        "total_tasks": len(rows),
        "todo": c(lambda t: t.status == "TODO"),
        "in_progress": c(lambda t: t.status == "IN_PROGRESS"),
        "waiting": c(lambda t: t.status == "WAITING_SUPPLIER"),
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


@router.get("/tasks", response_model=list[CommunicationTaskOut])
def my_tasks(
    user: User = Depends(get_current_employee),
    db: Session = Depends(get_db),
    status: str | None = None,
    task_source: str | None = None,
    supplier_po_no: str | None = None,
    overdue: bool = False,
) -> list[CommunicationTask]:
    """The employee's tasks: assigned to them, or on a PO they own."""
    owned = _owned_po_numbers(db, user.emp_code)
    conds = [CommunicationTask.assigned_to_user_id == user.id]
    if owned:
        conds.append(CommunicationTask.supplier_po_no.in_(owned))
    stmt = select(CommunicationTask).where(or_(*conds))
    if status:
        stmt = stmt.where(CommunicationTask.status == status)
    if task_source:
        stmt = stmt.where(CommunicationTask.task_source == task_source)
    if supplier_po_no:
        stmt = stmt.where(CommunicationTask.supplier_po_no == supplier_po_no)
    if overdue:
        now = datetime.utcnow()
        stmt = stmt.where(
            CommunicationTask.status != "DONE",
            CommunicationTask.due_date.isnot(None),
            CommunicationTask.due_date < now,
        )
    rows = db.scalars(stmt).all()
    return sorted(
        rows,
        key=lambda t: (1 if (t.status or "").upper() == "DONE" else 0, t.due_date or datetime.max),
    )


@router.get("/tasks/dashboard")
def my_tasks_dashboard(
    user: User = Depends(get_current_employee), db: Session = Depends(get_db)
) -> dict:
    return _scope_counts(list(my_tasks(user=user, db=db)))


@router.get("/assignees")
def list_assignees(
    user: User = Depends(get_current_employee), db: Session = Depends(get_db)
) -> list[dict]:
    """Assignable staff/employee accounts for the picker (same set as staff)."""
    return assign.list_assignees(db)


@router.post("/tasks", response_model=CommunicationTaskOut, status_code=201)
def create_task(
    payload: CommunicationTaskCreate,
    user: User = Depends(get_current_employee),
    db: Session = Depends(get_db),
) -> CommunicationTask:
    """Create a task on one of the employee's own POs (or a personal task)."""
    owned = _owned_po_numbers(db, user.emp_code)
    if payload.supplier_po_no:
        if payload.supplier_po_no not in owned:
            raise HTTPException(403, "You can only create tasks on your own POs")
    elif payload.assigned_to_user_id is None:
        # Personal task with no PO → pin to the employee so it stays in scope.
        payload.assigned_to_user_id = user.id
    return comm.create_task(payload=payload, db=db, actor=user)


@router.patch("/tasks/{task_id}", response_model=CommunicationTaskOut)
def update_my_task(
    task_id: int,
    payload: CommunicationTaskUpdate,
    user: User = Depends(get_current_employee),
    db: Session = Depends(get_db),
) -> CommunicationTask:
    """Full update of a task in the employee's scope (delegates to staff logic)."""
    _scoped_task_or_404(db, user, task_id)
    row = comm.update_task(task_id=task_id, payload=payload, db=db, actor=user)
    if row.supplier_po_no:
        notif.safe(
            notif.notify_po_owners, db,
            supplier_po_no=row.supplier_po_no,
            exclude_user_id=user.id,
            type="TASK_UPDATED",
            title=f"Task updated by {user.full_name or user.username}",
            body=f"{row.title} → {row.status}",
            link="/tasks",
            supplier_id=row.supplier_id,
        )
    return row


@router.delete("/tasks/{task_id}", status_code=204)
def delete_my_task(
    task_id: int,
    user: User = Depends(get_current_employee),
    db: Session = Depends(get_db),
):
    _scoped_task_or_404(db, user, task_id)
    comm.delete_task(task_id=task_id, db=db)


@router.get("/tasks/{task_id}/comments")
def task_comments(
    task_id: int,
    user: User = Depends(get_current_employee),
    db: Session = Depends(get_db),
) -> list[dict]:
    _scoped_task_or_404(db, user, task_id)
    return comm.task_comments(task_id=task_id, db=db)


@router.post("/tasks/{task_id}/comments", status_code=201)
def add_task_comment(
    task_id: int,
    body: dict = None,  # type: ignore[assignment]
    user: User = Depends(get_current_employee),
    db: Session = Depends(get_db),
) -> dict:
    _scoped_task_or_404(db, user, task_id)
    return comm.add_task_comment(task_id=task_id, body=body, db=db, actor=user)

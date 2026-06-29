"""Employee portal API — scoped to the logged-in employee account.

Mounted in main.py with `Depends(get_current_employee)`, so every handler can
trust `user.emp_code`. Employees only ever see POs whose `owner_emp_code` matches
their employee code. Read-only in v1.
"""
from __future__ import annotations

import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..core.deps import get_current_employee
from ..database import get_db
from ..models.communication_message import CommunicationMessage
from ..models.communication_task import TASK_STATUSES, CommunicationTask
from ..models.procurement import ProcurementRecord
from ..models.supplier import SupplierMaster
from ..models.user import User
from ..schemas.employee_portal import (
    EmployeePo,
    EmployeePoListResponse,
    EmployeePoMaterial,
    EmployeeSummary,
)
from ..schemas.portal import PortalMessage, PortalMessageCreate, PortalTask
from ..services import communication_message_service as msg_service
from ..services import notification_service as notif
from ..services import task_collaboration_service as collab

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


# ── Tasks (the employee's own Task Manager) ───────────────────────────────────
class EmployeeTaskUpdate(BaseModel):
    """Employees may only move a task and report progress — nothing else."""
    status: str | None = None
    progress_percent: int | None = None


def _to_portal_task(t: CommunicationTask) -> PortalTask:
    return PortalTask(
        id=t.id,
        title=t.title,
        description=t.description,
        material_name=t.material_name,
        status=t.status,
        priority=t.priority,
        signal=t.signal,
        progress_percent=t.progress_percent,
        due_date=t.due_date,
        created_at=t.created_at,
        closed_at=t.closed_at,
    )


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


@router.get("/tasks", response_model=list[PortalTask])
def my_tasks(
    user: User = Depends(get_current_employee), db: Session = Depends(get_db)
) -> list[PortalTask]:
    """The employee's tasks: assigned to them, or on a PO they own."""
    conds = [CommunicationTask.assigned_to_user_id == user.id]
    owned = _owned_po_numbers(db, user.emp_code)
    if owned:
        conds.append(CommunicationTask.supplier_po_no.in_(owned))
    rows = db.scalars(select(CommunicationTask).where(or_(*conds))).all()
    # Open tasks first, then by due date (undated last).
    rows = sorted(
        rows,
        key=lambda t: (1 if (t.status or "").upper() == "DONE" else 0, t.due_date or datetime.max),
    )
    return [_to_portal_task(t) for t in rows]


@router.patch("/tasks/{task_id}", response_model=PortalTask)
def update_my_task(
    task_id: int,
    payload: EmployeeTaskUpdate,
    user: User = Depends(get_current_employee),
    db: Session = Depends(get_db),
) -> PortalTask:
    """Employees can update status / progress on tasks assigned to them only."""
    row = db.get(CommunicationTask, task_id)
    if row is None or row.assigned_to_user_id != user.id:
        raise HTTPException(404, "Task not found for your account")

    data = payload.model_dump(exclude_unset=True)
    if data.get("status") is not None and data["status"] not in TASK_STATUSES:
        raise HTTPException(422, f"status must be one of {TASK_STATUSES}")
    if data.get("progress_percent") is not None:
        pp = int(data["progress_percent"])
        if not 0 <= pp <= 100:
            raise HTTPException(422, "progress_percent must be between 0 and 100")
        data["progress_percent"] = pp

    # Progress convenience rules (mirror the staff handler).
    if data.get("status") == "DONE":
        data["progress_percent"] = 100
    elif data.get("status") == "BACKLOG":
        data["progress_percent"] = 0

    tracked = ("status", "progress_percent")
    changes = {
        k: (getattr(row, k), data[k])
        for k in tracked
        if k in data and data[k] is not None and getattr(row, k) != data[k]
    }
    for k, v in data.items():
        if v is not None:
            setattr(row, k, v)

    if data.get("status") == "DONE" and not row.closed_at:
        row.closed_at = datetime.utcnow()
    elif data.get("status") and data["status"] != "DONE":
        row.closed_at = None

    if changes:
        collab.record_task_changes(
            db, row, changes,
            created_by=user.full_name or user.username,
            created_by_id=user.id,
        )
    db.commit()
    db.refresh(row)

    if changes and row.supplier_po_no:
        notif.safe(
            notif.notify_po_owners, db,
            supplier_po_no=row.supplier_po_no,
            exclude_user_id=user.id,  # the acting employee is often an owner
            type="TASK_UPDATED",
            title=f"Task updated by {user.full_name or user.username}",
            body=f"{row.title} → {row.status}",
            link="/tasks",
            supplier_id=row.supplier_id,
        )
    return _to_portal_task(row)

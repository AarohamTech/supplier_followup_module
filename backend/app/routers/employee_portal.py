"""Employee portal API — scoped to the logged-in employee account.

Mounted in main.py with `Depends(get_current_employee)`, so every handler can
trust `user.emp_code`. Employees only ever see POs whose `owner_emp_code` matches
their employee code. For Tasks they get the full staff Task Manager (create /
assign / escalate / comment) but every endpoint is scoped to tasks they own or
are assigned to, and delegates to the shared logic in `routers.communication`.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..core.deps import get_current_employee
from ..database import get_db
from ..models.communication_message import CommunicationMessage
from ..models.communication_task import CommunicationTask
from ..models.message_attachment import MessageAttachment
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
from ..schemas.procurement import DashboardKpis, ProcurementListOut, ProcurementBreakdown
from ..services import attachment_service
from ..services import communication_message_service as msg_service
from ..services import procurement_breakdown_service as breakdown_service
from ..services import notification_service as notif
from ..services import po_cancel_service
from ..services import po_followup_mail_service
from ..services import po_view_service
from ..services import task_assignment_service as assign
from . import ai_insights  # reuse the admin Black-Follow-ups aggregation + command schema
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
    # Grouped by (supplier, PO) — shared with the admin Purchase Orders view — but
    # scoped to POs this employee owns.
    groups = po_view_service.list_groups(db, owner_emp_code=user.emp_code)
    return EmployeePoListResponse(count=len(groups), items=[EmployeePo(**g) for g in groups])


@router.get("/pos/{supplier_po_no}/materials", response_model=list[EmployeePoMaterial])
def po_materials(
    supplier_po_no: str,
    supplier_name: Optional[str] = None,
    user: User = Depends(get_current_employee),
    db: Session = Depends(get_db),
) -> list[EmployeePoMaterial]:
    stmt = select(ProcurementRecord).where(
        ProcurementRecord.owner_emp_code == user.emp_code,
        ProcurementRecord.supplier_po_no == supplier_po_no,
    )
    # PO numbers are recycled across suppliers — scope to the supplier so a
    # shared PO number does not mix another vendor's materials into this PO.
    if supplier_name:
        stmt = stmt.where(
            func.upper(ProcurementRecord.supplier_name) == supplier_name.strip().upper()
        )
    rows = db.scalars(stmt).all()
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
            po_qty=float(r.po_qty) if r.po_qty is not None else None,
            grn_qty=float(r.grn_qty) if r.grn_qty is not None else None,
            pending_qty=float(r.pending_qty) if r.pending_qty is not None else None,
            receipt_status=r.receipt_status,
        )
        for r in rows
    ]


@router.get("/pos/{supplier_po_no}/detail")
def po_detail(
    supplier_po_no: str,
    supplier_name: Optional[str] = None,
    user: User = Depends(get_current_employee),
    db: Session = Depends(get_db),
) -> dict:
    """Materials + full communication history for one of the employee's own POs."""
    detail = po_view_service.po_detail(
        db, supplier_po_no=supplier_po_no, supplier_name=supplier_name, owner_emp_code=user.emp_code
    )
    if detail is None:
        raise HTTPException(404, "PO not found among your assigned POs")
    return detail


class PoCancelIn(BaseModel):
    remark: Optional[str] = None


@router.post("/pos/{supplier_po_no}/request-cancel")
def request_po_cancel(
    supplier_po_no: str,
    payload: Optional[PoCancelIn] = None,
    supplier_name: Optional[str] = None,
    user: User = Depends(get_current_employee),
    db: Session = Depends(get_db),
) -> dict:
    """Raise a cancellation for one of the employee's own POs. Sets the PO to
    'Pending cancellation' and calls the external cancel API (a no-op stub until the
    CRM cancel format is wired). Scoped to the caller's owned POs."""
    result = po_cancel_service.request_cancellation(
        db,
        supplier_po_no=supplier_po_no,
        supplier_name=supplier_name,
        owner_emp_code=user.emp_code,
        requested_by=user.emp_code or user.email,
        remark=payload.remark if payload else None,
    )
    if result is None:
        raise HTTPException(404, "PO not found among your assigned POs")
    return result


@router.get("/po-pdf")
def po_pdf(
    trn_no: str,
    amend_no: int = 0,
    user: User = Depends(get_current_employee),
    db: Session = Depends(get_db),
):
    """Download the PO PDF from the Hariom CRM for one of the employee's own POs
    (proxied — the CRM only accepts calls from this server). Scope boundary: the
    transaction number must belong to a line the employee owns."""
    from fastapi.responses import Response

    from ..services import crm_ingest_service
    from ..services.crm_config import get_current_crm_config

    owned = db.scalar(
        select(func.count()).select_from(ProcurementRecord).where(
            ProcurementRecord.po_trn_no == trn_no,
            ProcurementRecord.owner_emp_code == user.emp_code,
        )
    )
    if not owned:
        raise HTTPException(404, "PO not found among your assigned POs")
    cfg = get_current_crm_config(db)
    if cfg is None:
        raise HTTPException(503, "CRM connection is not configured for this company")
    try:
        content, media_type = crm_ingest_service.fetch_po_pdf(cfg, trn_no, amend_no)
    except RuntimeError as exc:
        raise HTTPException(502, str(exc))
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="PO-{trn_no}.pdf"'},
    )


# ── File attachments (chat uploads, scoped to this employee) ──────────────────
@router.post("/attachments/upload", status_code=201)
async def upload_attachment(
    file: UploadFile = File(...),
    user: User = Depends(get_current_employee),
    db: Session = Depends(get_db),
) -> dict:
    if not attachment_service.storage_enabled():
        raise HTTPException(503, attachment_service.disabled_reason())
    data = await file.read()
    try:
        att = attachment_service.save_upload(
            db,
            data=data,
            filename=file.filename,
            content_type=file.content_type,
            uploaded_by_kind="employee",
            uploaded_by_id=user.id,
            uploaded_by_label=user.full_name or user.username or user.email,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return attachment_service.out(att)


@router.get("/attachments/{attachment_id}/download")
def download_attachment(
    attachment_id: int,
    user: User = Depends(get_current_employee),
    db: Session = Depends(get_db),
):
    """An employee may download a file they uploaded themselves, or any file on
    a message in a PO thread they own."""
    from .attachments import attachment_response

    att = db.get(MessageAttachment, attachment_id)
    if att is None:
        raise HTTPException(404, "Attachment not found")
    allowed = att.uploaded_by_kind == "employee" and att.uploaded_by_id == user.id
    if not allowed and att.message_id:
        cm = db.get(CommunicationMessage, att.message_id)
        allowed = bool(
            cm and cm.supplier_po_no and _owned_po(db, user, cm.supplier_po_no)
        )
    if not allowed:
        raise HTTPException(404, "Attachment not found")
    return attachment_response(att)


# ── PO Follow-ups (staff /api/procurement mirrors, scoped to owned records) ─────
# Same response shapes (DashboardKpis / ProcurementListOut) and same filters as
# the staff procurement router, but every query carries an extra
# `owner_emp_code == user.emp_code` predicate so an employee only ever sees their
# own POs. This lets the staff PO Follow-ups page (store + components) be reused
# verbatim against these endpoints.
@router.get("/procurement/dashboard", response_model=DashboardKpis)
def procurement_dashboard(
    user: User = Depends(get_current_employee), db: Session = Depends(get_db)
) -> DashboardKpis:
    R = ProcurementRecord
    today = date.today()
    start = datetime.combine(today, datetime.min.time())
    end = datetime.combine(today, datetime.max.time())
    owned = R.owner_emp_code == user.emp_code

    row = db.execute(
        select(
            func.count().filter(owned),
            func.count().filter(owned, R.signal == "GREEN"),
            func.count().filter(owned, R.signal == "YELLOW"),
            func.count().filter(owned, R.signal == "RED"),
            func.count().filter(owned, R.signal == "BLACK"),
            func.count().filter(owned, R.shipment_date < start),
            func.count().filter(owned, R.shipment_date >= start, R.shipment_date < end),
            func.count().filter(owned, R.ai_required.is_(True)),
        )
    ).one()

    return DashboardKpis(
        total_records=row[0] or 0,
        green_count=row[1] or 0,
        yellow_count=row[2] or 0,
        red_count=row[3] or 0,
        black_count=row[4] or 0,
        overdue_count=row[5] or 0,
        due_today_count=row[6] or 0,
        ai_required_count=row[7] or 0,
    )


@router.get("/procurement/breakdown", response_model=ProcurementBreakdown)
def procurement_breakdown(
    user: User = Depends(get_current_employee),
    db: Session = Depends(get_db),
    signal: Optional[str] = None,
    supplier_name: Optional[str] = None,
    po_no: Optional[str] = None,
    supplier_po_no: Optional[str] = None,
    crm_no: Optional[str] = None,
    po_status: Optional[str] = None,
    shipment_date_from: Optional[date] = None,
    shipment_date_to: Optional[date] = None,
    search: Optional[str] = None,
) -> ProcurementBreakdown:
    """Same aggregations as the staff /breakdown, hard-scoped to the employee's own
    POs (owner_emp_code) — powers the buyer dashboard's supplier pie + pending count."""
    conds = [ProcurementRecord.owner_emp_code == user.emp_code]
    conds += breakdown_service.build_conditions(
        signal=signal, supplier_name=supplier_name, po_no=po_no,
        supplier_po_no=supplier_po_no, crm_no=crm_no, po_status=po_status,
        shipment_date_from=shipment_date_from, shipment_date_to=shipment_date_to,
        search=search,
    )
    return ProcurementBreakdown(**breakdown_service.compute_breakdown(db, conds))


@router.get("/procurement", response_model=ProcurementListOut)
def list_procurement(
    user: User = Depends(get_current_employee),
    db: Session = Depends(get_db),
    signal: Optional[str] = None,
    supplier_name: Optional[str] = None,
    po_no: Optional[str] = None,
    supplier_po_no: Optional[str] = None,
    crm_no: Optional[str] = None,
    po_status: Optional[str] = None,
    shipment_date_from: Optional[date] = None,
    shipment_date_to: Optional[date] = None,
    search: Optional[str] = None,
    page: int = 1,
    size: int = 50,
) -> ProcurementListOut:
    # Clamp to staff bounds (mirrors the /api/procurement Query(ge=1, le=500)).
    page = max(1, page)
    size = min(500, max(1, size))
    R = ProcurementRecord
    stmt = select(R).where(R.owner_emp_code == user.emp_code)
    if signal:
        stmt = stmt.where(R.signal == signal.upper())
    if supplier_name:
        stmt = stmt.where(R.supplier_name.ilike(f"%{supplier_name}%"))
    supplier_po_filter = supplier_po_no or po_no
    if supplier_po_filter:
        stmt = stmt.where(R.supplier_po_no.ilike(f"%{supplier_po_filter}%"))
    if crm_no:
        stmt = stmt.where(R.crm_no.ilike(f"%{crm_no}%"))
    if po_status:
        stmt = stmt.where(R.po_status == po_status)
    if shipment_date_from:
        stmt = stmt.where(
            R.shipment_date >= datetime.combine(shipment_date_from, datetime.min.time())
        )
    if shipment_date_to:
        stmt = stmt.where(
            R.shipment_date <= datetime.combine(shipment_date_to, datetime.max.time())
        )
    if search:
        like = f"%{search}%"
        stmt = stmt.where(
            or_(
                R.crm_no.ilike(like),
                R.supplier_po_no.ilike(like),
                R.material_name.ilike(like),
                R.supplier_name.ilike(like),
                R.po_status.ilike(like),
                R.signal.ilike(like),
            )
        )

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(R.shipment_date.asc().nulls_last())
        .offset((page - 1) * size)
        .limit(size)
    ).all()
    return ProcurementListOut(total=total, page=page, size=size, items=rows)


# ── Black Follow-ups (admin /api/ai/insights mirrors, scoped to owned POs) ──────
# The employee Black panel reuses the admin aggregation + command service; here we
# only enforce the scope boundary (owner_emp_code == user.emp_code). Unlike the
# admin command (manager+ to send), an employee may send on a PO they OWN.
def _owned_po_set(db: Session, emp_code: str | None) -> set[str]:
    if not emp_code:
        return set()
    rows = db.scalars(
        select(ProcurementRecord.supplier_po_no).where(
            ProcurementRecord.owner_emp_code == emp_code,
            ProcurementRecord.supplier_po_no.isnot(None),
        ).distinct()
    ).all()
    return {p for p in rows if p}


@router.get("/ai/insights/black-followups")
def employee_black_followups(
    user: User = Depends(get_current_employee),
    db: Session = Depends(get_db),
    limit: int = 100,
) -> dict:
    """Same shape as admin /black-followups, but only the employee's BLACK POs."""
    owned = _owned_po_set(db, user.emp_code)
    full = ai_insights.black_followups(db=db, limit=300)
    items = [i for i in full["items"] if i.get("supplier_po_no") in owned][: max(1, min(limit, 300))]
    return {
        "count": len(items),
        "chasing": sum(1 for i in items if not i["commitment_captured"]),
        "items": items,
    }


@router.get("/ai/insights/followup-history")
def employee_followup_history(
    user: User = Depends(get_current_employee),
    db: Session = Depends(get_db),
    signal: Optional[str] = None,
    outcome: Optional[str] = None,
    supplier_po_no: Optional[str] = None,
    limit: int = 100,
) -> dict:
    """Same shape as admin /followup-history, scoped to the employee's POs."""
    owned = _owned_po_set(db, user.emp_code)
    full = ai_insights.followup_history(
        db=db, signal=signal, outcome=outcome, supplier_po_no=supplier_po_no, limit=300
    )
    items = [i for i in full["items"] if i.get("supplier_po_no") in owned][: max(1, min(limit, 300))]
    return {"count": len(items), "items": items}


@router.post("/ai/insights/black-followups/command")
def employee_black_followup_command(
    payload: ai_insights.FollowupCommand,
    user: User = Depends(get_current_employee),
    db: Session = Depends(get_db),
) -> dict:
    """Draft/preview or send an AI follow-up — only on a PO the employee owns.

    Ownership IS the authorization here (no manager gate): an employee may send a
    follow-up on their own PO, consistent with the employee Communication Hub reply.
    """
    if payload.supplier_po_no not in _owned_po_set(db, user.emp_code):
        raise HTTPException(404, "PO not found for your account")
    result = po_followup_mail_service.command_followup(
        db,
        supplier_po_no=payload.supplier_po_no,
        instruction=payload.instruction,
        send=payload.send,
    )
    if not result.get("found"):
        raise HTTPException(404, result.get("error") or "PO not found")
    return result


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


def _msg_out(
    cm: CommunicationMessage,
    me: str | None,
    attachments: list[dict] | None = None,
) -> PortalMessage:
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
        attachments=attachments or [],
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
    atts = attachment_service.for_messages(db, [m.id for m in visible])
    return [_msg_out(m, user.full_name, atts.get(m.id)) for m in visible]


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
    bound = attachment_service.bind(
        db, cm.id, payload.attachment_ids,
        expect_kind="employee", expect_uploader_id=user.id,
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
    return _msg_out(cm, user.full_name, [attachment_service.out(a) for a in bound])


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

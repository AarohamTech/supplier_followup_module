"""Employee-scoped Communication Hub.

Mirrors the staff Communication Hub (`/api/communication-hub/*`) endpoint-for-
endpoint and RESPONSE-SHAPE-for-shape, but every payload is scoped to the POs the
logged-in employee owns. The employee portal frontend can therefore reuse the
admin hub components/types verbatim against this base URL.

Scoping rule (security boundary):
  * employee account = User with emp_code set, supplier_id NULL (get_current_employee)
  * a PO is in scope  ⇔ ∃ ProcurementRecord with that supplier_po_no AND
    owner_emp_code == user.emp_code
  * a supplier is in scope ⇔ it has ≥1 in-scope PO
  * any thread / task / message / commitment / mail the employee reads or mutates
    MUST belong to an in-scope PO, else → 404 (never leak existence).

Wherever possible this delegates to the existing admin hub functions and the
shared task logic in `routers.communication`, then filters/guards by scope — the
big query bodies are NOT duplicated.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.deps import get_current_employee
from ..database import get_db
from ..models.communication_message import CommunicationMessage
from ..models.hi_agent_chat_message import HiAgentChatMessage
from ..models.communication_task import CommunicationTask
from ..models.mail_history import MailHistory
from ..models.procurement import ProcurementRecord
from ..models.supplier import SupplierMaster
from ..models.user import User
from ..schemas.communication_task import (
    CommunicationTaskCreate,
    CommunicationTaskUpdate,
)
from ..services import po_followup_service
from ..services import task_assignment_service as assign
from . import communication as comm  # shared task logic (one source of truth)
from . import communication_hub as hub  # reuse admin aggregation + actions

router = APIRouter(prefix="/api/eportal/hub", tags=["employee-portal-hub"])


# ─────────────────────────────────────────────────────────────────────────────
# Scope helpers (the security boundary)
# ─────────────────────────────────────────────────────────────────────────────
def _owned_po_set(db: Session, emp_code: Optional[str]) -> set[str]:
    """Distinct supplier_po_no values the employee owns (owner_emp_code match)."""
    if not emp_code:
        return set()
    rows = db.scalars(
        select(ProcurementRecord.supplier_po_no)
        .where(
            ProcurementRecord.owner_emp_code == emp_code,
            ProcurementRecord.supplier_po_no.isnot(None),
        )
        .distinct()
    ).all()
    return {po for po in rows if po}


def _owned_supplier_names(db: Session, emp_code: Optional[str]) -> set[str]:
    """Uppercased supplier names that have ≥1 in-scope PO."""
    if not emp_code:
        return set()
    rows = db.scalars(
        select(ProcurementRecord.supplier_name)
        .where(
            ProcurementRecord.owner_emp_code == emp_code,
            ProcurementRecord.supplier_name.isnot(None),
        )
        .distinct()
    ).all()
    return {n.strip().upper() for n in rows if n and n.strip()}


def _emp_records(db: Session, emp_code: Optional[str]) -> list[ProcurementRecord]:
    if not emp_code:
        return []
    return list(
        db.scalars(
            select(ProcurementRecord).where(
                ProcurementRecord.owner_emp_code == emp_code
            )
        ).all()
    )


def _po_in_scope(db: Session, emp_code: Optional[str], supplier_po_no: Optional[str]) -> bool:
    if not emp_code or not supplier_po_no:
        return False
    return db.scalar(
        select(ProcurementRecord.id)
        .where(
            ProcurementRecord.owner_emp_code == emp_code,
            ProcurementRecord.supplier_po_no == supplier_po_no,
        )
        .limit(1)
    ) is not None


def _record_in_scope(
    db: Session, emp_code: Optional[str], procurement_record_id: Optional[int]
) -> Optional[ProcurementRecord]:
    """Return the record iff it (or its PO) is owned by the employee, else None."""
    if not emp_code or procurement_record_id is None:
        return None
    rec = db.get(ProcurementRecord, procurement_record_id)
    if rec is None:
        return None
    # The record itself may be owned, or it shares a PO with an owned record.
    if rec.owner_emp_code == emp_code:
        return rec
    if rec.supplier_po_no and _po_in_scope(db, emp_code, rec.supplier_po_no):
        return rec
    return None


def _resolve_scoped_po(
    db: Session,
    emp_code: Optional[str],
    *,
    supplier_po_no: Optional[str],
    procurement_record_id: Optional[int],
) -> str:
    """Resolve the supplier_po_no for a thread/action request and assert scope.

    Raises 404 (never leaks existence) when the resolved PO is not owned.
    """
    po_no = supplier_po_no
    if po_no is None and procurement_record_id is not None:
        rec = db.get(ProcurementRecord, procurement_record_id)
        po_no = rec.supplier_po_no if rec else None
    if not po_no or not _po_in_scope(db, emp_code, po_no):
        raise HTTPException(404, "PO not found for your account")
    return po_no


def _owned_supplier_name(
    db: Session,
    emp_code: Optional[str],
    *,
    supplier_id: Optional[int],
    supplier_name: Optional[str],
) -> Optional[str]:
    """Resolve a supplier name and return it iff the employee owns ≥1 PO with them.

    Used to scope non-PO "Other Mails" (which have no PO of their own). Returns
    None when the supplier can't be resolved or isn't owned, so callers can choose
    [] (list) or 404 (thread/mutate)."""
    name = supplier_name
    if name is None and supplier_id is not None:
        master = db.get(SupplierMaster, supplier_id)
        name = master.supplier_name if master else None
    if not name:
        return None
    return name if name.strip().upper() in _owned_supplier_names(db, emp_code) else None


# ─────────────────────────────────────────────────────────────────────────────
# 1. Dashboard — counts over in-scope POs only
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/dashboard")
def dashboard(
    user: User = Depends(get_current_employee), db: Session = Depends(get_db)
) -> dict[str, Any]:
    """Same shape as admin /dashboard, aggregated over the employee's POs only."""
    records = _emp_records(db, user.emp_code)
    owned_pos = {r.supplier_po_no for r in records if r.supplier_po_no}
    supplier_names = {
        r.supplier_name.strip().upper()
        for r in records
        if r.supplier_name and r.supplier_name.strip()
    }
    supplier_ids = {
        r.supplier_id for r in records if getattr(r, "supplier_id", None) is not None
    }

    # Mail history scoped to the employee's PO numbers.
    draft_mails = 0
    sent_mails = 0
    if owned_pos:
        draft_mails = int(
            db.execute(
                select(func.count(MailHistory.id)).where(
                    MailHistory.supplier_po_no.in_(owned_pos),
                    MailHistory.sent_status == "DRAFT",
                )
            ).scalar_one()
            or 0
        )
        sent_mails = int(
            db.execute(
                select(func.count(MailHistory.id)).where(
                    MailHistory.supplier_po_no.in_(owned_pos),
                    MailHistory.sent_status != "DRAFT",
                )
            ).scalar_one()
            or 0
        )

    open_tasks = 0
    critical_escalations = 0
    waiting_supplier = 0
    if owned_pos:
        open_tasks = int(
            db.execute(
                select(func.count(CommunicationTask.id)).where(
                    CommunicationTask.supplier_po_no.in_(owned_pos),
                    CommunicationTask.status != "DONE",
                )
            ).scalar_one()
            or 0
        )
        critical_escalations = int(
            db.execute(
                select(func.count(CommunicationTask.id)).where(
                    CommunicationTask.supplier_po_no.in_(owned_pos),
                    CommunicationTask.signal == "BLACK",
                )
            ).scalar_one()
            or 0
        )
        waiting_supplier = int(
            db.execute(
                select(func.count(CommunicationTask.id)).where(
                    CommunicationTask.supplier_po_no.in_(owned_pos),
                    CommunicationTask.status == "WAITING_SUPPLIER",
                )
            ).scalar_one()
            or 0
        )

    delayed_pos = len(
        {
            r.supplier_po_no
            for r in records
            if r.supplier_po_no and (r.signal or "").upper() in ("RED", "BLACK")
        }
    )

    unread_inbound = 0
    if owned_pos:
        unread_inbound = int(
            db.execute(
                select(func.count(CommunicationMessage.id)).where(
                    CommunicationMessage.direction == "INCOMING",
                    CommunicationMessage.read_at.is_(None),
                    CommunicationMessage.supplier_po_no.in_(owned_pos),
                )
            ).scalar_one()
            or 0
        )

    return {
        "active_suppliers": len(supplier_names),
        "active_pos": len(owned_pos),
        "draft_mails": draft_mails,
        "sent_mails": sent_mails,
        "open_tasks": open_tasks,
        "critical_escalations": critical_escalations,
        "delayed_pos": delayed_pos,
        "waiting_supplier": waiting_supplier,
        "unread_inbound": unread_inbound,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 2. Suppliers list — only suppliers with an in-scope PO
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/suppliers")
def list_suppliers(
    user: User = Depends(get_current_employee), db: Session = Depends(get_db)
) -> list[dict[str, Any]]:
    """Same shape as admin /suppliers, but only the employee's suppliers and with
    every aggregate (unread, signal, counts) computed over in-scope POs only."""
    owned_names = _owned_supplier_names(db, user.emp_code)
    if not owned_names:
        return []

    # Map uppercased name → master row (if any) so we can pass the real supplier_id.
    masters = db.scalars(
        select(SupplierMaster).where(SupplierMaster.is_active.is_(True))
    ).all()
    master_by_upper = {m.supplier_name.strip().upper(): m for m in masters}

    result: list[dict[str, Any]] = []
    for upper in sorted(owned_names):
        master = master_by_upper.get(upper)
        supplier_id = master.id if master else None
        display_name = master.supplier_name if master else upper
        # Use the original-cased name from a record when there is no master.
        if master is None:
            rec = db.scalar(
                select(ProcurementRecord).where(
                    ProcurementRecord.owner_emp_code == user.emp_code,
                    func.upper(ProcurementRecord.supplier_name) == upper,
                )
            )
            if rec and rec.supplier_name:
                display_name = rec.supplier_name
        result.append(
            _build_scoped_supplier_entry(db, user.emp_code, supplier_id, display_name)
        )

    result.sort(
        key=lambda s: (
            -(1 if s.get("unread_inbound") else 0),
            -hub._SIGNAL_RANK.get(hub._norm_signal(s["highest_signal"]), 1),
            -(1 if s["last_activity_at"] else 0),
        )
    )
    return result


def _build_scoped_supplier_entry(
    db: Session, emp_code: str, supplier_id: Optional[int], supplier_name: str
) -> dict[str, Any]:
    """Like hub._build_supplier_entry but every aggregate is restricted to the
    employee's owned POs for this supplier."""
    upper = supplier_name.strip().upper()
    owned_pos = {
        po
        for po in db.scalars(
            select(ProcurementRecord.supplier_po_no)
            .where(
                ProcurementRecord.owner_emp_code == emp_code,
                func.upper(ProcurementRecord.supplier_name) == upper,
                ProcurementRecord.supplier_po_no.isnot(None),
            )
            .distinct()
        ).all()
        if po
    }

    pos = db.scalars(
        select(ProcurementRecord).where(
            ProcurementRecord.owner_emp_code == emp_code,
            func.upper(ProcurementRecord.supplier_name) == upper,
        )
    ).all()

    mails = []
    open_task_count = 0
    unread_inbound = 0
    if owned_pos:
        mails = db.scalars(
            select(MailHistory)
            .where(
                func.upper(MailHistory.supplier_name) == upper,
                MailHistory.supplier_po_no.in_(owned_pos),
            )
            .order_by(MailHistory.created_at.desc())
        ).all()
        open_task_count = int(
            db.execute(
                select(func.count(CommunicationTask.id)).where(
                    CommunicationTask.supplier_po_no.in_(owned_pos),
                    CommunicationTask.status != "DONE",
                )
            ).scalar_one()
            or 0
        )
        unread_inbound = int(
            db.execute(
                select(func.count(CommunicationMessage.id)).where(
                    CommunicationMessage.direction == "INCOMING",
                    CommunicationMessage.read_at.is_(None),
                    CommunicationMessage.supplier_po_no.in_(owned_pos),
                )
            ).scalar_one()
            or 0
        )

    mapping_status = "NO_EMAIL"
    if supplier_id:
        from ..models.supplier_email import SupplierEmail

        email_row = db.scalar(
            select(SupplierEmail).where(
                SupplierEmail.supplier_id == supplier_id,
                SupplierEmail.is_active.is_(True),
            )
        )
        if email_row:
            mapping_status = "OK"

    # Non-PO "Other Mails" for this supplier. Scope is by owned-supplier (the
    # employee owns ≥1 PO with them); non-PO mails have no PO to scope by.
    non_po_count = int(
        db.execute(
            select(func.count(CommunicationMessage.id)).where(
                CommunicationMessage.direction == "INCOMING",
                CommunicationMessage.supplier_po_no.is_(None),
                func.upper(CommunicationMessage.supplier_name) == upper,
            )
        ).scalar_one()
        or 0
    )

    po_signals = [hub._norm_signal(p.signal) for p in pos]
    mail_signals = [hub._signal_from_mail_type(m.mail_type) for m in mails]
    highest = (
        hub._worst_signal(po_signals + mail_signals)
        if (po_signals or mail_signals)
        else "GREEN"
    )
    latest = mails[0] if mails else None
    draft_count = sum(1 for m in mails if m.sent_status == "DRAFT")

    return {
        "supplier_id": supplier_id,
        "supplier_name": supplier_name,
        "last_subject": latest.subject if latest else None,
        "last_activity_at": latest.created_at.isoformat() if latest else None,
        "open_po_count": len(owned_pos),
        "mail_count": len(mails),
        "draft_mail_count": draft_count,
        "task_count": open_task_count,
        "unread_inbound": int(unread_inbound or 0),
        "non_po_count": non_po_count,
        "highest_signal": highest,
        "health_score": hub._HEALTH.get(highest, 65),
        "mapping_status": mapping_status,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 3. PO list — only in-scope POs (mirrors admin pos shape)
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/pos")
def list_pos(
    supplier_name: Optional[str] = None,
    supplier_id: Optional[int] = None,
    user: User = Depends(get_current_employee),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """Same shape as admin POs list, restricted to in-scope POs.

    Resolves the supplier by name (or supplier_id → master name), builds the full
    admin PO payload via the shared service, then drops any PO the employee does
    not own."""
    name = supplier_name
    if name is None and supplier_id is not None:
        master = db.get(SupplierMaster, supplier_id)
        name = master.supplier_name if master else None
    if not name:
        return []

    owned_pos = {
        po
        for po in db.scalars(
            select(ProcurementRecord.supplier_po_no)
            .where(
                ProcurementRecord.owner_emp_code == user.emp_code,
                func.upper(ProcurementRecord.supplier_name) == name.strip().upper(),
                ProcurementRecord.supplier_po_no.isnot(None),
            )
            .distinct()
        ).all()
        if po
    }
    if not owned_pos:
        return []

    # Reuse the admin builder for the exact shape, then filter to owned POs.
    all_pos = hub._pos_for_supplier(db, supplier_id, name)
    return [p for p in all_pos if p.get("supplier_po_no") in owned_pos]


@router.get("/other-mails")
def list_other_mails(
    supplier_name: Optional[str] = None,
    supplier_id: Optional[int] = None,
    user: User = Depends(get_current_employee),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """Non-PO "Other Mails" for one of the employee's suppliers (same shape as
    admin). Empty list for a supplier the employee doesn't own (no existence leak)."""
    name = _owned_supplier_name(
        db, user.emp_code, supplier_id=supplier_id, supplier_name=supplier_name
    )
    if name is None:
        return []
    return hub.list_other_mails(supplier_id=supplier_id, supplier_name=name, db=db)


# ─────────────────────────────────────────────────────────────────────────────
# 4. PO thread — 404 if PO not in scope
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/thread")
def get_thread(
    supplier_po_no: Optional[str] = None,
    procurement_record_id: Optional[int] = None,
    supplier_id: Optional[int] = None,
    supplier_name: Optional[str] = None,
    non_po_subject: Optional[str] = None,
    user: User = Depends(get_current_employee),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Same shape as admin /thread; 404 if the PO (or non-PO supplier) is out of scope."""
    if non_po_subject is not None:
        name = _owned_supplier_name(
            db, user.emp_code, supplier_id=supplier_id, supplier_name=supplier_name
        )
        if name is None:
            raise HTTPException(404, "Mail not found for your account")
        return hub.get_thread(
            supplier_id=supplier_id, supplier_name=name, non_po_subject=non_po_subject, db=db
        )
    po_no = _resolve_scoped_po(
        db,
        user.emp_code,
        supplier_po_no=supplier_po_no,
        procurement_record_id=procurement_record_id,
    )
    return hub.get_thread(
        supplier_id=supplier_id,
        procurement_record_id=procurement_record_id,
        supplier_po_no=po_no,
        db=db,
    )


@router.post("/thread/mark-read")
def mark_thread_read(
    supplier_po_no: Optional[str] = None,
    procurement_record_id: Optional[int] = None,
    supplier_id: Optional[int] = None,
    supplier_name: Optional[str] = None,
    non_po_subject: Optional[str] = None,
    user: User = Depends(get_current_employee),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Same shape as admin mark-read; 404 if the PO (or non-PO supplier) is out of scope."""
    if non_po_subject is not None:
        name = _owned_supplier_name(
            db, user.emp_code, supplier_id=supplier_id, supplier_name=supplier_name
        )
        if name is None:
            raise HTTPException(404, "Mail not found for your account")
        return hub.mark_thread_read(
            supplier_id=supplier_id, supplier_name=name, non_po_subject=non_po_subject, db=db
        )
    po_no = _resolve_scoped_po(
        db,
        user.emp_code,
        supplier_po_no=supplier_po_no,
        procurement_record_id=procurement_record_id,
    )
    return hub.mark_thread_read(
        supplier_po_no=po_no,
        procurement_record_id=procurement_record_id,
        db=db,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 5. Tasks grouped by status — only in-scope PO tasks
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/tasks")
def get_tasks(
    supplier_id: Optional[int] = None,
    procurement_record_id: Optional[int] = None,
    supplier_po_no: Optional[str] = None,
    user: User = Depends(get_current_employee),
    db: Session = Depends(get_db),
) -> dict[str, list[dict[str, Any]]]:
    """Same grouped shape as admin /tasks, but only tasks on in-scope POs.

    When a specific PO is requested it must be in scope (else 404). When no PO is
    given, results are restricted to the union of the employee's owned POs."""
    owned_pos = _owned_po_set(db, user.emp_code)
    empty = {"todo": [], "waiting_supplier": [], "in_progress": [], "done": []}
    if not owned_pos:
        return empty

    po_no = supplier_po_no
    if po_no is None and procurement_record_id is not None:
        rec = db.get(ProcurementRecord, procurement_record_id)
        po_no = rec.supplier_po_no if rec else None

    if po_no is not None:
        if po_no not in owned_pos:
            raise HTTPException(404, "PO not found for your account")
        return hub.get_hub_tasks(
            supplier_id=supplier_id,
            procurement_record_id=procurement_record_id,
            supplier_po_no=po_no,
            db=db,
        )

    # No specific PO → all tasks across the employee's owned POs.
    all_tasks = db.scalars(
        select(CommunicationTask)
        .where(CommunicationTask.supplier_po_no.in_(owned_pos))
        .order_by(CommunicationTask.created_at.desc())
    ).all()
    grouped: dict[str, list[dict[str, Any]]] = {
        "todo": [],
        "waiting_supplier": [],
        "in_progress": [],
        "done": [],
    }
    for t in all_tasks:
        entry = hub._task_dict(t)
        s = (t.status or "TODO").upper()
        if s == "TODO":
            grouped["todo"].append(entry)
        elif s == "WAITING_SUPPLIER":
            grouped["waiting_supplier"].append(entry)
        elif s == "IN_PROGRESS":
            grouped["in_progress"].append(entry)
        else:
            grouped["done"].append(entry)
    return grouped


# ─────────────────────────────────────────────────────────────────────────────
# 6. Create task (delegates to shared logic; PO must be in scope)
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/tasks", status_code=201)
def create_task(
    payload: CommunicationTaskCreate,
    user: User = Depends(get_current_employee),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Create a task on an in-scope PO. Validates scope BEFORE delegating to the
    shared staff create logic (so assignee resolution / activity log are identical
    to the admin hub). Returns the admin task dict shape."""
    owned_pos = _owned_po_set(db, user.emp_code)
    if payload.supplier_po_no:
        if payload.supplier_po_no not in owned_pos:
            raise HTTPException(404, "PO not found for your account")
    elif payload.assigned_to_user_id is None:
        # Personal task with no PO → pin to the employee so it stays in scope.
        payload.assigned_to_user_id = user.id
    row = comm.create_task(payload=payload, db=db, actor=user)
    return hub._task_dict(row)


# ─────────────────────────────────────────────────────────────────────────────
# 7. Update task (PO must be in scope)
# ─────────────────────────────────────────────────────────────────────────────
@router.patch("/tasks/{task_id}")
def update_task(
    task_id: int,
    payload: CommunicationTaskUpdate,
    user: User = Depends(get_current_employee),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Update a task on an in-scope PO. 404 if the task's PO is not owned (or the
    task does not exist). Delegates to the shared staff update logic."""
    owned_pos = _owned_po_set(db, user.emp_code)
    row = db.get(CommunicationTask, task_id)
    if row is None or not (row.supplier_po_no and row.supplier_po_no in owned_pos):
        raise HTTPException(404, "Task not found for your account")
    updated = comm.update_task(task_id=task_id, payload=payload, db=db, actor=user)
    return hub._task_dict(updated)


# ─────────────────────────────────────────────────────────────────────────────
# 8. AI reply — scoped to an in-scope PO record
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/ai-reply")
def ai_reply(
    procurement_record_id: int = Query(...),
    user: User = Depends(get_current_employee),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Same shape as admin /ai-reply; 404 if the record's PO is not in scope."""
    if _record_in_scope(db, user.emp_code, procurement_record_id) is None:
        raise HTTPException(404, "Procurement record not found")
    return hub.ai_reply(procurement_record_id=procurement_record_id, db=db)


# ─────────────────────────────────────────────────────────────────────────────
# 9. Reply on a PO thread — 404 if PO not in scope (may send real email)
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/reply")
def reply_now(
    payload: hub.HubReplyIn,
    user: User = Depends(get_current_employee),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Same shape as admin /reply; 404 if the PO (or non-PO supplier) is out of scope."""
    is_non_po = bool(
        payload.non_po_subject
        and not payload.supplier_po_no
        and payload.procurement_record_id is None
    )
    if is_non_po:
        name = _owned_supplier_name(
            db, user.emp_code,
            supplier_id=payload.supplier_id, supplier_name=payload.supplier_name,
        )
        if name is None:
            raise HTTPException(404, "Mail not found for your account")
    else:
        _resolve_scoped_po(
            db,
            user.emp_code,
            supplier_po_no=payload.supplier_po_no,
            procurement_record_id=payload.procurement_record_id,
        )
    return hub.reply_now(payload=payload, db=db)


# ─────────────────────────────────────────────────────────────────────────────
# 10. Escalate — 404 if record's PO not in scope
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/escalate")
def escalate(
    procurement_record_id: int = Query(...),
    user: User = Depends(get_current_employee),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Same shape as admin /escalate; 404 if the record's PO is not in scope."""
    if _record_in_scope(db, user.emp_code, procurement_record_id) is None:
        raise HTTPException(404, "Procurement record not found")
    return hub.escalate(procurement_record_id=procurement_record_id, db=db)


# ─────────────────────────────────────────────────────────────────────────────
# 11. Send / approve / discard a mail draft — only if it belongs to an in-scope PO
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/send-mail")
def send_mail_now(
    mail_history_id: int = Query(..., description="MailHistory row to send"),
    user: User = Depends(get_current_employee),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Same shape as admin /send-mail; 404 if the mail's PO is not in scope."""
    history = db.get(MailHistory, mail_history_id)
    if history is None or not _po_in_scope(db, user.emp_code, history.supplier_po_no):
        raise HTTPException(404, "MailHistory not found")
    return hub.send_mail_now(mail_history_id=mail_history_id, db=db)


@router.post("/messages/{message_id}/approve")
def approve_message(
    message_id: int,
    user: User = Depends(get_current_employee),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Approve a DRAFT outbound message whose PO is in scope (else 404)."""
    msg = _scoped_message_or_404(db, user.emp_code, message_id)
    if msg.direction != "OUTGOING" or msg.status != "DRAFT":
        raise HTTPException(409, "Only OUTGOING DRAFT messages can be approved")
    msg.status = "READY"
    db.commit()
    return {"ok": True, "message_id": msg.id, "status": msg.status}


@router.post("/messages/{message_id}/discard")
def discard_message(
    message_id: int,
    user: User = Depends(get_current_employee),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Discard a DRAFT outbound message whose PO is in scope (else 404)."""
    msg = _scoped_message_or_404(db, user.emp_code, message_id)
    if msg.direction != "OUTGOING" or msg.status != "DRAFT":
        raise HTTPException(409, "Only OUTGOING DRAFT messages can be discarded")
    db.delete(msg)
    db.commit()
    return {"ok": True, "discarded_id": message_id}


def _scoped_message_or_404(
    db: Session, emp_code: Optional[str], message_id: int
) -> CommunicationMessage:
    msg = db.get(CommunicationMessage, message_id)
    if msg is None or not _po_in_scope(db, emp_code, msg.supplier_po_no):
        raise HTTPException(404, "Message not found")
    return msg


# ─────────────────────────────────────────────────────────────────────────────
# 12. Commitments — scoped to an in-scope PO
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/commitments")
def list_commitments(
    supplier_po_no: str = Query(...),
    supplier_name: Optional[str] = None,
    user: User = Depends(get_current_employee),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """Supplier commitments for an in-scope PO (same shape as the po-followups
    commitments endpoint). 404 if the PO is not owned."""
    if not _po_in_scope(db, user.emp_code, supplier_po_no):
        raise HTTPException(404, "PO not found for your account")
    return po_followup_service.list_commitments(
        db, supplier_po_no=supplier_po_no, supplier_name=supplier_name
    )


# ─────────────────────────────────────────────────────────────────────────────
# 13. HI agent (/hi) — scoped to an in-scope PO context
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/agent/history")
def get_agent_history(
    procurement_record_id: int = Query(...),
    user: User = Depends(get_current_employee),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return HI history only when this employee owns the PO thread."""
    _resolve_scoped_po(
        db, user.emp_code,
        supplier_po_no=None,
        procurement_record_id=procurement_record_id,
    )
    return hub.get_agent_history(procurement_record_id=procurement_record_id, db=db)


@router.post("/agent")
def run_agent(
    payload: hub.HubAgentIn,
    user: User = Depends(get_current_employee),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Same shape as admin /agent, but the thread context must be an in-scope PO.

    Customer-mail threads are not part of the employee surface → 404 if supplied."""
    if payload.customer_mail_id is not None:
        raise HTTPException(404, "Customer mail not found")
    _resolve_scoped_po(
        db,
        user.emp_code,
        supplier_po_no=payload.supplier_po_no,
        procurement_record_id=payload.procurement_record_id,
    )
    return hub.run_agent(payload=payload, user=user, db=db)


@router.post("/agent/confirm")
def confirm_agent_action(
    payload: hub.HubAgentConfirmIn,
    user: User = Depends(get_current_employee),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Confirm a pending HI-agent draft/subscription. Drafts are scope-checked by
    PO; subscriptions are owned by the requesting user, so they pass through."""
    if payload.action_type == "draft":
        # Only a draft on an in-scope PO can be confirmed/sent by an employee.
        _scoped_message_or_404(db, user.emp_code, payload.id)
    return hub.confirm_agent_action(payload=payload, db=db)


@router.post("/agent/history/dismiss")
def dismiss_agent_action(
    payload: hub.HubAgentDismissIn,
    user: User = Depends(get_current_employee),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    row = db.get(HiAgentChatMessage, payload.chat_message_id)
    if row is None:
        raise HTTPException(404, "Chat message not found")
    _resolve_scoped_po(
        db, user.emp_code,
        supplier_po_no=None,
        procurement_record_id=row.procurement_record_id,
    )
    return hub.dismiss_agent_action(payload=payload, db=db)


# ─────────────────────────────────────────────────────────────────────────────
# 14. Assignees + mention targets — same set as staff (NOT PO-scoped)
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/assignees")
def list_assignees(
    user: User = Depends(get_current_employee), db: Session = Depends(get_db)
) -> list[dict]:
    """Assignable staff/employee accounts for the picker (same set as staff)."""
    return assign.list_assignees(db)


@router.get("/mention-targets")
def list_mention_targets(
    user: User = Depends(get_current_employee), db: Session = Depends(get_db)
) -> list[dict]:
    """@-mention candidates for the /hi assistant (same set as staff)."""
    return assign.list_mention_targets(db)

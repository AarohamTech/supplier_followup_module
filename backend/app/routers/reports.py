"""Admin workload reports — per-user, per-supplier, and overall rollups.

One endpoint (`GET /api/reports/workload`) returns everything the admin
reporting dashboard needs in a single round-trip:

- ``users``      — every active internal account with the POs they own
                   (via ``ProcurementRecord.owner_emp_code == User.emp_code``)
                   and their task workload (``assigned_to_user_id``).
- ``suppliers``  — every active supplier with PO/signal/task/mail/ASN rollups
                   (procurement joins by UPPER(supplier_name); other tables
                   carry supplier_name too).
- ``overall``    — system-wide totals of the same measures.

Aggregations use SUM(CASE …) so they run identically on SQLite (tests) and
Postgres (prod). Mounted admin-only in main.py.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.asn import Asn
from ..models.communication_message import CommunicationMessage
from ..models.communication_task import CommunicationTask
from ..models.procurement import ProcurementRecord
from ..models.supplier import SupplierMaster
from ..models.user import User

router = APIRouter(prefix="/api/reports", tags=["reports"])

# Mirrors procurement_breakdown_service: a PO line is "pending" until its
# ERP status says it left the building.
_DELIVERED_STATUS = ("DISPATCHED", "DELIVERED", "CLOSED", "COMPLETED", "RECEIVED")
_ASN_CLOSED = ("DELIVERED", "CANCELLED")


def _one(x: Any) -> int:
    return int(x or 0)


def _po_measures() -> list[Any]:
    """Shared per-group PO aggregate columns (order matters — unpacked below)."""
    R = ProcurementRecord
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    pending = case(
        (R.po_status.is_(None), 1),
        (func.upper(R.po_status).notin_(_DELIVERED_STATUS), 1),
        else_=0,
    )
    overdue = case(
        (func.coalesce(R.shipment_date, today) < today, 1),
        else_=0,
    )
    sig = func.upper(func.coalesce(R.signal, ""))
    return [
        func.count(R.id),
        func.sum(pending),
        func.sum(overdue),
        func.sum(case((sig == "GREEN", 1), else_=0)),
        func.sum(case((sig == "YELLOW", 1), else_=0)),
        func.sum(case((sig == "RED", 1), else_=0)),
        func.sum(case((sig == "BLACK", 1), else_=0)),
        func.avg(func.coalesce(R.followup_count, 0)),
    ]


def _po_dict(row: Any) -> dict[str, Any]:
    return {
        "total": _one(row[0]),
        "pending": _one(row[1]),
        "overdue": _one(row[2]),
        "green": _one(row[3]),
        "yellow": _one(row[4]),
        "red": _one(row[5]),
        "black": _one(row[6]),
        "avg_followups": round(float(row[7] or 0), 1),
    }


def _task_measures() -> list[Any]:
    T = CommunicationTask
    now = datetime.utcnow()
    open_ = case((T.status != "DONE", 1), else_=0)
    overdue = case(
        (T.status != "DONE", case((func.coalesce(T.due_date, now) < now, 1), else_=0)),
        else_=0,
    )
    done = case((T.status == "DONE", 1), else_=0)
    due_today = case(
        (T.status != "DONE",
         case((T.due_date.between(now, now + timedelta(days=1)), 1), else_=0)),
        else_=0,
    )
    escalations = case(
        (T.task_source == "ESCALATION", case((T.status != "DONE", 1), else_=0)),
        else_=0,
    )
    return [
        func.count(T.id),
        func.sum(open_),
        func.sum(overdue),
        func.sum(done),
        func.sum(due_today),
        func.sum(escalations),
    ]


def _task_dict(row: Any) -> dict[str, Any]:
    return {
        "total": _one(row[0]),
        "open": _one(row[1]),
        "overdue": _one(row[2]),
        "done": _one(row[3]),
        "due_today": _one(row[4]),
        "escalations": _one(row[5]),
    }


_EMPTY_PO = {"total": 0, "pending": 0, "overdue": 0, "green": 0, "yellow": 0,
             "red": 0, "black": 0, "avg_followups": 0.0}
_EMPTY_TASK = {"total": 0, "open": 0, "overdue": 0, "done": 0, "due_today": 0,
               "escalations": 0}


@router.get("/workload")
def workload_report(db: Session = Depends(get_db)) -> dict[str, Any]:
    R, T, M, A = ProcurementRecord, CommunicationTask, CommunicationMessage, Asn

    # ── per-user ────────────────────────────────────────────────────────────
    users = list(
        db.scalars(
            select(User).where(User.is_active.is_(True), User.supplier_id.is_(None))
            .order_by(User.full_name.nullslast(), User.username)
        ).all()
    )
    po_by_emp = {
        (code or ""): row
        for code, *row in db.execute(
            select(R.owner_emp_code, *_po_measures())
            .where(R.owner_emp_code.is_not(None))
            .group_by(R.owner_emp_code)
        ).all()
    }
    task_by_user = {
        uid: row
        for uid, *row in db.execute(
            select(T.assigned_to_user_id, *_task_measures())
            .where(T.assigned_to_user_id.is_not(None))
            .group_by(T.assigned_to_user_id)
        ).all()
    }
    user_rows = []
    for u in users:
        po = po_by_emp.get((u.emp_code or "").strip())
        tk = task_by_user.get(u.id)
        user_rows.append({
            "user_id": u.id,
            "name": u.full_name or u.username or u.email,
            "role": u.role,
            "emp_code": u.emp_code,
            "last_login_at": u.last_login_at,
            "pos": _po_dict(po) if po else dict(_EMPTY_PO),
            "tasks": _task_dict(tk) if tk else dict(_EMPTY_TASK),
        })
    # Busiest first: open tasks, then pending POs.
    user_rows.sort(key=lambda r: (-r["tasks"]["open"], -r["pos"]["pending"], r["name"] or ""))

    # ── per-supplier (join key: UPPER(supplier_name)) ───────────────────────
    def _by_name(stmt) -> dict[str, Any]:
        return {(name or "").upper(): row for name, *row in db.execute(stmt).all()}

    po_by_sup = _by_name(
        select(R.supplier_name, *_po_measures())
        .where(R.supplier_name.is_not(None))
        .group_by(R.supplier_name)
    )
    task_by_sup = _by_name(
        select(T.supplier_name, *_task_measures())
        .where(T.supplier_name.is_not(None))
        .group_by(T.supplier_name)
    )
    mail_by_sup = _by_name(
        select(
            M.supplier_name,
            func.sum(case((M.direction == "INCOMING", 1), else_=0)),
            func.sum(case((M.direction == "OUTGOING", 1), else_=0)),
            func.sum(case(
                (M.direction == "INCOMING",
                 case((M.read_at.is_(None), 1), else_=0)),
                else_=0,
            )),
        )
        .where(M.supplier_name.is_not(None))
        .group_by(M.supplier_name)
    )
    asn_by_sup = _by_name(
        select(
            A.supplier_name,
            func.count(A.id),
            func.sum(case(
                (func.upper(A.status).notin_(_ASN_CLOSED + ("DRAFT",)), 1), else_=0,
            )),
            func.sum(case((func.upper(A.status) == "DELIVERED", 1), else_=0)),
        )
        .where(A.supplier_name.is_not(None))
        .group_by(A.supplier_name)
    )

    supplier_rows = []
    for s in db.scalars(
        select(SupplierMaster).where(SupplierMaster.is_active.is_(True))
        .order_by(SupplierMaster.supplier_name)
    ).all():
        key = (s.supplier_name or "").upper()
        po = po_by_sup.get(key)
        tk = task_by_sup.get(key)
        ml = mail_by_sup.get(key)
        an = asn_by_sup.get(key)
        po_d = _po_dict(po) if po else dict(_EMPTY_PO)
        worst = next(
            (c for c in ("BLACK", "RED", "YELLOW", "GREEN") if po_d[c.lower()] > 0),
            None,
        )
        supplier_rows.append({
            "supplier_id": s.id,
            "supplier_name": s.supplier_name,
            "worst_signal": worst,
            "pos": po_d,
            "tasks": _task_dict(tk) if tk else dict(_EMPTY_TASK),
            "mails": {
                "incoming": _one(ml[0]) if ml else 0,
                "outgoing": _one(ml[1]) if ml else 0,
                "unread": _one(ml[2]) if ml else 0,
            },
            "asns": {
                "total": _one(an[0]) if an else 0,
                "in_transit": _one(an[1]) if an else 0,
                "delivered": _one(an[2]) if an else 0,
            },
        })
    supplier_rows.sort(
        key=lambda r: (-r["pos"]["black"], -r["pos"]["red"], -r["pos"]["pending"],
                       r["supplier_name"] or "")
    )

    # ── overall ─────────────────────────────────────────────────────────────
    po_all = db.execute(select(*_po_measures())).one()
    task_all = db.execute(select(*_task_measures())).one()
    overall = {
        "pos": _po_dict(po_all),
        "tasks": _task_dict(task_all),
        "suppliers_active": len(supplier_rows),
        "internal_users": len(user_rows),
        "unassigned_open_tasks": _one(db.scalar(
            select(func.count(T.id)).where(
                T.status != "DONE", T.assigned_to_user_id.is_(None)
            )
        )),
        "unread_inbound": _one(db.scalar(
            select(func.count(M.id)).where(
                M.direction == "INCOMING", M.read_at.is_(None)
            )
        )),
        "asns_in_transit": _one(db.scalar(
            select(func.count(A.id)).where(
                func.upper(A.status).notin_(_ASN_CLOSED + ("DRAFT",))
            )
        )),
        "generated_at": datetime.utcnow(),
    }
    return {"overall": overall, "users": user_rows, "suppliers": supplier_rows}

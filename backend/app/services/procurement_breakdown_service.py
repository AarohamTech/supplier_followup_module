"""Dashboard aggregations over procurement_records.

Given a set of filter conditions, returns signal counts, the open/not-delivered
("pending") count, and the supplier distribution (top-N suppliers + an aggregated
"Others" slice). Shared by the staff dashboard (all POs, optionally filtered by
employee / supplier / signal) and the employee dashboard (scoped to owner_emp_code),
so both compute the pies from the full result set rather than one page of rows.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..models.procurement import ProcurementRecord

# A line is "delivered / closed" (no longer pending) when its source po_status is
# one of these. Mirrors ai_insights_service._DELIVERED_STATUS.
_DELIVERED_STATUS = ("DISPATCHED", "DELIVERED", "CLOSED", "COMPLETED", "RECEIVED")
_TOP_SUPPLIERS = 8


def build_conditions(
    *,
    signal: Optional[str] = None,
    supplier_name: Optional[str] = None,
    po_no: Optional[str] = None,
    supplier_po_no: Optional[str] = None,
    crm_no: Optional[str] = None,
    po_status: Optional[str] = None,
    owner_emp_code: Optional[str] = None,
    shipment_date_from: Optional[date] = None,
    shipment_date_to: Optional[date] = None,
    search: Optional[str] = None,
) -> list:
    """Translate the shared dashboard/list query params into SQLAlchemy predicates.

    Kept in one place so the list endpoints and the breakdown endpoints filter
    identically (a supplier pie must reflect the same rows the table shows)."""
    R = ProcurementRecord
    conds: list = []
    if signal:
        conds.append(R.signal == signal.upper())
    if supplier_name:
        conds.append(R.supplier_name.ilike(f"%{supplier_name}%"))
    supplier_po_filter = supplier_po_no or po_no
    if supplier_po_filter:
        conds.append(R.supplier_po_no.ilike(f"%{supplier_po_filter}%"))
    if crm_no:
        conds.append(R.crm_no.ilike(f"%{crm_no}%"))
    if po_status:
        conds.append(R.po_status == po_status)
    if owner_emp_code:
        conds.append(R.owner_emp_code == owner_emp_code)
    if shipment_date_from:
        conds.append(R.shipment_date >= datetime.combine(shipment_date_from, datetime.min.time()))
    if shipment_date_to:
        conds.append(R.shipment_date <= datetime.combine(shipment_date_to, datetime.max.time()))
    if search:
        like = f"%{search}%"
        conds.append(
            or_(
                R.crm_no.ilike(like),
                R.supplier_po_no.ilike(like),
                R.material_name.ilike(like),
                R.supplier_name.ilike(like),
                R.po_status.ilike(like),
                R.signal.ilike(like),
            )
        )
    return conds


def compute_breakdown(db: Session, conditions: list) -> dict:
    """Signal counts + pending count + supplier distribution under `conditions`."""
    R = ProcurementRecord

    def scoped(*cols):
        stmt = select(*cols)
        for cond in conditions:
            stmt = stmt.where(cond)
        return stmt

    # NULL po_status counts as pending ("not yet delivered"); NOT IN alone would
    # drop NULLs, so OR them back in.
    not_delivered = or_(
        R.po_status.is_(None),
        func.upper(R.po_status).notin_(_DELIVERED_STATUS),
    )

    row = db.execute(
        scoped(
            func.count(),
            func.count().filter(R.signal == "GREEN"),
            func.count().filter(R.signal == "YELLOW"),
            func.count().filter(R.signal == "RED"),
            func.count().filter(R.signal == "BLACK"),
            func.count().filter(not_delivered),
        )
    ).one()

    name = func.coalesce(R.supplier_name, "—")
    supplier_rows = db.execute(
        scoped(name.label("name"), func.count().label("cnt")).group_by(name).order_by(func.count().desc())
    ).all()

    by_supplier = [{"name": r.name, "count": r.cnt} for r in supplier_rows[:_TOP_SUPPLIERS]]
    others = sum(r.cnt for r in supplier_rows[_TOP_SUPPLIERS:])
    if others:
        by_supplier.append({"name": "Others", "count": others})

    return {
        "total": row[0] or 0,
        "green_count": row[1] or 0,
        "yellow_count": row[2] or 0,
        "red_count": row[3] or 0,
        "black_count": row[4] or 0,
        "pending_count": row[5] or 0,
        "by_supplier": by_supplier,
    }

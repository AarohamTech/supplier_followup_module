from datetime import date, datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, or_
from sqlalchemy.orm import Session

from ..core.deps import require_admin, require_manager
from ..database import get_db
from ..models.crm_ingest_log import CrmIngestLog
from ..models.procurement import ProcurementRecord
from ..schemas.procurement import (
    ProcurementCreate, ProcurementUpdate, ProcurementOut,
    ProcurementListOut, ProcurementSyncSummary, DashboardKpis, CrmIngestLogOut,
    ProcurementBreakdown,
)
from ..services.procurement_sync_service import (
    ACCEPTED_EXCEL_COLUMNS,
    COLUMN_ALIASES,
    sync_procurement_rows,
)
from ..services.followup_engine import apply_followup_logic
from ..services import crm_ingest_service
from ..services import procurement_breakdown_service as breakdown_service

router = APIRouter(prefix="/api/procurement", tags=["procurement"])


@router.get("/dashboard", response_model=DashboardKpis)
def dashboard(db: Session = Depends(get_db), owner_emp_code: Optional[str] = None):
    R = ProcurementRecord
    today = date.today()
    start = datetime.combine(today, datetime.min.time())
    end = datetime.combine(today, datetime.max.time())

    # Optional employee scope: every KPI is counted only within the selected
    # employee's owned POs (mirrors the /breakdown + list owner_emp_code filter),
    # so the whole dashboard re-scopes from one control.
    owner = (R.owner_emp_code == owner_emp_code) if owner_emp_code else None

    def cnt(*conds):
        all_conds = list(conds) + ([owner] if owner is not None else [])
        return func.count().filter(*all_conds) if all_conds else func.count()

    # Single round-trip: conditional COUNT(*) FILTER(...) instead of 8 queries —
    # the DB is cross-region, so collapsing round-trips is the main win.
    row = db.execute(
        select(
            cnt(),
            cnt(R.signal == "GREEN"),
            cnt(R.signal == "YELLOW"),
            cnt(R.signal == "RED"),
            cnt(R.signal == "BLACK"),
            cnt(R.shipment_date < start),
            cnt(R.shipment_date >= start, R.shipment_date < end),
            cnt(R.ai_required.is_(True)),
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


@router.get("/breakdown", response_model=ProcurementBreakdown)
def breakdown(
    db: Session = Depends(get_db),
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
):
    """Signal + supplier + pending aggregations for the dashboard pies, under the
    same filters as the list (so the pies match the visible table)."""
    conds = breakdown_service.build_conditions(
        signal=signal, supplier_name=supplier_name, po_no=po_no,
        supplier_po_no=supplier_po_no, crm_no=crm_no, po_status=po_status,
        owner_emp_code=owner_emp_code, shipment_date_from=shipment_date_from,
        shipment_date_to=shipment_date_to, search=search,
    )
    return ProcurementBreakdown(**breakdown_service.compute_breakdown(db, conds))


@router.get("", response_model=ProcurementListOut)
def list_records(
    db: Session = Depends(get_db),
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
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=500),
):
    R = ProcurementRecord
    stmt = select(R)
    if signal: stmt = stmt.where(R.signal == signal.upper())
    if supplier_name: stmt = stmt.where(R.supplier_name.ilike(f"%{supplier_name}%"))
    supplier_po_filter = supplier_po_no or po_no
    if supplier_po_filter: stmt = stmt.where(R.supplier_po_no.ilike(f"%{supplier_po_filter}%"))
    if crm_no: stmt = stmt.where(R.crm_no.ilike(f"%{crm_no}%"))
    if po_status: stmt = stmt.where(R.po_status == po_status)
    if owner_emp_code: stmt = stmt.where(R.owner_emp_code == owner_emp_code)
    if shipment_date_from:
        stmt = stmt.where(R.shipment_date >= datetime.combine(shipment_date_from, datetime.min.time()))
    if shipment_date_to:
        stmt = stmt.where(R.shipment_date <= datetime.combine(shipment_date_to, datetime.max.time()))
    if search:
        like = f"%{search}%"
        stmt = stmt.where(or_(
            R.crm_no.ilike(like),
            R.supplier_po_no.ilike(like),
            R.material_name.ilike(like),
            R.supplier_name.ilike(like),
            R.po_status.ilike(like),
            R.signal.ilike(like),
        ))

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(R.shipment_date.asc().nulls_last() if hasattr(R.shipment_date, "asc") else R.id.desc())
            .offset((page - 1) * size).limit(size)
    ).all()
    return ProcurementListOut(total=total, page=page, size=size, items=rows)


@router.get("/columns")
def columns():
    return {
        "unique_key": ["crm_no", "supplier_po_no", "material_name"],
        "excel_columns": ACCEPTED_EXCEL_COLUMNS,
        "field_names": list(ProcurementCreate.model_fields.keys()),
        "aliases": COLUMN_ALIASES,
        "notes": {"po_no": "Deprecated alias. It maps to supplier_po_no for backward-compatible JSON only."},
    }


@router.get(
    "/crm-ingestion-logs",
    response_model=list[CrmIngestLogOut],
    dependencies=[Depends(require_admin)],
)
def crm_ingestion_logs(
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=500),
) -> list[CrmIngestLog]:
    """Admin-only CRM fetch history: how many POs were fetched / added / changed."""
    return list(
        db.scalars(select(CrmIngestLog).order_by(CrmIngestLog.ran_at.desc()).limit(limit)).all()
    )


@router.get("/{rec_id}", response_model=ProcurementOut)
def get_one(rec_id: int, db: Session = Depends(get_db)):
    rec = db.get(ProcurementRecord, rec_id)
    if not rec:
        raise HTTPException(404, "Not found")
    return rec


@router.post("/sync", response_model=ProcurementSyncSummary)
def sync_endpoint(payload: list[dict[str, Any]], db: Session = Depends(get_db)):
    return sync_procurement_rows(db, payload, source="json")


@router.post("/crm-sync", dependencies=[Depends(require_manager)])
def crm_sync_now(db: Session = Depends(get_db)) -> dict:
    """Manually trigger a live CRM ingestion run (manager+). Records a fetch log."""
    return crm_ingest_service.poll_and_ingest(db, trigger="manual")


@router.put("/{rec_id}", response_model=ProcurementOut)
def update_record(rec_id: int, payload: ProcurementUpdate, db: Session = Depends(get_db)):
    rec = db.get(ProcurementRecord, rec_id)
    if not rec:
        raise HTTPException(404, "Not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(rec, k, v)
    apply_followup_logic(rec)
    db.commit()
    db.refresh(rec)
    return rec

"""DTOs for the internal employee portal (read-only, scoped to one employee)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class EmployeeSummary(BaseModel):
    emp_code: str | None = None
    full_name: str | None = None
    total_pos: int = 0
    total_materials: int = 0
    green: int = 0
    yellow: int = 0
    red: int = 0
    black: int = 0
    escalated_pos: int = 0
    overdue_pos: int = 0


class EmployeePo(BaseModel):
    supplier_po_no: str
    crm_no: Optional[str] = None
    supplier_name: Optional[str] = None
    material_count: int = 0
    overall_signal: Optional[str] = None
    po_status: Optional[str] = None
    # NULL / "PENDING" (cancel requested, awaiting confirmation) / "CANCELLED".
    cancellation_status: Optional[str] = None
    # Receipt rollup from CRM GRN quantities: PENDING / PARTIAL / COMPLETED.
    receipt_status: Optional[str] = None
    # End-customer this PO serves; None => ordered directly (Direct PO).
    customer_name: Optional[str] = None
    is_direct: bool = False
    earliest_shipment_date: Optional[datetime] = None
    escalated: bool = False
    # Unread supplier replies (INCOMING, not yet read) on this PO.
    unread_inbound: int = 0


class EmployeePoListResponse(BaseModel):
    count: int
    items: list[EmployeePo]


class EmployeePoMaterial(BaseModel):
    procurement_record_id: int
    crm_no: Optional[str] = None
    material_name: str
    uom: Optional[str] = None
    qty: Optional[float] = None
    supplier_name: Optional[str] = None
    shipment_date: Optional[datetime] = None
    signal: Optional[str] = None
    po_status: Optional[str] = None
    rate: Optional[float] = None
    lead_time: Optional[int] = None
    commitment_date: Optional[datetime] = None
    # Receipt quantities from the CRM desk feed (GRN progress).
    po_qty: Optional[float] = None
    grn_qty: Optional[float] = None
    pending_qty: Optional[float] = None
    receipt_status: Optional[str] = None

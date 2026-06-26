"""DTOs for the supplier portal surface (dashboard summary + PO list)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from .asn import AsnSummaryOut


class PortalSummary(BaseModel):
    supplier_name: Optional[str] = None
    total_pos: int
    pending_pos: int
    completed_pos: int
    blocked_count: int
    asn: AsnSummaryOut


class PortalPo(BaseModel):
    supplier_po_no: str
    crm_no: Optional[str] = None
    material_count: int
    overall_signal: Optional[str] = None
    po_status: Optional[str] = None
    earliest_shipment_date: Optional[datetime] = None
    completed: bool
    asn_count: int
    message_count: int = 0
    # True when a buyer has escalated this PO (manual or rule-based).
    escalated: bool = False


class PortalMessage(BaseModel):
    id: int
    direction: str            # INCOMING (from supplier) / OUTGOING (from buyer)
    mine: bool                # True if this supplier authored it (chat alignment)
    author: str
    subject: Optional[str] = None
    body: str
    mail_type: Optional[str] = None
    status: str
    at: Optional[datetime] = None


class PortalMessageCreate(BaseModel):
    body: str = Field(min_length=1)
    subject: Optional[str] = None


class PortalPoMaterial(BaseModel):
    procurement_record_id: int
    crm_no: str
    material_name: str
    uom: Optional[str] = None
    qty: Optional[float] = None
    po_date: Optional[datetime] = None
    shipment_date: Optional[datetime] = None
    signal: Optional[str] = None
    po_status: Optional[str] = None
    # Current supplier commitment (if any) for this material.
    commitment_date: Optional[datetime] = None
    commitment_qty: Optional[float] = None
    commitment_status: Optional[str] = None
    commitment_remark: Optional[str] = None


class PortalCommitmentItem(BaseModel):
    procurement_record_id: int
    commitment_date: Optional[str] = None      # YYYY-MM-DD
    commitment_qty: Optional[float] = None
    supplier_status: Optional[str] = None       # CONFIRMED / DELAYED / PARTIAL / …
    supplier_remark: Optional[str] = None


class PortalCommitmentSubmit(BaseModel):
    items: list[PortalCommitmentItem] = Field(default_factory=list)


class PortalPoListResponse(BaseModel):
    count: int
    items: list[PortalPo] = Field(default_factory=list)

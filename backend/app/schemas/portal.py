"""DTOs for the supplier portal surface (dashboard summary + PO list)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from .asn import AsnSummaryOut
from .attachment import AttachmentOut


class PortalSummary(BaseModel):
    supplier_name: Optional[str] = None
    total_pos: int
    pending_pos: int
    completed_pos: int
    blocked_count: int
    asn: AsnSummaryOut


class PortalPo(BaseModel):
    supplier_po_no: str
    # PO document reference from the CRM (PoShortRefTrnNo) — the number the
    # supplier knows from their PO document. Shown as the primary number.
    po_ref: Optional[str] = None
    crm_no: Optional[str] = None
    material_count: int
    overall_signal: Optional[str] = None
    po_status: Optional[str] = None
    earliest_shipment_date: Optional[datetime] = None
    completed: bool
    asn_count: int
    message_count: int = 0
    # Unread buyer messages (OUTGOING, not yet read by the supplier) on this PO.
    unread_inbound: int = 0
    # True when a buyer has escalated this PO (manual or rule-based).
    escalated: bool = False
    # CRM PO transaction number — drives the official PO PDF download.
    po_trn_no: Optional[str] = None


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
    attachments: list[AttachmentOut] = Field(default_factory=list)


class PortalMessageCreate(BaseModel):
    body: str = Field(min_length=1)
    subject: Optional[str] = None
    # Ids returned by the scoped /attachments/upload endpoint, bound on send.
    attachment_ids: list[int] = Field(default_factory=list)


class PortalEscalateIn(BaseModel):
    # Optional free-text reason shown to the buyer team on the task + notification.
    reason: Optional[str] = Field(default=None, max_length=500)


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


class PortalTask(BaseModel):
    """Safe, read-only view of an internal task for the supplier's PO."""
    id: int
    title: str
    description: Optional[str] = None
    material_name: Optional[str] = None
    status: str
    priority: str
    signal: Optional[str] = None
    progress_percent: int = 0
    due_date: Optional[datetime] = None
    created_at: datetime
    closed_at: Optional[datetime] = None


class PortalPoListResponse(BaseModel):
    count: int
    items: list[PortalPo] = Field(default_factory=list)

from typing import Optional
from pydantic import BaseModel, EmailStr, Field


class MailDraftRequest(BaseModel):
    procurement_record_id: int


class MailDraftOut(BaseModel):
    history_id: int
    procurement_record_id: int
    to_emails: list[EmailStr] = Field(default_factory=list)
    cc_emails: list[EmailStr] = Field(default_factory=list)
    bcc_emails: list[EmailStr] = Field(default_factory=list)
    escalation_emails: list[EmailStr] = Field(default_factory=list)
    subject: str
    body: str
    mail_type: str
    ai_required: bool
    notes: Optional[str] = None


class MailDraftPoRequest(BaseModel):
    supplier_name: str
    supplier_po_no: str
    mail_type: Optional[str] = None  # override, otherwise derived from highest signal
    force_new: bool = False  # ignore today's existing draft and create fresh


class MailDraftPoOut(BaseModel):
    history_id: int
    procurement_record_id: int  # anchor record for legacy compatibility
    supplier_name: Optional[str] = None
    supplier_po_no: str
    to_emails: list[EmailStr] = Field(default_factory=list)
    cc_emails: list[EmailStr] = Field(default_factory=list)
    bcc_emails: list[EmailStr] = Field(default_factory=list)
    escalation_emails: list[EmailStr] = Field(default_factory=list)
    subject: str
    body: str  # plain text fallback
    body_html: str  # rich HTML with materials table
    mail_type: str
    overall_signal: str
    material_count: int
    materials: list[dict] = Field(default_factory=list)
    reused_existing: bool = False
    notes: Optional[str] = None


class OutlookComposeRequest(BaseModel):
    history_id: int
    procurement_record_id: int
    supplier_po_no: Optional[str] = None
    to_emails: list[EmailStr] = Field(default_factory=list)
    cc_emails: list[EmailStr] = Field(default_factory=list)
    bcc_emails: list[EmailStr] = Field(default_factory=list)
    escalation_emails: list[EmailStr] = Field(default_factory=list)
    subject: str
    body: str
    body_html: Optional[str] = None


class OutlookComposeOut(BaseModel):
    ok: bool = True
    message: str

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class MailHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    procurement_record_id: int
    supplier_id: Optional[int] = None
    supplier_name: Optional[str] = None
    supplier_po_no: str
    material_name: str
    to_emails: list[EmailStr] = Field(default_factory=list)
    cc_emails: list[EmailStr] = Field(default_factory=list)
    bcc_emails: list[EmailStr] = Field(default_factory=list)
    escalation_emails: list[EmailStr] = Field(default_factory=list)
    subject: str
    body: str
    mail_type: str
    sent_status: str
    created_at: datetime
    sent_at: Optional[datetime] = None
    remarks: Optional[str] = None


class MailHistoryStatusUpdate(BaseModel):
    sent_status: str
    remarks: Optional[str] = None

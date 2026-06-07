from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class SupplierEmailBase(BaseModel):
    supplier_id: int
    supplier_name: Optional[str] = None
    to_emails: list[EmailStr] = Field(default_factory=list)
    cc_emails: list[EmailStr] = Field(default_factory=list)
    bcc_emails: list[EmailStr] = Field(default_factory=list)
    escalation_emails: list[EmailStr] = Field(default_factory=list)
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    remarks: Optional[str] = None
    is_active: bool = True


class SupplierEmailCreate(SupplierEmailBase):
    pass


class SupplierEmailUpdate(BaseModel):
    supplier_id: Optional[int] = None
    supplier_name: Optional[str] = None
    to_emails: Optional[list[EmailStr]] = None
    cc_emails: Optional[list[EmailStr]] = None
    bcc_emails: Optional[list[EmailStr]] = None
    escalation_emails: Optional[list[EmailStr]] = None
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    remarks: Optional[str] = None
    is_active: Optional[bool] = None


class SupplierEmailOut(SupplierEmailBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    updated_at: datetime

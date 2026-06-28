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


class CreatedLogin(BaseModel):
    email: str
    temp_password: str


class LoginConflict(BaseModel):
    email: str
    reason: str


class LoginProvisioningSummary(BaseModel):
    """Result of reconciling supplier logins with the mapping's TO emails."""
    created: list[CreatedLogin] = Field(default_factory=list)
    reactivated: list[str] = Field(default_factory=list)
    deactivated: list[str] = Field(default_factory=list)
    conflicts: list[LoginConflict] = Field(default_factory=list)
    emailed: list[str] = Field(default_factory=list)


class SupplierEmailOut(SupplierEmailBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    updated_at: datetime
    # Populated on create/update responses; None when simply listing mappings.
    provisioning: Optional[LoginProvisioningSummary] = None


class SupplierEmailAuditOut(BaseModel):
    """One change-log entry for a supplier email mapping (admin-only view)."""
    model_config = ConfigDict(from_attributes=True)
    id: int
    supplier_email_id: Optional[int] = None
    supplier_id: Optional[int] = None
    supplier_name: Optional[str] = None
    action: str
    changed_by_id: Optional[int] = None
    changed_by: Optional[str] = None
    changes: Optional[dict] = None
    created_at: datetime


class SupplierLoginOut(BaseModel):
    """A supplier portal login account (subset of User) for admin review."""
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: EmailStr
    supplier_id: Optional[int] = None
    is_active: bool
    must_change_password: bool
    last_login_at: Optional[datetime] = None
    created_at: datetime

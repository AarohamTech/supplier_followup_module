from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class SupplierUpdate(BaseModel):
    supplier_name: Optional[str] = None
    is_active: Optional[bool] = None


class SupplierOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    supplier_name: str
    latest_supplier_po_no: Optional[str] = None
    latest_signal: Optional[str] = None
    is_active: bool
    email_mapped: bool = False
    primary_email: Optional[str] = None
    created_at: datetime
    updated_at: datetime

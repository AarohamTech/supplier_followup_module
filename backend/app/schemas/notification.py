"""DTOs for in-app notifications."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    type: str
    title: str
    body: Optional[str] = None
    link: Optional[str] = None
    supplier_id: Optional[int] = None
    supplier_po_no: Optional[str] = None
    is_read: bool
    created_at: datetime

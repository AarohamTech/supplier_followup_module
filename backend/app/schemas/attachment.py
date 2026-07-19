"""DTO for user-uploaded message attachments (chat / communication hub)."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class AttachmentOut(BaseModel):
    id: int
    filename: str
    content_type: Optional[str] = None
    size_bytes: int = 0

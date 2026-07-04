"""Public-facing company branding DTO (login picker + active-company theme)."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class CompanyBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    display_name: str
    theme: str
    brand_name: str
    logo_url: str | None = None

"""Per-company CRM feed configuration.

The default company (102) uses the legacy `CRM_*` settings. Other companies read
`CRM_<CODE>_*` env vars, so CRM passwords never live in the database. A company
whose config is incomplete (missing desk id / credentials / base url) yields None
and is skipped by ingestion until its creds are added.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from ..core.config import settings


@dataclass(frozen=True)
class CrmConfig:
    base_url: str
    desk_id: str
    login_email: str
    login_password: str
    device_id: str


def _env(code: str, name: str) -> str:
    return (os.environ.get(f"CRM_{code}_{name}") or "").strip()


def get_crm_config(code: str, *, is_default: bool) -> CrmConfig | None:
    if is_default:
        desk = str(settings.CRM_DESK_ID or "").strip()
        email = (settings.CRM_LOGIN_EMAIL or "").strip()
        password = (settings.CRM_LOGIN_PASSWORD or "").strip()
        device = (settings.CRM_DEVICE_ID or "").strip() or desk
        base = (settings.CRM_API_BASE_URL or "").rstrip("/")
    else:
        desk = _env(code, "DESK_ID")
        email = _env(code, "LOGIN_EMAIL")
        password = _env(code, "LOGIN_PASSWORD")
        device = _env(code, "DEVICE_ID") or desk
        base = (_env(code, "BASE_URL") or settings.CRM_API_BASE_URL or "").rstrip("/")
    if not (desk and email and password and base):
        return None
    return CrmConfig(
        base_url=base, desk_id=desk, login_email=email,
        login_password=password, device_id=device,
    )

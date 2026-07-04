"""Per-company CRM feed configuration.

The default company (102) uses the legacy `CRM_*` settings. Other companies read
`CRM_<CODE>_*` env vars, so CRM passwords never live in the database. Because the
CRM is one account with per-desk feeds, a non-default company reuses the SHARED
login/token by default (same credentials, same base url) and only needs its own
`CRM_<CODE>_DESK_ID` — the request just sends a different desk. `CRM_<CODE>_LOGIN_EMAIL`
/`_LOGIN_PASSWORD`/`_BASE_URL` are optional overrides for a company that ever needs a
distinct CRM account. A company with no desk id (and no resolvable login) yields None
and is skipped by ingestion.
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
        # Non-default companies reuse the shared CRM login/token (same account,
        # different desk) unless they explicitly override it.
        email = _env(code, "LOGIN_EMAIL") or (settings.CRM_LOGIN_EMAIL or "").strip()
        password = _env(code, "LOGIN_PASSWORD") or (settings.CRM_LOGIN_PASSWORD or "").strip()
        device = _env(code, "DEVICE_ID") or desk
        base = (_env(code, "BASE_URL") or settings.CRM_API_BASE_URL or "").rstrip("/")
    if not (desk and email and password and base):
        return None
    return CrmConfig(
        base_url=base, desk_id=desk, login_email=email,
        login_password=password, device_id=device,
    )

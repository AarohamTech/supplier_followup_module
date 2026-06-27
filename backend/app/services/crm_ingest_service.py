"""Live PO ingestion from the Hariom CRM.

Polls the CRM "pending desk" feed on a schedule and upserts generated POs into
``procurement_records`` via the shared :mod:`procurement_sync_service`. The CRM
bearer token is short-lived, so we log in once and auto-refresh it before expiry.

Design notes:
- The login response shape is not contractually fixed, so the token is extracted
  defensively: known field names first, then a recursive scan for a JWT-looking
  string. The response keys are logged once to ease future debugging.
- Failure-safe: any network/auth/parse error raises (the caller logs it) and the
  existing data is never wiped — a bad cycle is simply skipped.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any

import requests
from jose import jwt as jose_jwt
from sqlalchemy.orm import Session

from ..core.config import settings
from ..database import SessionLocal
from ..models.crm_ingest_log import CrmIngestLog
from ..schemas.procurement import ProcurementSyncSummary
from .procurement_sync_service import sync_procurement_rows

log = logging.getLogger(__name__)

# Refresh the token this many seconds before its real expiry.
_TOKEN_LEEWAY_SECONDS = 300

_lock = threading.Lock()
_token_cache: dict[str, Any] = {"token": None, "exp": 0.0}
_login_keys_logged = False


# ── token handling ────────────────────────────────────────────────────────
def _find_jwt(obj: Any) -> str | None:
    """Recursively locate a JWT-looking string in an arbitrary JSON structure."""
    if isinstance(obj, str):
        s = obj.strip().strip('"')
        return s if s.startswith("eyJ") and s.count(".") >= 2 else None
    if isinstance(obj, dict):
        for v in obj.values():
            found = _find_jwt(v)
            if found:
                return found
    if isinstance(obj, list):
        for v in obj:
            found = _find_jwt(v)
            if found:
                return found
    return None


def _extract_token(data: Any) -> str | None:
    if isinstance(data, str):
        s = data.strip().strip('"')
        return s or None
    if isinstance(data, dict):
        for key in (
            "token", "Token", "accessToken", "access_token", "AccessToken",
            "jwt", "Jwt", "JWT", "authToken", "bearer",
        ):
            v = data.get(key)
            if isinstance(v, str) and v:
                return v
    return _find_jwt(data)


def _token_exp(token: str) -> float:
    """Best-effort unverified `exp` (epoch seconds); 0 if undecodable."""
    try:
        claims = jose_jwt.get_unverified_claims(token)
        return float(claims.get("exp") or 0.0)
    except Exception:  # noqa: BLE001
        return 0.0


def _login() -> str:
    global _login_keys_logged
    base = settings.CRM_API_BASE_URL.rstrip("/")
    body = {
        "Email": settings.CRM_LOGIN_EMAIL,
        "Password": settings.CRM_LOGIN_PASSWORD,
        "DeviceId": settings.CRM_DEVICE_ID,
    }
    resp = requests.post(
        f"{base}/api/login",
        json=body,
        timeout=settings.CRM_HTTP_TIMEOUT_SECONDS,
        headers={"Accept": "application/json"},
    )
    resp.raise_for_status()
    try:
        data = resp.json()
    except ValueError:
        data = resp.text
    if not _login_keys_logged:
        shape = list(data.keys()) if isinstance(data, dict) else type(data).__name__
        log.info("[crm] login response shape: %s", shape)
        _login_keys_logged = True
    token = _extract_token(data)
    if not token:
        raise RuntimeError("CRM login succeeded but no token found in the response")
    return token


def get_token(*, force_refresh: bool = False) -> str:
    """Return a valid bearer token, logging in / refreshing as needed."""
    with _lock:
        now = time.time()
        cached = _token_cache["token"]
        exp = _token_cache["exp"]
        fresh_enough = cached and (exp == 0.0 or now < exp - _TOKEN_LEEWAY_SECONDS)
        if cached and fresh_enough and not force_refresh:
            return cached
        token = _login()
        _token_cache["token"] = token
        _token_cache["exp"] = _token_exp(token)
        return token


# ── fetch + map ─────────────────────────────────────────────────────────────
def fetch_desk(desk_id: str | None = None) -> list[dict[str, Any]]:
    desk = str(desk_id or settings.CRM_DESK_ID)
    base = settings.CRM_API_BASE_URL.rstrip("/")
    url = f"{base}/api/crm/GetPendingUserDesk/{desk}"

    def _call(token: str) -> requests.Response:
        return requests.get(
            url,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=settings.CRM_HTTP_TIMEOUT_SECONDS,
        )

    resp = _call(get_token())
    if resp.status_code == 401:  # token rejected — force a fresh login and retry once
        resp = _call(get_token(force_refresh=True))
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, list):
        raise RuntimeError(f"CRM desk feed returned {type(data).__name__}, expected a list")
    return data


def _emp_code(value: Any) -> str | None:
    if value in (None, "", 0, "0"):
        return None
    return str(value).strip() or None


def _is_generated(row: dict[str, Any]) -> bool:
    """Only generated POs: an APPROVED status with a real vendor (PoLongName)."""
    status = str(row.get("PoStatus") or "").strip().upper()
    vendor = str(row.get("PoLongName") or "").strip()
    return status == "APPROVED" and bool(vendor)


def map_row(row: dict[str, Any]) -> dict[str, Any]:
    """CRM record → a dict keyed for procurement_sync_service.normalize_procurement_row."""
    return {
        "crm_no": row.get("CRMNo"),
        "supplier_po_no": row.get("PoNo"),
        "material_name": row.get("MaterialName"),
        "uom": row.get("MaterialUom"),
        "qty": row.get("Quantity"),
        "quantity": row.get("PoQuantity"),
        "rate": row.get("Rate"),
        "stock": row.get("Stock"),
        "signal": row.get("Signal"),
        "po_status": row.get("PoStatus"),
        "adv_status": row.get("AdvanceStatus"),
        "supplier_name": row.get("PoLongName"),
        "supplier_date": row.get("PoRefTrnDate"),
        "shipment_date": row.get("ShipmentDate"),
        "lead_time": row.get("LeadTime"),
        "owner_emp_code": _emp_code(row.get("EmpCode")),
    }


# ── orchestration ─────────────────────────────────────────────────────────────
def _log_run(**fields: Any) -> None:
    """Persist one CRM fetch-history row (own session so it survives failures)."""
    session = SessionLocal()
    try:
        session.add(CrmIngestLog(**fields))
        session.commit()
    except Exception:  # noqa: BLE001
        session.rollback()
        log.exception("[crm] failed to write ingest log")
    finally:
        session.close()


def poll_and_ingest(db: Session, trigger: str = "auto") -> dict[str, Any]:
    """Fetch the desk feed, keep generated POs, and upsert them. Failure-safe.

    Records a CRM fetch-history row each run (admin-visible) with added/changed
    counts. On error the existing data is left untouched and an ERROR row logged.
    """
    if not settings.CRM_INGEST_ENABLED:
        _log_run(status="DISABLED", trigger=trigger, message="CRM_INGEST_ENABLED is false")
        return {"ok": True, "status": "DISABLED", "message": "CRM_INGEST_ENABLED is false"}

    t0 = time.time()
    try:
        feed = fetch_desk()
        generated = [r for r in feed if _is_generated(r)]
        rows = [map_row(r) for r in generated]
        summary: ProcurementSyncSummary = sync_procurement_rows(db, rows, source="crm")
    except Exception as exc:  # noqa: BLE001
        _log_run(
            status="ERROR", trigger=trigger, desk=str(settings.CRM_DESK_ID),
            duration_ms=int((time.time() - t0) * 1000), message=str(exc)[:1000],
        )
        raise

    duration_ms = int((time.time() - t0) * 1000)
    _log_run(
        status="OK", trigger=trigger, desk=str(settings.CRM_DESK_ID),
        fetched=len(feed), generated=len(generated),
        created=summary.created_count, updated=summary.updated_count,
        skipped=summary.skipped_count, errors=summary.error_count,
        duration_ms=duration_ms,
    )

    result = {
        "ok": True,
        "status": "OK",
        "desk": str(settings.CRM_DESK_ID),
        "fetched": len(feed),
        "generated": len(generated),
        "created": summary.created_count,
        "updated": summary.updated_count,
        "skipped": summary.skipped_count,
        "errors": summary.error_count,
        "duration_ms": duration_ms,
        "records_processed": len(rows),
        "records_success": summary.created_count + summary.updated_count,
        "records_failed": summary.error_count,
    }
    log.info(
        "[crm] ingest desk=%s fetched=%d generated=%d created=%d updated=%d skipped=%d errors=%d",
        result["desk"], result["fetched"], result["generated"],
        result["created"], result["updated"], result["skipped"], result["errors"],
    )
    return result

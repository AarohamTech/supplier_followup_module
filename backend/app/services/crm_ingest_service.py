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
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.config import settings
from ..database import SessionLocal
from ..models.crm_ingest_log import CrmIngestLog
from ..models.procurement import ProcurementRecord
from ..models.supplier import SupplierMaster
from ..schemas.procurement import ProcurementCreate
from .followup_engine import apply_followup_logic
from .procurement_sync_service import UPDATABLE_FROM_SOURCE, normalize_procurement_row

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


def _bulk_upsert(db: Session, raw_rows: list[dict[str, Any]]) -> tuple[int, int, int]:
    """Normalize + upsert CRM rows with minimal DB round-trips.

    The Supabase DB is in a different AWS region than this app, so per-row
    queries (one SELECT + write each) are far too slow at ~1k rows. Instead:
    normalize in memory, load all existing rows for these CRM numbers in ONE
    query, then add/update objects and commit once (SQLAlchemy batches the
    INSERTs/UPDATEs). Returns (created, updated, skipped).
    """
    by_key: dict[tuple, dict[str, Any]] = {}
    skipped = 0
    for raw in raw_rows:
        norm, errs = normalize_procurement_row(raw)
        if errs or norm is None:
            skipped += 1
            continue
        try:
            payload = ProcurementCreate(**norm).model_dump()
        except Exception:  # noqa: BLE001
            skipped += 1
            continue
        # Dedupe duplicate feed rows by business key (keep the latest).
        by_key[(payload["crm_no"], payload["supplier_po_no"], payload["material_name"])] = payload
    if not by_key:
        return 0, 0, skipped

    crm_nos = {k[0] for k in by_key}
    existing: dict[tuple, ProcurementRecord] = {}
    for r in db.scalars(
        select(ProcurementRecord).where(ProcurementRecord.crm_no.in_(crm_nos))
    ).all():
        existing[(r.crm_no, r.supplier_po_no, r.material_name)] = r

    created = updated = 0
    new_objs: list[ProcurementRecord] = []
    for key, payload in by_key.items():
        rec = existing.get(key)
        if rec is None:
            data = dict(payload)
            data["po_no"] = payload["supplier_po_no"]  # legacy NOT NULL column
            rec = ProcurementRecord(**data)
            apply_followup_logic(rec)
            new_objs.append(rec)
            created += 1
            continue
        changed = False
        for field in UPDATABLE_FROM_SOURCE:
            new_val = payload.get(field)
            if new_val is not None and getattr(rec, field) != new_val:
                setattr(rec, field, new_val)
                changed = True
        if rec.po_no != payload["supplier_po_no"]:
            rec.po_no = payload["supplier_po_no"]
            changed = True
        if changed:
            apply_followup_logic(rec)
            updated += 1
    if new_objs:
        db.add_all(new_objs)

    # Ensure supplier_master rows exist (one query + bulk add of the missing).
    names = {p["supplier_name"] for p in by_key.values() if p.get("supplier_name")}
    if names:
        have = set(
            db.scalars(
                select(SupplierMaster.supplier_name).where(SupplierMaster.supplier_name.in_(names))
            ).all()
        )
        for name in names - have:
            db.add(SupplierMaster(supplier_name=name, is_active=True))

    db.commit()
    return created, updated, skipped


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
        created, updated, skipped = _bulk_upsert(db, rows)
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
        created=created, updated=updated, skipped=skipped, errors=0,
        duration_ms=duration_ms,
    )

    result = {
        "ok": True,
        "status": "OK",
        "desk": str(settings.CRM_DESK_ID),
        "fetched": len(feed),
        "generated": len(generated),
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "errors": 0,
        "duration_ms": duration_ms,
        "records_processed": created + updated + skipped,
        "records_success": created + updated,
        "records_failed": 0,
    }
    log.info(
        "[crm] ingest desk=%s fetched=%d generated=%d created=%d updated=%d skipped=%d errors=%d",
        result["desk"], result["fetched"], result["generated"],
        result["created"], result["updated"], result["skipped"], result["errors"],
    )
    return result

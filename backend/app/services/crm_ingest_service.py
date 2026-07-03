"""Live PO ingestion from the Hariom CRM.

Polls the CRM "pending desk" feed on a schedule and upserts generated POs into
``procurement_records``. The CRM bearer token is short-lived, so we log in once
and auto-refresh it before expiry.

Performance: the Supabase DB is in a different AWS region than this app, so
per-row writes are far too slow (~1s/row). Ingestion therefore uses a single
``INSERT ... ON CONFLICT DO UPDATE`` per chunk (server-side, idempotent), so a
run stays in the low seconds and concurrent runs can't collide on the unique key.
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Any

import requests
from jose import jwt as jose_jwt
from sqlalchemy import case, func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from ..core.config import settings
from ..database import SessionLocal
from ..models.crm_ingest_log import CrmIngestLog
from ..models.procurement import ProcurementRecord
from ..models.supplier import SupplierMaster
from ..schemas.procurement import ProcurementCreate
from .followup_engine import get_followup_rule
from .procurement_sync_service import normalize_procurement_row

log = logging.getLogger(__name__)

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
    if isinstance(data, dict):
        # Some endpoints wrap the array, e.g. {"success":..,"data":[...]}.
        for key in ("data", "Data", "result", "Result", "items", "Items"):
            if isinstance(data.get(key), list):
                return data[key]
    if not isinstance(data, list):
        raise RuntimeError(f"CRM desk feed returned {type(data).__name__}, expected a list")
    _log_row_keys(data)
    return data


_row_keys_logged = False


def _log_row_keys(data: list[dict[str, Any]]) -> None:
    """Log the desk-row field names once, so the real end-customer field names
    (see _CUSTOMER_*_KEYS) can be confirmed from the prod logs and pruned."""
    global _row_keys_logged
    if _row_keys_logged or not data or not isinstance(data[0], dict):
        return
    log.info("[crm] desk row keys: %s", sorted(data[0].keys()))
    _row_keys_logged = True


def _emp_code(value: Any) -> str | None:
    if value in (None, "", 0, "0"):
        return None
    return str(value).strip() or None


def _is_generated(row: dict[str, Any]) -> bool:
    """Only generated POs: an APPROVED status with a real vendor (PoLongName)."""
    status = str(row.get("PoStatus") or "").strip().upper()
    vendor = str(row.get("PoLongName") or "").strip()
    return status == "APPROVED" and bool(vendor)


# End-customer CRM field names vary by feed. We read the first present candidate
# so the mapping is robust; confirm the real names from the one-time
# "[crm] desk row keys" log on the prod box and prune this list to the exact key.
_CUSTOMER_NAME_KEYS = (
    "CustomerName", "CustName", "PartyName", "BuyerName", "Customer",
    "CustomerLongName", "PartyLongName",
)
_CUSTOMER_PO_KEYS = (
    "CustomerPoNo", "CustPoNo", "CustomerPONo", "PartyPoNo", "CustomerRefNo",
    "CustPoNumber", "CustomerOrderNo",
)
_CUSTOMER_PO_DATE_KEYS = (
    "CustomerPoDate", "CustPoDate", "PartyPoDate", "CustomerOrderDate", "PoDate",
)


def _first(row: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for k in keys:
        v = row.get(k)
        if v not in (None, ""):
            return v
    return None


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
        # PO owner = the procurement USER who handles it (CRM `UserId`), which
        # matches the employee master's EMPLOYEE_ID. NOT `EmpCode` (the indenter/
        # requester — a company-wide code that rarely maps to a portal user).
        "owner_emp_code": _emp_code(row.get("UserId")),
        # End-customer fields (candidate keys — see note above).
        "customer_name": _first(row, _CUSTOMER_NAME_KEYS),
        "customer_po_no": _first(row, _CUSTOMER_PO_KEYS),
        "po_date": _first(row, _CUSTOMER_PO_DATE_KEYS),
    }


# ── bulk upsert ───────────────────────────────────────────────────────────────
class _SignalShim:
    """Minimal stand-in for ProcurementRecord so get_followup_rule can read a
    signal (+ red_since) without an ORM object during bulk value building."""

    __slots__ = ("signal", "red_since")

    def __init__(self, signal: str | None):
        self.signal = signal
        self.red_since = datetime.utcnow() if (signal or "").upper() == "RED" else None


def _col_values(payload: dict[str, Any]) -> dict[str, Any]:
    """Build a column-keyed dict for INSERT (schema field `quantity` → column
    `supplier_quantity`), with insert-time follow-up fields computed."""
    sig = (payload.get("signal") or "").upper() or None
    rule = get_followup_rule(_SignalShim(sig))
    now = datetime.utcnow()
    return {
        "crm_no": payload["crm_no"],
        "material_name": payload["material_name"],
        "uom": payload.get("uom"),
        "lead_time": payload.get("lead_time"),
        "shipment_date": payload.get("shipment_date"),
        "signal": sig,
        "stock": payload.get("stock"),
        "qty": payload.get("qty"),
        "po_status": payload.get("po_status"),
        "adv_status": payload.get("adv_status"),
        "supplier_po_no": payload["supplier_po_no"],
        "supplier_date": payload.get("supplier_date"),
        "supplier_name": payload.get("supplier_name"),
        "supplier_quantity": payload.get("quantity"),
        "rate": payload.get("rate"),
        "owner_emp_code": payload.get("owner_emp_code"),
        # po_no is the CUSTOMER PO (falls back to the supplier PO when the feed
        # carries no customer PO, preserving the old not-null behaviour).
        "po_no": payload.get("customer_po_no") or payload["supplier_po_no"],
        "customer_name": payload.get("customer_name"),
        "po_date": payload.get("po_date"),
        "followup_status": rule.followup_status,
        "escalation_level": rule.escalation_level,
        "ai_required": rule.ai_required,
        "mail_status": "NOT_SENT",
        "followup_count": 0,
        # Due now so the first message (green release / yellow / red day-1) fires
        # as soon as the PO is ingested; later follow-ups are rescheduled by the
        # follow-up engine after each send.
        "next_followup_date": now,
        "red_since": now if sig == "RED" else None,
    }


_MISSING = object()
# Source fields that define whether a PO row has materially changed.
_HASH_FIELDS = (
    "signal", "po_status", "adv_status", "shipment_date", "qty", "rate", "stock",
    "supplier_name", "supplier_date", "lead_time", "uom", "owner_emp_code", "quantity",
    "customer_name", "customer_po_no", "po_date",
)


def _source_hash(payload: dict[str, Any]) -> str:
    sub = {k: payload.get(k) for k in _HASH_FIELDS}
    return hashlib.sha1(json.dumps(sub, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _bulk_upsert(db: Session, raw_rows: list[dict[str, Any]]) -> tuple[int, int, int]:
    """Normalize + bulk-upsert via INSERT ... ON CONFLICT DO UPDATE (one statement
    per chunk, server-side). Returns (created, updated, skipped)."""
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

    # The DB is cross-region; give bulk statements timeout headroom.
    try:
        db.execute(text("SET statement_timeout = '180s'"))
    except Exception:  # noqa: BLE001
        pass

    # Detect genuinely new / changed rows via a content hash (one key+hash query),
    # so unchanged POs are never re-written and the fetch history is accurate.
    crm_nos = {k[0] for k in by_key}
    existing_hash: dict[tuple, str | None] = {}
    for row in db.execute(
        select(
            ProcurementRecord.crm_no,
            ProcurementRecord.supplier_po_no,
            ProcurementRecord.material_name,
            ProcurementRecord.source_hash,
        ).where(ProcurementRecord.crm_no.in_(crm_nos))
    ).all():
        existing_hash[(row[0], row[1], row[2])] = row[3]

    created = updated = 0
    to_upsert: list[dict[str, Any]] = []
    for key, payload in by_key.items():
        h = _source_hash(payload)
        prior = existing_hash.get(key, _MISSING)
        if prior is _MISSING:
            created += 1
        elif prior != h:
            updated += 1
        else:
            continue  # unchanged — skip the write entirely
        row_values = _col_values(payload)
        row_values["source_hash"] = h
        to_upsert.append(row_values)

    tbl = ProcurementRecord.__table__
    batch = 500
    for i in range(0, len(to_upsert), batch):
        part = to_upsert[i : i + batch]
        stmt = pg_insert(tbl).values(part)
        sig = stmt.excluded.signal
        stmt = stmt.on_conflict_do_update(
            constraint="uq_procurement_match_latest",
            set_={
                "uom": stmt.excluded.uom,
                "lead_time": stmt.excluded.lead_time,
                "shipment_date": stmt.excluded.shipment_date,
                "signal": stmt.excluded.signal,
                "stock": stmt.excluded.stock,
                "qty": stmt.excluded.qty,
                "po_status": stmt.excluded.po_status,
                "adv_status": stmt.excluded.adv_status,
                "supplier_date": stmt.excluded.supplier_date,
                "supplier_name": stmt.excluded.supplier_name,
                "supplier_quantity": stmt.excluded.supplier_quantity,
                "rate": stmt.excluded.rate,
                "owner_emp_code": stmt.excluded.owner_emp_code,
                "po_no": stmt.excluded.po_no,
                "customer_name": stmt.excluded.customer_name,
                "po_date": stmt.excluded.po_date,
                "source_hash": stmt.excluded.source_hash,
                "followup_status": case(
                    (sig == "GREEN", "PENDING_ACK"),
                    (sig == "YELLOW", "REMINDER_DUE"),
                    (sig == "RED", "URGENT_FOLLOWUP"),
                    (sig == "BLACK", "CRITICAL_ESCALATION"),
                    else_="PENDING",
                ),
                "escalation_level": case(
                    (sig == "RED", "LEVEL_1"),
                    (sig == "BLACK", "CRITICAL"),
                    else_="NONE",
                ),
                "ai_required": case((sig == "BLACK", True), else_=False),
                "red_since": case(
                    (sig == "RED", func.coalesce(tbl.c.red_since, func.now())),
                    else_=None,
                ),
                # On a signal-tier change, become due now so the new-tier message
                # (e.g. yellow → red day-1) fires immediately; otherwise keep the
                # existing schedule so unchanged POs aren't re-chased.
                "next_followup_date": case(
                    (sig != tbl.c.signal, func.now()),
                    else_=tbl.c.next_followup_date,
                ),
                "updated_at": func.now(),
            },
        )
        db.execute(stmt)

    # Ensure supplier_master rows exist (one query + one bulk insert of missing).
    names = {p["supplier_name"] for p in by_key.values() if p.get("supplier_name")}
    if names:
        have = set(
            db.scalars(
                select(SupplierMaster.supplier_name).where(SupplierMaster.supplier_name.in_(names))
            ).all()
        )
        missing = [{"supplier_name": n, "is_active": True} for n in (names - have)]
        if missing:
            db.execute(
                pg_insert(SupplierMaster.__table__)
                .values(missing)
                .on_conflict_do_nothing(index_elements=["supplier_name"])
            )

    db.commit()
    return created, updated, skipped


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


def _auto_send_after_ingest(db: Session) -> None:
    """Queue the green/yellow/red follow-ups now due and send the ready ones.

    Best-effort: any failure here is logged and swallowed so it never affects the
    ingest result. The queue step self-guards on ``AUTO_PO_FOLLOWUP_ENABLED`` and
    skips POs with no active email mapping, so it is safe to call unconditionally.
    """
    # Lazy imports avoid any import-time cycle between ingest / mail services.
    from .po_followup_mail_service import queue_due_po_followups
    from ..workers.mail_send_worker import send_ready_messages

    try:
        queue_due_po_followups(db)
    except Exception:  # noqa: BLE001
        log.exception("[crm] auto follow-up queue failed (ignored)")
    if getattr(settings, "SMTP_ENABLED", False):
        try:
            send_ready_messages()
        except Exception:  # noqa: BLE001
            log.exception("[crm] auto follow-up send failed (ignored)")


def poll_and_ingest(db: Session, trigger: str = "auto") -> dict[str, Any]:
    """Fetch the desk feed, keep generated POs, and bulk-upsert them. Failure-safe.

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
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
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

    # Contact suppliers as soon as their data lands: queue + send the signal-based
    # follow-ups for the POs that just changed, rather than waiting for the
    # separate follow-up cron. Best-effort — never breaks the ingest.
    if created or updated:
        _auto_send_after_ingest(db)

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
        "[crm] ingest desk=%s fetched=%d generated=%d created=%d updated=%d skipped=%d in %dms",
        result["desk"], result["fetched"], result["generated"],
        result["created"], result["updated"], result["skipped"], duration_ms,
    )
    return result

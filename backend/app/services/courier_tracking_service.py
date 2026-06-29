"""Courier tracking: poll the self-hosted indian-courier-api for in-transit ASNs
and append new, geocoded checkpoints to the ASN timeline.

Design constraints:
- Entirely gated by `settings.COURIER_API_ENABLED`.
- Fully fail-safe: any network/parse/db error is swallowed per-ASN; the poller
  never raises and never blocks the ASN flow.
- Never regresses the lifecycle stage; only advances on clear signals and never
  auto-flips to DELIVERED on ambiguous text.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import requests
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..core.config import settings
from ..data.india_city_coords import geocode
from ..models.asn import Asn
from . import asn_service
from .asn_service import STAGE_ORDER

log = logging.getLogger(__name__)

# Provider slugs the indian-courier-api supports (working set).
SUPPORTED_COURIERS = ("delhivery", "bluedart", "ekart", "dtdc", "ecom", "dhl")

_DATE_FORMATS = (
    "%d %b, %Y %H:%M hrs",
    "%d %b %Y %H:%M",
    "%d-%m-%Y %H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M",
)


def _map_stage(detail: str) -> str | None:
    """Map a free-text checkpoint to a lifecycle stage, or None if unclear."""
    d = (detail or "").lower()
    if "out for delivery" in d:
        return "OUT_FOR_DELIVERY"
    if "deliver" in d and "undeliver" not in d:
        return "DELIVERED"
    if "customs" in d:
        return "AT_CUSTOMS"
    if "out for" not in d and ("hub" in d or "facility" in d or "received at" in d or "arrived" in d):
        return "INBOUND_HUB"
    if any(w in d for w in ("in transit", "in-transit", "dispatched", "departed", "shipped", "picked")):
        return "IN_TRANSIT"
    return None


def _forward_stage(mapped: str | None, current: str) -> str:
    """Never regress: return the later of mapped vs current (by STAGE_ORDER)."""
    order = list(STAGE_ORDER)
    ci = order.index(current) if current in order else 0
    if not mapped or mapped not in order:
        return current if current in order else "IN_TRANSIT"
    mi = order.index(mapped)
    return mapped if mi >= ci else current


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _fetch(courier: str, tracking_no: str) -> list[dict[str, Any]]:
    base = settings.COURIER_API_BASE_URL.rstrip("/")
    resp = requests.get(
        f"{base}/api/track/{courier}/{tracking_no}",
        timeout=settings.COURIER_HTTP_TIMEOUT_SECONDS,
        headers={"Accept": "application/json"},
    )
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, list):
        return [c for c in data if isinstance(c, dict)]
    if isinstance(data, dict):
        for key in ("checkpoints", "scans", "events", "history", "data"):
            v = data.get(key)
            if isinstance(v, list):
                return [c for c in v if isinstance(c, dict)]
    return []


def _checkpoint(c: dict) -> tuple[str | None, str | None, datetime | None]:
    location = c.get("location") or c.get("city") or c.get("place")
    detail = c.get("detail") or c.get("status") or c.get("activity") or c.get("description")
    when = _parse_date(c.get("date") or c.get("time") or c.get("timestamp"))
    return (
        str(location).strip() if location else None,
        str(detail).strip() if detail else None,
        when,
    )


def poll_in_transit(db: Session) -> dict[str, Any]:
    """Fetch + append new checkpoints for every trackable in-transit ASN."""
    if not settings.COURIER_API_ENABLED:
        return {"enabled": False, "polled": 0, "updated": 0, "errors": 0}

    asns = list(
        db.scalars(
            select(Asn)
            .options(selectinload(Asn.events))
            .where(
                Asn.tracking_no.isnot(None),
                Asn.courier_code.isnot(None),
                Asn.status.notin_(("DELIVERED", "CANCELLED", "DRAFT")),
            )
        ).all()
    )

    polled = updated = errors = 0
    for asn in asns:
        courier = (asn.courier_code or "").strip().lower()
        tracking_no = (asn.tracking_no or "").strip()
        if courier not in SUPPORTED_COURIERS or not tracking_no:
            continue
        polled += 1
        try:
            checkpoints = _fetch(courier, tracking_no)
        except Exception:  # noqa: BLE001
            errors += 1
            log.warning("courier fetch failed asn=%s courier=%s", asn.asn_no, courier, exc_info=True)
            continue

        seen = {
            (e.occurred_at, (e.location or "").lower(), (e.note or "")[:80])
            for e in asn.events
            if e.source == "COURIER_API"
        }
        parsed = []
        for c in checkpoints:
            loc, detail, when = _checkpoint(c)
            if not (loc or detail):
                continue
            parsed.append((when or datetime.utcnow(), loc, detail))
        parsed.sort(key=lambda x: x[0])

        for when, loc, detail in parsed:
            key = (when, (loc or "").lower(), (detail or "")[:80])
            if key in seen:
                continue
            seen.add(key)
            coords = geocode(loc)
            stage = _forward_stage(_map_stage(detail or ""), asn.status)
            try:
                asn_service.add_event(
                    db,
                    asn,
                    stage=stage,
                    location=loc,
                    note=detail,
                    occurred_at=when,
                    created_by="courier-api",
                    lat=coords[0] if coords else None,
                    lng=coords[1] if coords else None,
                    source="COURIER_API",
                )
                updated += 1
            except Exception:  # noqa: BLE001
                db.rollback()
                errors += 1
                log.warning("courier add_event failed asn=%s", asn.asn_no, exc_info=True)

    return {"enabled": True, "polled": polled, "updated": updated, "errors": errors}

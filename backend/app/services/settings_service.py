"""Runtime-editable scheduler & follow-up interval settings.

Stored in ``app_settings`` under two keys:

* ``scheduler_intervals`` – cron job intervals (minutes).
* ``followup_intervals`` – per-``followup_status`` interval (hours) used
  by ``followup_engine.apply_followup_logic`` to compute ``next_followup_date``.

Defaults fall back to ``settings`` (env vars) when no row is present.
"""
from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from ..core.config import settings as env_settings
from ..models.app_setting import AppSetting

SCHEDULER_INTERVALS_KEY = "scheduler_intervals"
FOLLOWUP_INTERVALS_KEY = "followup_intervals"

# Canonical list of cron job interval keys (minutes).
SCHEDULER_FIELDS = (
    "MAIL_FETCH_INTERVAL_MINUTES",
    "STATUS_CHANGE_INTERVAL_MINUTES",
    "AUTO_REPLY_INTERVAL_MINUTES",
    "MAIL_SEND_INTERVAL_MINUTES",
)

# Canonical follow-up statuses with default interval hours.
DEFAULT_FOLLOWUP_INTERVALS_HOURS: dict[str, int] = {
    "PENDING_ACK": 48,
    "REMINDER_DUE": 24,
    "URGENT_FOLLOWUP": 12,
    "STRONG_FOLLOWUP": 8,
    "AI_FOLLOWUP": 6,
    "CRITICAL_ESCALATION": 4,
    "PENDING": 24,
}


def _get_raw(db: Session, key: str) -> dict[str, Any] | None:
    row = db.get(AppSetting, key)
    if row is None or not isinstance(row.value, dict):
        return None
    return row.value


def _set_raw(db: Session, key: str, value: dict[str, Any]) -> None:
    row = db.get(AppSetting, key)
    if row is None:
        row = AppSetting(key=key, value=value)
        db.add(row)
    else:
        row.value = value


def get_scheduler_intervals(db: Session) -> dict[str, int]:
    stored = _get_raw(db, SCHEDULER_INTERVALS_KEY) or {}
    out: dict[str, int] = {}
    for field in SCHEDULER_FIELDS:
        raw = stored.get(field)
        try:
            value = int(raw) if raw is not None else int(getattr(env_settings, field))
        except (TypeError, ValueError):
            value = int(getattr(env_settings, field))
        out[field] = max(1, value)
    return out


def set_scheduler_intervals(db: Session, values: dict[str, int]) -> dict[str, int]:
    sanitized: dict[str, int] = {}
    for field in SCHEDULER_FIELDS:
        if field in values and values[field] is not None:
            try:
                sanitized[field] = max(1, int(values[field]))
            except (TypeError, ValueError):
                continue
    if sanitized:
        existing = _get_raw(db, SCHEDULER_INTERVALS_KEY) or {}
        existing.update(sanitized)
        _set_raw(db, SCHEDULER_INTERVALS_KEY, existing)
        db.commit()
    return get_scheduler_intervals(db)


def get_followup_intervals(db: Session) -> dict[str, int]:
    stored = _get_raw(db, FOLLOWUP_INTERVALS_KEY) or {}
    out: dict[str, int] = dict(DEFAULT_FOLLOWUP_INTERVALS_HOURS)
    for status, hours in stored.items():
        try:
            out[str(status).upper()] = max(1, int(hours))
        except (TypeError, ValueError):
            continue
    return out


def set_followup_intervals(db: Session, values: dict[str, int]) -> dict[str, int]:
    sanitized: dict[str, int] = {}
    for status, hours in (values or {}).items():
        try:
            sanitized[str(status).upper()] = max(1, int(hours))
        except (TypeError, ValueError):
            continue
    if sanitized:
        existing = _get_raw(db, FOLLOWUP_INTERVALS_KEY) or {}
        existing.update(sanitized)
        _set_raw(db, FOLLOWUP_INTERVALS_KEY, existing)
        db.commit()
    return get_followup_intervals(db)


ADMIN_DIGEST_KEY = "admin_digest"

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

DEFAULT_ADMIN_DIGEST: dict[str, Any] = {
    "enabled": False,
    "recipients": [],
    "send_hour": 9,
    "timezone": "Asia/Kolkata",
    "sections": {
        "counts": True, "summary": True, "critical": True,
        "heated": True, "risk": True, "overdue": True,
    },
    "limits": {"critical": 10, "heated": 5, "risk": 10, "overdue": 15},
    "last_sent_date": None,
}


def _merge_admin_digest(stored: dict[str, Any]) -> dict[str, Any]:
    """Merge a stored config dict over defaults, returning a complete config."""
    return {
        "enabled": bool(stored.get("enabled", DEFAULT_ADMIN_DIGEST["enabled"])),
        "recipients": [e for e in stored.get("recipients", []) if isinstance(e, str)],
        "send_hour": _clamp_int(stored.get("send_hour"), DEFAULT_ADMIN_DIGEST["send_hour"], 0, 23),
        "timezone": str(stored.get("timezone") or DEFAULT_ADMIN_DIGEST["timezone"]),
        "sections": {**DEFAULT_ADMIN_DIGEST["sections"], **_bool_map(stored.get("sections"))},
        "limits": {**DEFAULT_ADMIN_DIGEST["limits"], **_int_map(stored.get("limits"), lo=1, hi=100)},
        "last_sent_date": stored.get("last_sent_date") or None,
    }


def get_admin_digest(db: Session) -> dict[str, Any]:
    return _merge_admin_digest(_get_raw(db, ADMIN_DIGEST_KEY) or {})


def set_admin_digest(db: Session, values: dict[str, Any]) -> dict[str, Any]:
    existing = _get_raw(db, ADMIN_DIGEST_KEY) or {}
    if "enabled" in values:
        existing["enabled"] = bool(values["enabled"])
    if "recipients" in values:
        existing["recipients"] = [
            e.strip() for e in values["recipients"]
            if isinstance(e, str) and _EMAIL_RE.match(e.strip())
        ]
    if "send_hour" in values:
        existing["send_hour"] = _clamp_int(values["send_hour"], DEFAULT_ADMIN_DIGEST["send_hour"], 0, 23)
    if "timezone" in values and values["timezone"]:
        existing["timezone"] = str(values["timezone"])
    if "sections" in values:
        existing["sections"] = {**existing.get("sections", {}), **_bool_map(values["sections"])}
    if "limits" in values:
        existing["limits"] = {**existing.get("limits", {}), **_int_map(values["limits"], lo=1, hi=100)}
    _set_raw(db, ADMIN_DIGEST_KEY, existing)
    db.commit()
    return _merge_admin_digest(existing)


def mark_admin_digest_sent(db: Session, day_iso: str) -> None:
    existing = _get_raw(db, ADMIN_DIGEST_KEY) or {}
    existing["last_sent_date"] = day_iso
    _set_raw(db, ADMIN_DIGEST_KEY, existing)
    db.commit()


def _clamp_int(raw: Any, default: int, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(raw)))
    except (TypeError, ValueError):
        return default


def _bool_map(raw: Any) -> dict[str, bool]:
    return {str(k): bool(v) for k, v in raw.items()} if isinstance(raw, dict) else {}


def _int_map(raw: Any, *, lo: int, hi: int) -> dict[str, int]:
    out: dict[str, int] = {}
    if isinstance(raw, dict):
        for k, v in raw.items():
            try:
                out[str(k)] = max(lo, min(hi, int(v)))
            except (TypeError, ValueError):
                continue
    return out

"""Runtime-editable scheduler & follow-up interval settings.

Stored in ``app_settings`` under two keys:

* ``scheduler_intervals`` – cron job intervals (minutes).
* ``followup_intervals`` – per-``followup_status`` interval (hours) used
  by ``followup_engine.apply_followup_logic`` to compute ``next_followup_date``.

Defaults fall back to ``settings`` (env vars) when no row is present.
"""
from __future__ import annotations

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

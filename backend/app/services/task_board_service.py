"""Configurable Task Manager board columns.

A board column IS a task status: a task sits in the column whose ``key`` equals
its ``status``. The seven built-in statuses always exist (the dashboards, the
ZanFlow bridge and the DONE / closed_at rules depend on them), but an admin may
rename, recolour, reorder or hide them. Admins may also add custom columns,
whose keys are minted here as ``C_<SLUG>`` so they can never collide with a
built-in.

Stored in ``app_settings`` under ``task_board_columns`` as ``{"columns": [...]}``.
"""
from __future__ import annotations

import re
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..models.app_setting import AppSetting
from ..models.communication_task import TASK_STATUSES, CommunicationTask

BOARD_COLUMNS_KEY = "task_board_columns"

# Tailwind dot classes the frontend knows how to render. Anything else falls
# back to slate so a hand-edited row can't inject arbitrary classes.
COLORS = ("slate", "blue", "amber", "violet", "cyan", "rose", "green", "orange", "pink", "teal", "indigo", "lime")

DEFAULT_COLUMNS: list[dict[str, Any]] = [
    {"key": "BACKLOG", "label": "Backlog", "color": "slate"},
    {"key": "TODO", "label": "To Do", "color": "blue"},
    {"key": "IN_PROGRESS", "label": "In Progress", "color": "amber"},
    {"key": "WAITING_SUPPLIER", "label": "Waiting Supplier", "color": "violet"},
    {"key": "WAITING_CUSTOMER", "label": "Waiting Customer", "color": "cyan"},
    {"key": "BLOCKED", "label": "Blocked", "color": "rose"},
    {"key": "DONE", "label": "Done", "color": "green"},
]

MAX_CUSTOM_COLUMNS = 12
_KEY_RE = re.compile(r"^[A-Z0-9_]{1,32}$")


def _default_by_key() -> dict[str, dict[str, Any]]:
    return {c["key"]: c for c in DEFAULT_COLUMNS}


def is_valid_key_shape(key: Any) -> bool:
    return isinstance(key, str) and bool(_KEY_RE.match(key))


def _mint_key(label: str, taken: set[str]) -> str:
    slug = re.sub(r"[^A-Z0-9]+", "_", label.upper()).strip("_")[:28] or "COLUMN"
    key = f"C_{slug}"[:32]
    n = 2
    while key in taken:
        suffix = f"_{n}"
        key = f"C_{slug}"[: 32 - len(suffix)] + suffix
        n += 1
    return key


def _clean(col: dict[str, Any], builtin: bool) -> dict[str, Any]:
    default = _default_by_key().get(col.get("key"), {})
    label = str(col.get("label") or default.get("label") or col.get("key") or "").strip()[:40]
    color = col.get("color") if col.get("color") in COLORS else (default.get("color") or "slate")
    return {
        "key": col["key"],
        "label": label or default.get("label") or col["key"],
        "color": color,
        # DONE can never be hidden: completing a task must stay possible.
        "hidden": bool(col.get("hidden")) and col["key"] != "DONE",
        "builtin": builtin,
    }


def _normalise(stored: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Stored order + every built-in exactly once (missing ones appended)."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for col in stored or []:
        key = col.get("key") if isinstance(col, dict) else None
        if not is_valid_key_shape(key) or key in seen:
            continue
        builtin = key in TASK_STATUSES
        if not builtin and not key.startswith("C_"):
            continue
        out.append(_clean(col, builtin))
        seen.add(key)
    for col in DEFAULT_COLUMNS:
        if col["key"] not in seen:
            out.append(_clean(col, True))
    return out


def get_columns(db: Session) -> list[dict[str, Any]]:
    row = db.get(AppSetting, BOARD_COLUMNS_KEY)
    stored = row.value.get("columns") if row is not None and isinstance(row.value, dict) else None
    return _normalise(stored)


def valid_status_keys(db: Session) -> tuple[str, ...]:
    return tuple(c["key"] for c in get_columns(db))


def set_columns(db: Session, columns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Replace the board layout. New custom columns arrive without a key (or with
    a non-``C_`` placeholder) and get one minted from their label. A custom
    column that is dropped has its tasks moved back to TODO, so no task is ever
    left in a status the board cannot show."""
    current_keys = {c["key"] for c in get_columns(db)}
    taken = set(TASK_STATUSES) | {
        c.get("key") for c in columns if isinstance(c, dict) and str(c.get("key") or "").startswith("C_")
    }
    prepared: list[dict[str, Any]] = []
    custom = 0
    for col in columns:
        if not isinstance(col, dict):
            continue
        key = col.get("key")
        label = str(col.get("label") or "").strip()
        if key in TASK_STATUSES:
            prepared.append({**col, "key": key})
            continue
        if not (is_valid_key_shape(key) and str(key).startswith("C_")):
            if not label:
                continue
            key = _mint_key(label, taken)
            taken.add(key)
        if not label:
            continue
        custom += 1
        if custom > MAX_CUSTOM_COLUMNS:
            raise ValueError(f"At most {MAX_CUSTOM_COLUMNS} custom columns are allowed.")
        prepared.append({**col, "key": key, "label": label})

    final = _normalise(prepared)
    final_keys = {c["key"] for c in final}
    removed = [k for k in current_keys - final_keys if k not in TASK_STATUSES]
    if removed:
        db.execute(
            update(CommunicationTask)
            .where(CommunicationTask.status.in_(removed))
            .values(status="TODO")
        )

    value = {"columns": [{k: c[k] for k in ("key", "label", "color", "hidden")} for c in final]}
    row = db.get(AppSetting, BOARD_COLUMNS_KEY)
    if row is None:
        db.add(AppSetting(key=BOARD_COLUMNS_KEY, value=value))
    else:
        row.value = value  # new dict → SQLAlchemy sees the JSON change
    db.commit()
    return final


def task_counts_by_status(db: Session) -> dict[str, int]:
    rows = db.execute(
        select(CommunicationTask.status, func.count(CommunicationTask.id)).group_by(CommunicationTask.status)
    ).all()
    return {status: int(n) for status, n in rows}

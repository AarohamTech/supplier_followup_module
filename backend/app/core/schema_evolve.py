"""Lightweight online schema evolution for SQLite.

`Base.metadata.create_all()` only creates *missing* tables — it never adds
columns to existing ones. This module bridges the gap by inspecting the
live schema and issuing safe `ALTER TABLE ... ADD COLUMN` statements for
columns that are declared on the SQLAlchemy model but missing from disk.

This is intentionally narrow:
  - never drops or renames columns
  - never changes column types
  - only used for SQLite (no-op for other dialects)
"""
from __future__ import annotations

import logging
from typing import Iterable

from sqlalchemy import Column, inspect, text
from sqlalchemy.engine import Engine

log = logging.getLogger(__name__)


def _column_ddl_type(column: Column) -> str:
    try:
        return column.type.compile()
    except Exception:  # noqa: BLE001
        return "TEXT"


def _default_clause(column: Column) -> str:
    if column.default is not None and getattr(column.default, "is_scalar", False):
        value = column.default.arg
        if isinstance(value, bool):
            return f" DEFAULT {1 if value else 0}"
        if isinstance(value, (int, float)):
            return f" DEFAULT {value}"
        if isinstance(value, str):
            escaped = value.replace("'", "''")
            return f" DEFAULT '{escaped}'"
    return ""


def ensure_columns(engine: Engine, tables: Iterable | None = None) -> list[str]:
    """Add columns that are declared on models but missing from the live schema.

    Returns a list of human-readable change descriptions for logging.
    Only operates on SQLite — silently no-ops elsewhere.
    """
    if not engine.url.get_backend_name().startswith("sqlite"):
        return []

    from ..database import Base

    inspector = inspect(engine)
    changes: list[str] = []
    target_tables = list(tables) if tables else list(Base.metadata.sorted_tables)

    with engine.begin() as conn:
        existing_tables = set(inspector.get_table_names())
        for table in target_tables:
            if table.name not in existing_tables:
                continue
            existing_cols = {c["name"] for c in inspector.get_columns(table.name)}
            for col in table.columns:
                if col.name in existing_cols:
                    continue
                ddl_type = _column_ddl_type(col)
                default = _default_clause(col)
                # SQLite ALTER TABLE ADD COLUMN cannot add NOT NULL without a default
                # so we relax the constraint here when no default is available.
                nullable = "" if col.nullable or default else ""
                stmt = (
                    f"ALTER TABLE {table.name} ADD COLUMN {col.name} {ddl_type}"
                    f"{default}{nullable}"
                )
                try:
                    conn.execute(text(stmt))
                    changes.append(f"{table.name}.{col.name}")
                    log.info("Schema evolve: added %s.%s", table.name, col.name)
                except Exception:  # noqa: BLE001
                    log.exception("Schema evolve failed for %s.%s", table.name, col.name)
    return changes

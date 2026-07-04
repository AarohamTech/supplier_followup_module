"""Lightweight online schema evolution for SQLite and PostgreSQL.

`Base.metadata.create_all()` only creates *missing* tables — it never adds
columns to existing ones. This module bridges the gap by inspecting the
live schema and issuing safe `ALTER TABLE ... ADD COLUMN` statements for
columns that are declared on the SQLAlchemy model but missing from the DB.

This is intentionally narrow:
  - never drops or renames columns
  - never changes column types
  - only ever ADDs missing columns (no-op for other dialects)
"""
from __future__ import annotations

import logging
from typing import Iterable

from sqlalchemy import Column, inspect, text
from sqlalchemy.engine import Engine

log = logging.getLogger(__name__)


def _column_ddl_type(column: Column, engine: Engine) -> str:
    try:
        return column.type.compile(dialect=engine.dialect)
    except Exception:  # noqa: BLE001
        return "TEXT"


def _default_clause(column: Column, engine: Engine) -> str:
    if column.default is not None and getattr(column.default, "is_scalar", False):
        value = column.default.arg
        if isinstance(value, bool):
            # Postgres BOOLEAN rejects `DEFAULT 0/1` (DatatypeMismatch); it needs
            # the boolean literal. SQLite has no bool type and uses 0/1.
            if engine.dialect.name == "postgresql":
                return f" DEFAULT {'true' if value else 'false'}"
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
    backend = engine.url.get_backend_name()
    if not (backend.startswith("sqlite") or backend.startswith("postgresql")):
        return []

    from ..database import Base

    inspector = inspect(engine)
    changes: list[str] = []
    target_tables = list(tables) if tables else list(Base.metadata.sorted_tables)

    existing_tables = set(inspector.get_table_names())
    for table in target_tables:
        if table.name not in existing_tables:
            continue
        existing_cols = {c["name"] for c in inspector.get_columns(table.name)}
        for col in table.columns:
            if col.name in existing_cols:
                continue
            ddl_type = _column_ddl_type(col, engine)
            default = _default_clause(col, engine)
            # ADD COLUMN can only be NOT NULL when a default exists to backfill
            # existing rows; otherwise add it nullable.
            not_null = " NOT NULL" if (not col.nullable and default) else ""
            stmt = (
                f"ALTER TABLE {table.name} ADD COLUMN {col.name} {ddl_type}"
                f"{default}{not_null}"
            )
            # Each ALTER runs in its own transaction so one failure (e.g. a column
            # Postgres rejects) can't abort the others.
            try:
                with engine.begin() as conn:
                    conn.execute(text(stmt))
                changes.append(f"{table.name}.{col.name}")
                log.info("Schema evolve: added %s.%s", table.name, col.name)
            except Exception:  # noqa: BLE001
                log.exception("Schema evolve failed for %s.%s", table.name, col.name)
    return changes


def ensure_columns_in_schema(engine: Engine, schema: str) -> list[str]:
    """Like `ensure_columns`, but inspects/alters tables inside `schema`.
    Postgres only; no-op on SQLite. Never drops/renames — only ADDs missing
    columns declared on the models to the per-company copy of each table."""
    backend = engine.url.get_backend_name()
    if not backend.startswith("postgresql"):
        return []
    import re as _re
    if not _re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", schema):
        raise ValueError(f"invalid schema name: {schema!r}")

    from ..database import Base, SHARED_TABLES

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names(schema=schema))
    changes: list[str] = []
    for table in Base.metadata.sorted_tables:
        if table.name in SHARED_TABLES or table.name not in existing_tables:
            continue
        existing_cols = {c["name"] for c in inspector.get_columns(table.name, schema=schema)}
        for col in table.columns:
            if col.name in existing_cols:
                continue
            ddl_type = _column_ddl_type(col, engine)
            default = _default_clause(col, engine)
            not_null = " NOT NULL" if (not col.nullable and default) else ""
            stmt = (
                f'ALTER TABLE "{schema}"."{table.name}" ADD COLUMN {col.name} {ddl_type}'
                f"{default}{not_null}"
            )
            try:
                with engine.begin() as conn:
                    conn.execute(text(stmt))
                changes.append(f"{schema}.{table.name}.{col.name}")
                log.info("Schema evolve: added %s.%s.%s", schema, table.name, col.name)
            except Exception:  # noqa: BLE001
                log.exception("Schema evolve failed for %s.%s.%s", schema, table.name, col.name)
    return changes

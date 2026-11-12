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


# Foreign keys from a shared `public` table into a per-company table. They point
# at public's copy only, so rows belonging to another company always violate
# them (company-101 supplier logins could never be created). Dropped on boot;
# the models no longer declare them.
CROSS_COMPANY_FKS: tuple[tuple[str, str], ...] = (
    ("users", "users_supplier_id_fkey"),
)


def drop_cross_company_fks(engine: Engine) -> list[str]:
    """Drop the stale FKs in CROSS_COMPANY_FKS. Postgres only; idempotent."""
    if not engine.url.get_backend_name().startswith("postgresql"):
        return []
    dropped: list[str] = []
    for table, constraint in CROSS_COMPANY_FKS:
        try:
            with engine.begin() as conn:
                exists = conn.execute(
                    text(
                        "SELECT 1 FROM pg_constraint WHERE conname = :c "
                        "AND conrelid = to_regclass(:t)"
                    ),
                    {"c": constraint, "t": f"public.{table}"},
                ).first()
                if exists:
                    conn.execute(text(f'ALTER TABLE public."{table}" DROP CONSTRAINT "{constraint}"'))
                    dropped.append(f"public.{table}.{constraint}")
                    log.info("Schema evolve: dropped FK public.%s.%s", table, constraint)
        except Exception:  # noqa: BLE001
            log.exception("Schema evolve failed dropping FK %s.%s", table, constraint)
    return dropped


def relax_users_email_unique(engine: Engine) -> list[str]:
    """Swap the global unique index on ``public.users.email`` for a per-company
    one (``lower(email), coalesce(company_id, 0)``). Postgres only; idempotent.

    ``users`` is shared by every company, so a global unique email meant a
    supplier contact who deals with both companies could only ever get a portal
    login in one of them; the other company's Email Master save reported
    "belongs to another supplier". The replacement index is created first; the
    old global one is dropped only when that succeeds, so a failure (e.g. two
    rows differing only in case) leaves the stricter rule in place.
    """
    if not engine.url.get_backend_name().startswith("postgresql"):
        return []
    changes: list[str] = []
    try:
        with engine.begin() as conn:
            if conn.execute(text("SELECT to_regclass('public.users')")).scalar() is None:
                return []
            conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_users_email_company "
                "ON public.users (lower(email), coalesce(company_id, 0))"
            ))
    except Exception:  # noqa: BLE001
        log.exception("Schema evolve: could not create uq_users_email_company; "
                      "keeping the global unique email index")
        return changes

    try:
        with engine.begin() as conn:
            rows = conn.execute(text(
                """
                SELECT i.relname AS index_name, c.conname AS constraint_name
                FROM pg_index x
                JOIN pg_class i ON i.oid = x.indexrelid
                LEFT JOIN pg_constraint c ON c.conindid = x.indexrelid
                    AND c.conrelid = x.indrelid
                WHERE x.indrelid = 'public.users'::regclass
                  AND x.indisunique AND NOT x.indisprimary
                  AND x.indnatts = 1
                  AND x.indexprs IS NULL
                  AND x.indkey[0] = (
                      SELECT attnum FROM pg_attribute
                      WHERE attrelid = 'public.users'::regclass AND attname = 'email'
                  )
                """
            )).all()
            for index_name, constraint_name in rows:
                if constraint_name:
                    conn.execute(text(
                        f'ALTER TABLE public.users DROP CONSTRAINT "{constraint_name}"'
                    ))
                else:
                    conn.execute(text(f'DROP INDEX IF EXISTS public."{index_name}"'))
                changes.append(f"public.users.{constraint_name or index_name}")
                log.info("Schema evolve: dropped global unique email index %s",
                         constraint_name or index_name)
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_users_email ON public.users (email)"))
    except Exception:  # noqa: BLE001
        log.exception("Schema evolve: could not drop the global unique email index")
    return changes

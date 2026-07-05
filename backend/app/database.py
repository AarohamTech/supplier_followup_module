import re
from sqlalchemy import create_engine, text
from sqlalchemy import event
from sqlalchemy.orm import sessionmaker, DeclarativeBase, Session
from sqlalchemy.pool import NullPool
from .core.config import settings
from .core.tenant import get_current_schema, DEFAULT_SCHEMA

_is_sqlite = settings.DATABASE_URL.startswith("sqlite")

# When DB_SCHEMA is set (Postgres only), pin the connection's search_path to it
# so every unqualified table lives in that schema — isolating this app from any
# other tables sharing the database.
_schema = (settings.DB_SCHEMA or "").strip() or None

connect_args: dict = {}
if _is_sqlite:
    connect_args = {"check_same_thread": False}
elif _schema:
    connect_args = {"options": f"-csearch_path={_schema}"}

_engine_kwargs: dict = dict(pool_pre_ping=True, future=True, connect_args=connect_args)
if settings.DB_USE_NULLPOOL and not _is_sqlite:
    # Serverless: don't keep a client-side pool; let the Supabase pooler manage it.
    _engine_kwargs["poolclass"] = NullPool

engine = create_engine(settings.DATABASE_URL, **_engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def ensure_schema() -> str | None:
    """Create the configured schema if it does not exist. No-op for SQLite or
    when DB_SCHEMA is unset. Safe to call repeatedly. Returns the schema name."""
    if _is_sqlite or not _schema:
        return None
    with engine.connect() as conn:
        conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{_schema}"'))
        conn.commit()
    return _schema


def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Multi-company tenancy ─────────────────────────────────────────────────────
# Tables shared across all companies (live in `public`); every other mapped
# table is per-company (copied into each company schema).
SHARED_TABLES: set[str] = {"users", "companies"}

_SCHEMA_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@event.listens_for(engine, "checkout")
def _pin_search_path(dbapi_connection, connection_record, connection_proxy):
    """Pin the pooled connection's search_path to the active company's schema for
    the duration of this checkout. Postgres only — SQLite has no schemas. The
    trailing `, public` keeps the shared `users`/`companies` tables reachable from
    any company schema, and re-running it on every checkout means a reused
    connection can never leak the previous company's schema."""
    if _is_sqlite:
        return
    schema = get_current_schema() or DEFAULT_SCHEMA
    if not _SCHEMA_RE.match(schema):
        schema = DEFAULT_SCHEMA
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute(f'SET search_path TO "{schema}", public')
    finally:
        cursor.close()


def create_company_schema(schema: str) -> list[str]:
    """Create `schema` and, inside it, a structural copy of every per-company
    table from `public`. Postgres only (no-op on SQLite or for `public`).

    Uses `CREATE TABLE <schema>.<t> (LIKE public.<t> INCLUDING ALL)`, which copies
    columns, defaults, NOT NULL/CHECK constraints and unique/PK indexes but
    intentionally does NOT copy foreign keys — tenant tables reference the shared
    `users` table (and each other) as soft references, giving hard isolation.
    Idempotent (`IF NOT EXISTS`). Returns the per-company table names processed."""
    if not _SCHEMA_RE.match(schema):
        raise ValueError(f"invalid schema name: {schema!r}")
    if _is_sqlite:
        return []
    if schema == DEFAULT_SCHEMA:
        return []
    per_company = [t.name for t in Base.metadata.sorted_tables if t.name not in SHARED_TABLES]
    with engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
        for name in per_company:
            conn.execute(
                text(
                    f'CREATE TABLE IF NOT EXISTS "{schema}"."{name}" '
                    f'(LIKE public."{name}" INCLUDING ALL)'
                )
            )
    return per_company

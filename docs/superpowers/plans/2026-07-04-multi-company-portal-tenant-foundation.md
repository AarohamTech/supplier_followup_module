# Multi-Company Portal — Plan 1: Tenant Foundation (Backend) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the single FastAPI app serve two companies (102 "Hariom Tech" in the `public` schema, 101 "Enterprise" in a new `company_101` schema) by resolving the active company from the login token and pinning the Postgres `search_path` per request/job — without changing any existing business query.

**Architecture:** A `ContextVar` holds the active company's schema. A SQLAlchemy engine `checkout` listener runs `SET search_path TO "<schema>", public` on every pooled-connection checkout (Postgres only; no-op on SQLite). A raw-ASGI middleware sets the `ContextVar` per request from a `company` claim in the JWT; background jobs (Plan 2) set it via a `use_company()` context manager. A new shared `companies` registry table (in `public`) maps a company `code` → `schema_name` + branding/theme. New company schemas are created by `CREATE TABLE <schema>.x (LIKE public.x INCLUDING ALL)`, which copies structure but drops cross-schema FKs (intended: tenant isolation via soft references). `users` and `companies` stay shared in `public`.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy 2.0 (`Mapped`/`mapped_column`), Pydantic v2, APScheduler, python-jose (JWT), Postgres (Supabase) in prod / in-memory SQLite in tests. No new dependencies.

## Global Constraints

- **Run backend tooling via the project venv:** `backend/.venv/Scripts/python.exe` (conda Python 3.13). Run all `pytest`/`python` from `backend/`.
- **Tests use in-memory SQLite** (see `backend/tests/conftest.py`); Postgres-only behavior (schema switching, `LIKE`) MUST be guarded so SQLite tests never hit it, and verified separately on Postgres.
- **No new Python dependencies.**
- **Never migrate or drop 102's live data.** 102 stays in `public`. 101 is new, empty tables only.
- **`search_path` is always `"<schema>", public`** — never a bare schema — so the shared `users`/`companies` tables resolve from any company schema.
- **Shared tables are exactly `{"users", "companies"}`.** Every other mapped table is per-company.
- **Schema names are validated** against `^[A-Za-z_][A-Za-z0-9_]*$` before being interpolated into SQL (they come from our own registry, but validate defensively).
- **Follow existing patterns:** models in `app/models/<name>.py` (one class, `Mapped`/`mapped_column`); services in `app/services/<name>_service.py` (no FastAPI imports); routers under `/api/...`; `schema_evolve.ensure_columns` adds new columns online on startup.
- The default company is the `companies` row with `is_default=True` (102 / `public`). A request with no/invalid/omitted company claim resolves to it.

---

### Task 1: Tenant context module

**Files:**
- Create: `backend/app/core/tenant.py`
- Test: `backend/tests/test_tenant_context.py`

**Interfaces:**
- Produces:
  - `DEFAULT_SCHEMA: str` (= `"public"`)
  - `get_current_schema() -> str`
  - `set_current_schema(schema: str | None) -> Token` (contextvars token)
  - `reset_current_schema(token: Token) -> None`
  - `use_company(schema: str | None) -> ContextManager[None]`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_tenant_context.py
from app.core.tenant import (
    DEFAULT_SCHEMA,
    get_current_schema,
    set_current_schema,
    reset_current_schema,
    use_company,
)


def test_default_schema_is_public():
    assert DEFAULT_SCHEMA == "public"
    assert get_current_schema() == "public"


def test_use_company_sets_and_restores():
    assert get_current_schema() == "public"
    with use_company("company_101"):
        assert get_current_schema() == "company_101"
    assert get_current_schema() == "public"


def test_use_company_nested_restore():
    with use_company("company_101"):
        with use_company("company_202"):
            assert get_current_schema() == "company_202"
        assert get_current_schema() == "company_101"
    assert get_current_schema() == "public"


def test_empty_or_none_falls_back_to_default():
    with use_company(""):
        assert get_current_schema() == "public"
    with use_company(None):
        assert get_current_schema() == "public"


def test_set_reset_pair():
    token = set_current_schema("company_101")
    assert get_current_schema() == "company_101"
    reset_current_schema(token)
    assert get_current_schema() == "public"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_tenant_context.py -v` (from `backend/`)
Expected: FAIL with `ModuleNotFoundError: No module named 'app.core.tenant'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/core/tenant.py
"""Per-request / per-job tenant (company) context.

The active company's Postgres schema is stored in a ContextVar so the DB layer
can pin `search_path` for the current request or background-job iteration. On
SQLite (tests) schemas don't exist, so the value is tracked but never applied.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Iterator

DEFAULT_SCHEMA = "public"

_current_schema: ContextVar[str] = ContextVar("current_schema", default=DEFAULT_SCHEMA)


def get_current_schema() -> str:
    return _current_schema.get()


def set_current_schema(schema: str | None) -> Token:
    """Set the active schema; returns a token for `reset_current_schema`."""
    return _current_schema.set(schema or DEFAULT_SCHEMA)


def reset_current_schema(token: Token) -> None:
    _current_schema.reset(token)


@contextmanager
def use_company(schema: str | None) -> Iterator[None]:
    """Bind the active schema for the duration of the block (background jobs)."""
    token = set_current_schema(schema)
    try:
        yield
    finally:
        reset_current_schema(token)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_tenant_context.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/tenant.py backend/tests/test_tenant_context.py
git commit -m "feat(tenant): per-request company schema ContextVar + use_company"
```

---

### Task 2: Engine search_path listener + company-schema creator

**Files:**
- Modify: `backend/app/database.py` (append after `SessionLocal`/`Base`; add imports)
- Test: `backend/tests/test_company_schema_ddl.py`

**Interfaces:**
- Consumes: `app.core.tenant.get_current_schema`, `app.core.tenant.DEFAULT_SCHEMA`
- Produces:
  - `SHARED_TABLES: set[str]` (= `{"users", "companies"}`)
  - `create_company_schema(schema: str) -> list[str]` — Postgres: create `schema` + a `LIKE public.<t> INCLUDING ALL` copy of every per-company table; returns created table names. SQLite / `schema=="public"`: returns `[]`. Raises `ValueError` on an invalid schema name.
  - A registered `checkout` event listener that pins `search_path` (Postgres only).

Note: the shared `users`/`companies` tables must exist in `public` (created by the normal `Base.metadata.create_all`) **before** `create_company_schema` runs — the `LIKE public.<t>` copy requires the public tables to already exist.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_company_schema_ddl.py
import pytest

from app.database import SHARED_TABLES, create_company_schema


def test_shared_tables_are_users_and_companies():
    assert SHARED_TABLES == {"users", "companies"}


def test_create_company_schema_is_noop_on_sqlite():
    # The test engine is SQLite → no schemas; must be a safe no-op, never raise.
    assert create_company_schema("company_101") == []


def test_create_company_schema_public_is_noop():
    assert create_company_schema("public") == []


def test_create_company_schema_rejects_bad_name():
    with pytest.raises(ValueError):
        create_company_schema("bad-name; DROP TABLE users")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_company_schema_ddl.py -v`
Expected: FAIL with `ImportError: cannot import name 'SHARED_TABLES'` (and `create_company_schema`)

- [ ] **Step 3: Write minimal implementation**

Add these imports at the top of `backend/app/database.py` (alongside the existing `from sqlalchemy import create_engine, text`):

```python
import re
from sqlalchemy import event
from .core.tenant import get_current_schema, DEFAULT_SCHEMA
```

Append to the end of `backend/app/database.py`:

```python
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
    if _is_sqlite:
        return []
    if not _SCHEMA_RE.match(schema):
        raise ValueError(f"invalid schema name: {schema!r}")
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_company_schema_ddl.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Run the full backend suite to confirm no regression**

Run: `backend/.venv/Scripts/python.exe -m pytest -q`
Expected: same pass/fail baseline as before this task (the 2 pre-existing `test_mail_send_retry` failures may remain; nothing else newly fails).

- [ ] **Step 6: Commit**

```bash
git add backend/app/database.py backend/tests/test_company_schema_ddl.py
git commit -m "feat(tenant): search_path checkout listener + create_company_schema (LIKE)"
```

---

### Task 3: `companies` registry model

**Files:**
- Create: `backend/app/models/company.py`
- Modify: `backend/app/models/__init__.py` (register the model so `create_all` sees it — match the file's existing import style)
- Test: `backend/tests/test_company_model.py`

**Interfaces:**
- Produces: `Company` ORM model, table `companies`, columns:
  `id` (int PK), `code` (str, unique), `display_name` (str), `schema_name` (str, unique),
  `theme` (str, default `"red"`), `brand_name` (str, default `""`), `logo_url` (str|None),
  `is_active` (bool, default True), `is_default` (bool, default False),
  `created_at`, `updated_at`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_company_model.py
from sqlalchemy import select

from app.models.company import Company


def test_company_roundtrip(db_session):
    db_session.add(
        Company(
            code="102", display_name="Hariom Tech", schema_name="public",
            theme="red", brand_name="H-Connect", is_active=True, is_default=True,
        )
    )
    db_session.commit()
    row = db_session.scalar(select(Company).where(Company.code == "102"))
    assert row is not None
    assert row.schema_name == "public"
    assert row.theme == "red"
    assert row.is_default is True
    assert row.is_active is True
```

> Uses the existing `db_session` fixture from `backend/tests/conftest.py`. If the
> fixture has a different name, match whatever the other model tests use (grep
> `def test_` in `tests/test_supplier_portal.py` for the exact fixture name).

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_company_model.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.models.company'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/models/company.py
"""Company (tenant) registry — shared table in `public`.

One row per company. Maps a stable `code` (used in the JWT `company` claim) to the
Postgres `schema_name` that holds that company's business data, plus branding/theme
the frontend applies. See docs/superpowers/specs/2026-07-04-multi-company-portal-design.md.
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Stable business identifier embedded in the JWT `company` claim (e.g. "101").
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    # Postgres schema holding this company's business data. "public" for 102.
    schema_name: Mapped[str] = mapped_column(String(63), unique=True, nullable=False)
    # Frontend theme key ("red" = current Hariom palette, "blue" = Enterprise).
    theme: Mapped[str] = mapped_column(String(32), default="red", nullable=False)
    brand_name: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Exactly one row should be the default (resolves a request with no company).
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
```

Then register it in `backend/app/models/__init__.py`. Open that file and add an
import matching the existing style (if the file lists models explicitly, add
`from .company import Company` and add `"Company"` to `__all__`; if it does nothing,
add the import line so `create_all` imports the class).

- [ ] **Step 4: Run test to verify it passes**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_company_model.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/company.py backend/app/models/__init__.py backend/tests/test_company_model.py
git commit -m "feat(tenant): companies registry model"
```

---

### Task 4: Company registry service + schema cache

**Files:**
- Create: `backend/app/services/company_service.py`
- Create: `backend/app/schemas/company.py`
- Test: `backend/tests/test_company_service.py`

**Interfaces:**
- Consumes: `app.models.company.Company`, `app.core.tenant.DEFAULT_SCHEMA`
- Produces:
  - `seed_companies(db) -> dict` — idempotent; ensures the 102 + 101 rows from `SEED_COMPANIES` exist (matched by `code`); returns `{"created": n, "existing": m}`.
  - `refresh_cache(db) -> None` — reloads the in-process `code -> schema_name` map and the default schema.
  - `get_schema_for_code(code: str | None) -> str` — cache lookup; falls back to the default schema.
  - `list_active(db) -> list[Company]`
  - `get_by_code(db, code: str) -> Company | None`
  - `get_default(db) -> Company | None`
  - `SEED_COMPANIES: list[dict]` — the 102 + 101 definitions.
  - `schemas/company.py`: `CompanyBrief` (`code`, `display_name`, `theme`, `brand_name`, `logo_url`) with `from_attributes=True`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_company_service.py
from app.services import company_service
from app.core.tenant import DEFAULT_SCHEMA


def test_seed_companies_is_idempotent(db_session):
    first = company_service.seed_companies(db_session)
    assert first["created"] == 2          # 102 + 101
    second = company_service.seed_companies(db_session)
    assert second["created"] == 0
    codes = {c.code for c in company_service.list_active(db_session)}
    assert {"101", "102"} <= codes


def test_default_company_is_102_public(db_session):
    company_service.seed_companies(db_session)
    default = company_service.get_default(db_session)
    assert default.code == "102"
    assert default.schema_name == "public"
    assert default.is_default is True


def test_schema_cache_resolution(db_session):
    company_service.seed_companies(db_session)
    company_service.refresh_cache(db_session)
    assert company_service.get_schema_for_code("101") == "company_101"
    assert company_service.get_schema_for_code("102") == "public"
    # Unknown / missing → default schema (public).
    assert company_service.get_schema_for_code("999") == DEFAULT_SCHEMA
    assert company_service.get_schema_for_code(None) == DEFAULT_SCHEMA
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_company_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.company_service'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/schemas/company.py
"""Public-facing company branding DTO (login picker + active-company theme)."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class CompanyBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    display_name: str
    theme: str
    brand_name: str
    logo_url: str | None = None
```

```python
# backend/app/services/company_service.py
"""Company (tenant) registry: seeding, lookups, and a small in-process cache
mapping the JWT `company` code to a Postgres schema. No FastAPI imports."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.tenant import DEFAULT_SCHEMA
from ..models.company import Company

# Canonical company definitions. 102 keeps the current data in `public`; 101 is new.
SEED_COMPANIES: list[dict] = [
    dict(code="102", display_name="Hariom Tech", schema_name="public",
         theme="red", brand_name="H-Connect", is_active=True, is_default=True),
    dict(code="101", display_name="Enterprise", schema_name="company_101",
         theme="blue", brand_name="Enterprise", is_active=True, is_default=False),
]

# code -> schema_name; refreshed from the DB. Read on the hot request path so the
# tenant middleware never issues a query per request.
_schema_cache: dict[str, str] = {}
_default_schema: str = DEFAULT_SCHEMA


def seed_companies(db: Session) -> dict:
    created = 0
    existing = 0
    for spec in SEED_COMPANIES:
        row = db.scalar(select(Company).where(Company.code == spec["code"]))
        if row is None:
            db.add(Company(**spec))
            created += 1
        else:
            existing += 1
    db.commit()
    refresh_cache(db)
    return {"created": created, "existing": existing}


def refresh_cache(db: Session) -> None:
    global _default_schema
    rows = list(db.scalars(select(Company)).all())
    _schema_cache.clear()
    for row in rows:
        _schema_cache[row.code] = row.schema_name
        if row.is_default:
            _default_schema = row.schema_name


def get_schema_for_code(code: str | None) -> str:
    if not code:
        return _default_schema
    return _schema_cache.get(code, _default_schema)


def list_active(db: Session) -> list[Company]:
    return list(db.scalars(select(Company).where(Company.is_active.is_(True))
                           .order_by(Company.code)).all())


def get_by_code(db: Session, code: str) -> Company | None:
    return db.scalar(select(Company).where(Company.code == code))


def get_default(db: Session) -> Company | None:
    return db.scalar(select(Company).where(Company.is_default.is_(True)))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_company_service.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/company_service.py backend/app/schemas/company.py backend/tests/test_company_service.py
git commit -m "feat(tenant): company registry service + schema cache + CompanyBrief"
```

---

### Task 5: `users.company_id` column

**Files:**
- Modify: `backend/app/models/user.py` (add one column)
- Test: `backend/tests/test_user_company_id.py`

**Interfaces:**
- Produces: `User.company_id: Mapped[int | None]` — FK to `companies.id`, nullable, indexed. NULL → resolves to the default company (102). Set → pins a portal account to that company. Both `users` and `companies` are shared/`public`, so this FK is same-schema and safe.
- Note: `schema_evolve.ensure_columns` adds this column to the live `users` table on startup (it only ever ADDs columns).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_user_company_id.py
from sqlalchemy import select

from app.models.user import User


def test_user_has_nullable_company_id(db_session):
    u = User(email="staff@example.com", hashed_password="x", role="admin")
    db_session.add(u)
    db_session.commit()
    row = db_session.scalar(select(User).where(User.email == "staff@example.com"))
    assert row.company_id is None  # staff default → resolved to default company
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_user_company_id.py -v`
Expected: FAIL with `AttributeError: type object 'User' has no attribute 'company_id'`

- [ ] **Step 3: Write minimal implementation**

In `backend/app/models/user.py`, add this column just after the `emp_code` column (keep the existing `ForeignKey`/`Mapped` import style already in the file):

```python
    # Company (tenant) this account is pinned to. NULL → staff account resolved to
    # the default company (102). Set → portal account scoped to that company only.
    # Both `users` and `companies` live in `public`, so this FK is same-schema.
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id"), index=True, nullable=True
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_user_company_id.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/user.py backend/tests/test_user_company_id.py
git commit -m "feat(tenant): users.company_id (pins portal accounts to a company)"
```

---

### Task 6: Login accepts + embeds the company claim

**Files:**
- Modify: `backend/app/schemas/user.py` (add `company` to `LoginRequest`; add `company` to `Token`)
- Modify: `backend/app/services/company_service.py` (add `resolve_login_company`)
- Modify: `backend/app/routers/auth.py` (embed claim; return active company; new open list endpoint)
- Test: `backend/tests/test_auth_company_claim.py`

**Interfaces:**
- Consumes: `company_service.get_by_code`, `company_service.get_default`, `create_access_token(..., extra=...)`, `decode_token`
- Produces:
  - `company_service.resolve_login_company(db, user, requested_code: str | None) -> Company` — portal accounts (`supplier_id` or `emp_code` set) are pinned to their `company_id`'s company (default if unset); staff get the requested active company or the default.
  - `LoginRequest.company: str | None`
  - `Token.company: CompanyBrief | None`
  - `GET /api/auth/companies` (open) → `list[CompanyBrief]` for the login picker.
  - The JWT now carries `extra={"company": <code>}`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_auth_company_claim.py
from app.core.security import decode_token
from app.services import company_service, user_service


def _login(client, **body):
    return client.post("/api/auth/login", json=body)


def test_staff_login_embeds_requested_company(client, db_session):
    company_service.seed_companies(db_session)
    user_service.create_user(db_session, email="a@x.com", password="Passw0rd!",
                             full_name="A", role="admin", is_active=True)
    r = _login(client, email="a@x.com", password="Passw0rd!", company="101")
    assert r.status_code == 200
    data = r.json()
    assert data["company"]["code"] == "101"
    assert decode_token(data["access_token"])["company"] == "101"


def test_staff_login_defaults_to_102_when_company_omitted(client, db_session):
    company_service.seed_companies(db_session)
    user_service.create_user(db_session, email="b@x.com", password="Passw0rd!",
                             full_name="B", role="admin", is_active=True)
    r = _login(client, email="b@x.com", password="Passw0rd!")
    assert r.status_code == 200
    assert r.json()["company"]["code"] == "102"


def test_companies_list_endpoint_is_open(client, db_session):
    company_service.seed_companies(db_session)
    r = client.get("/api/auth/companies")
    assert r.status_code == 200
    codes = {c["code"] for c in r.json()}
    assert {"101", "102"} <= codes
```

> Uses the `client` (FastAPI TestClient) + `db_session` fixtures from
> `backend/tests/conftest.py` (the same ones `test_supplier_portal.py` uses). If
> the TestClient fixture has a different name, match it.

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_auth_company_claim.py -v`
Expected: FAIL (login response has no `company` key; `/api/auth/companies` → 404)

- [ ] **Step 3: Write minimal implementation**

In `backend/app/schemas/user.py`, add `company` to `LoginRequest` and `Token`:

```python
# add to LoginRequest (after `password: ...`):
    # Company code chosen at login (staff only; portal accounts are pinned). When
    # omitted, the default company (102) is used.
    company: str | None = None
```

```python
# at the top of schemas/user.py add:
from .company import CompanyBrief

# add to Token (after `user: UserOut`):
    company: CompanyBrief | None = None
```

In `backend/app/services/company_service.py`, add:

```python
def resolve_login_company(db: Session, user, requested_code: str | None) -> Company | None:
    """Resolve which company an account logs into. Portal accounts (supplier or
    employee) are pinned to their own company; staff get the requested active
    company, falling back to the default."""
    is_portal = getattr(user, "supplier_id", None) is not None or getattr(user, "emp_code", None) is not None
    if is_portal:
        if user.company_id is not None:
            pinned = db.get(Company, user.company_id)
            if pinned is not None:
                return pinned
        return get_default(db)
    if requested_code:
        chosen = get_by_code(db, requested_code)
        if chosen is not None and chosen.is_active:
            return chosen
    return get_default(db)
```

In `backend/app/routers/auth.py`, update the imports and the `login` function, and
add the open list endpoint. Replace the existing `login` body's token line and
return, and add the new route:

```python
# add imports
from ..schemas.company import CompanyBrief
from ..services import company_service

# --- in login(), replace the token creation + return with: ---
    active = company_service.resolve_login_company(db, user, payload.company)
    extra = {"company": active.code} if active is not None else None
    token = create_access_token(subject=user.id, role=user.role, email=user.email, extra=extra)
    return Token(
        access_token=token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=user_out(db, user),
        company=CompanyBrief.model_validate(active) if active is not None else None,
    )


# --- add a new open endpoint (login picker needs this BEFORE auth) ---
@router.get("/companies", response_model=list[CompanyBrief])
def list_companies(db: Session = Depends(get_db)) -> list[CompanyBrief]:
    return [CompanyBrief.model_validate(c) for c in company_service.list_active(db)]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_auth_company_claim.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/user.py backend/app/services/company_service.py backend/app/routers/auth.py backend/tests/test_auth_company_claim.py
git commit -m "feat(tenant): login accepts+embeds company claim, open /auth/companies"
```

---

### Task 7: Tenant middleware (resolve schema per request)

**Files:**
- Create: `backend/app/core/tenant_middleware.py`
- Modify: `backend/app/main.py` (register the middleware; refresh the company cache at startup)
- Test: `backend/tests/test_tenant_middleware.py`

**Interfaces:**
- Consumes: `decode_token`, `company_service.get_schema_for_code`, `tenant.set_current_schema`/`reset_current_schema`
- Produces:
  - `schema_from_authorization(header: str | None) -> str` — pure function: extract bearer, decode, map `company` claim → schema; any failure → default schema.
  - `TenantMiddleware` — raw-ASGI middleware that sets the schema ContextVar for the request and resets it after.

Why raw ASGI (not `BaseHTTPMiddleware`): a `ContextVar` set in `BaseHTTPMiddleware` does not reliably propagate to the endpoint/DB dependency. A raw-ASGI middleware sets it in the same task that runs the endpoint, so `get_db`'s connection checkout sees the right schema.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_tenant_middleware.py
from app.core.security import create_access_token
from app.core.tenant_middleware import schema_from_authorization
from app.services import company_service


def test_schema_from_authorization_resolves_company(db_session):
    company_service.seed_companies(db_session)
    company_service.refresh_cache(db_session)
    token = create_access_token(subject=1, role="admin", extra={"company": "101"})
    assert schema_from_authorization(f"Bearer {token}") == "company_101"


def test_schema_from_authorization_defaults_on_missing_or_bad(db_session):
    company_service.seed_companies(db_session)
    company_service.refresh_cache(db_session)
    assert schema_from_authorization(None) == "public"
    assert schema_from_authorization("Bearer not-a-jwt") == "public"
    token_no_company = create_access_token(subject=1, role="admin")
    assert schema_from_authorization(f"Bearer {token_no_company}") == "public"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_tenant_middleware.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.core.tenant_middleware'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/core/tenant_middleware.py
"""Raw-ASGI middleware that binds the active company's schema for each request.

Reads the JWT `company` claim from the Authorization header, maps it to a schema
via the company registry cache, and sets the tenant ContextVar for the lifetime
of the request. Raw ASGI (not BaseHTTPMiddleware) so the ContextVar propagates to
the endpoint and its DB session. Fail-open: anything unresolved → default schema.
"""
from __future__ import annotations

from .security import TokenError, decode_token
from .tenant import reset_current_schema, set_current_schema, DEFAULT_SCHEMA
from ..services import company_service


def schema_from_authorization(header: str | None) -> str:
    if not header or not header.lower().startswith("bearer "):
        return DEFAULT_SCHEMA
    token = header.split(" ", 1)[1].strip()
    try:
        payload = decode_token(token)
    except TokenError:
        return DEFAULT_SCHEMA
    return company_service.get_schema_for_code(payload.get("company"))


class TenantMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        header = None
        for key, value in scope.get("headers", []):
            if key == b"authorization":
                header = value.decode("latin-1")
                break
        token = set_current_schema(schema_from_authorization(header))
        try:
            await self.app(scope, receive, send)
        finally:
            reset_current_schema(token)
```

In `backend/app/main.py`:

1. Add the import near the other core imports:

```python
from .core.tenant_middleware import TenantMiddleware
from .services import company_service
```

2. Register the middleware AFTER the `CORSMiddleware` block (Starlette runs the
   last-added middleware outermost; either order is fine here since CORS short-
   circuits `OPTIONS` before tenant resolution matters):

```python
app.add_middleware(TenantMiddleware)
```

3. Seed + cache companies during startup. Inside `lifespan`, right after the
   `seed_module.run()` block succeeds, add:

```python
        try:
            with SessionLocal() as _cdb:
                company_service.seed_companies(_cdb)
                company_service.refresh_cache(_cdb)
        except Exception:  # noqa: BLE001
            log.exception("Company registry seed/cache failed (continuing)")
```

   (Add `SessionLocal` to the existing `from .database import ...` line.)

- [ ] **Step 4: Run test to verify it passes**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_tenant_middleware.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Run the full suite (no regression)**

Run: `backend/.venv/Scripts/python.exe -m pytest -q`
Expected: baseline pass/fail unchanged.

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/tenant_middleware.py backend/app/main.py backend/tests/test_tenant_middleware.py
git commit -m "feat(tenant): raw-ASGI middleware resolves company schema per request"
```

---

### Task 8: Company switch endpoint (staff)

**Files:**
- Modify: `backend/app/routers/auth.py` (add `POST /api/auth/switch-company`)
- Test: `backend/tests/test_switch_company.py`

**Interfaces:**
- Consumes: `get_current_user`, `company_service.get_by_code`, `create_access_token`
- Produces: `POST /api/auth/switch-company` body `{"company": "<code>"}` → `Token` with a re-issued JWT for the new company. Staff only (portal accounts → 403). Unknown/inactive company → 400.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_switch_company.py
from app.core.security import decode_token
from app.services import company_service, user_service


def _token(client, db_session):
    company_service.seed_companies(db_session)
    user_service.create_user(db_session, email="s@x.com", password="Passw0rd!",
                             full_name="S", role="manager", is_active=True)
    r = client.post("/api/auth/login", json={"email": "s@x.com", "password": "Passw0rd!"})
    return r.json()["access_token"]


def test_switch_company_reissues_token(client, db_session):
    tok = _token(client, db_session)
    r = client.post("/api/auth/switch-company", json={"company": "101"},
                    headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    body = r.json()
    assert body["company"]["code"] == "101"
    assert decode_token(body["access_token"])["company"] == "101"


def test_switch_company_rejects_unknown(client, db_session):
    tok = _token(client, db_session)
    r = client.post("/api/auth/switch-company", json={"company": "999"},
                    headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_switch_company.py -v`
Expected: FAIL (route → 404)

- [ ] **Step 3: Write minimal implementation**

Add to `backend/app/routers/auth.py`:

```python
from pydantic import BaseModel


class SwitchCompanyRequest(BaseModel):
    company: str


@router.post("/switch-company", response_model=Token)
def switch_company(
    payload: SwitchCompanyRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Token:
    # Portal accounts are pinned to their own company — no switching.
    if user.supplier_id is not None or user.emp_code is not None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Portal accounts cannot switch company")
    target = company_service.get_by_code(db, payload.company)
    if target is None or not target.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Unknown or inactive company")
    token = create_access_token(subject=user.id, role=user.role, email=user.email,
                                extra={"company": target.code})
    return Token(
        access_token=token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=user_out(db, user),
        company=CompanyBrief.model_validate(target),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_switch_company.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/auth.py backend/tests/test_switch_company.py
git commit -m "feat(tenant): staff switch-company endpoint re-issues token"
```

---

### Task 9: Create the 101 schema on startup

**Files:**
- Modify: `backend/app/seed.py` (create non-public company schemas after companies are seeded)
- Modify: `backend/app/main.py` (call the schema creation once during `lifespan`, after `create_all` + company seed)
- Test: `backend/tests/test_seed_company_schema.py`

**Interfaces:**
- Consumes: `company_service.seed_companies`, `company_service.list_active`, `database.create_company_schema`
- Produces: `seed.ensure_company_schemas(db) -> list[str]` — for each active company whose `schema_name != "public"`, call `create_company_schema(schema)`; returns the schemas processed. No-op on SQLite (so tests stay green).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_seed_company_schema.py
from app import seed
from app.services import company_service


def test_ensure_company_schemas_noop_on_sqlite(db_session):
    company_service.seed_companies(db_session)
    # On SQLite create_company_schema is a no-op, so this returns [] and never raises.
    assert seed.ensure_company_schemas(db_session) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_seed_company_schema.py -v`
Expected: FAIL with `AttributeError: module 'app.seed' has no attribute 'ensure_company_schemas'`

- [ ] **Step 3: Write minimal implementation**

Add to `backend/app/seed.py`:

```python
def ensure_company_schemas(db: Session) -> list[str]:
    """Create the Postgres schema + per-company tables for every non-public
    company. No-op on SQLite. Requires the public tables to already exist."""
    from .database import create_company_schema
    from .services import company_service

    done: list[str] = []
    for company in company_service.list_active(db):
        if company.schema_name and company.schema_name != "public":
            create_company_schema(company.schema_name)
            done.append(company.schema_name)
    return done
```

Wire it into `backend/app/main.py`'s `lifespan`, immediately after the company
seed/cache block from Task 7 (so it runs after `create_all` created the public
tables and after the companies rows exist):

```python
        try:
            with SessionLocal() as _sdb:
                created = seed_module.ensure_company_schemas(_sdb)
                if created:
                    log.info("Ensured company schemas: %s", ", ".join(created))
        except Exception:  # noqa: BLE001
            log.exception("Company schema creation failed (continuing)")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_seed_company_schema.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Run the full suite (no regression)**

Run: `backend/.venv/Scripts/python.exe -m pytest -q`
Expected: baseline pass/fail unchanged.

- [ ] **Step 6: Commit**

```bash
git add backend/app/seed.py backend/app/main.py backend/tests/test_seed_company_schema.py
git commit -m "feat(tenant): create company_101 schema + tables on startup"
```

---

### Task 10: Postgres isolation test + live verification

**Files:**
- Create: `backend/tests/test_tenant_isolation_pg.py` (Postgres-gated; skipped on SQLite)

**Interfaces:**
- Consumes: everything above. This is the end-to-end proof that a write under
  `use_company("company_101")` lands in `company_101` and is invisible to the
  default (public/102) context.

- [ ] **Step 1: Write the Postgres-gated integration test**

```python
# backend/tests/test_tenant_isolation_pg.py
"""End-to-end tenant isolation — Postgres only (schemas don't exist on SQLite).

Runs only when TEST_DATABASE_URL points at Postgres. It creates the company_101
schema, writes a procurement row under each company context, and asserts each
context sees only its own rows.
"""
import os

import pytest
from sqlalchemy import create_engine, text

PG_URL = os.getenv("TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(
    not PG_URL.startswith("postgresql"),
    reason="tenant isolation requires a Postgres TEST_DATABASE_URL",
)


def test_company_101_rows_are_isolated_from_public():
    # NOTE: run against a throwaway Postgres DB. This test drives the real DDL +
    # search_path path that SQLite cannot exercise.
    from app.core.tenant import use_company
    from app.database import Base, engine, create_company_schema
    from app.models.procurement import ProcurementRecord
    from app.database import SessionLocal

    Base.metadata.create_all(bind=engine)          # public tables
    create_company_schema("company_101")           # LIKE-copy into company_101

    marker_public = "ISO-PUBLIC-0001"
    marker_101 = "ISO-101-0001"

    # Write one row in each company context.
    with SessionLocal() as db:                      # default → public
        db.add(ProcurementRecord(crm_no=marker_public, supplier_po_no="P1",
                                 material_name="M", po_no="P1"))
        db.commit()
    with use_company("company_101"):
        with SessionLocal() as db:
            db.add(ProcurementRecord(crm_no=marker_101, supplier_po_no="P1",
                                     material_name="M", po_no="P1"))
            db.commit()

    # Each context sees only its own row.
    with SessionLocal() as db:
        crms = {r.crm_no for r in db.query(ProcurementRecord).all()}
        assert marker_public in crms and marker_101 not in crms
    with use_company("company_101"):
        with SessionLocal() as db:
            crms = {r.crm_no for r in db.query(ProcurementRecord).all()}
            assert marker_101 in crms and marker_public not in crms

    # Cleanup.
    with engine.begin() as conn:
        conn.execute(text('DROP SCHEMA IF EXISTS "company_101" CASCADE'))
        conn.execute(text(f"DELETE FROM public.procurement_records WHERE crm_no = '{marker_public}'"))
```

> `ProcurementRecord`'s required NOT-NULL columns may differ; if the insert fails
> on a missing non-null field, add the minimal required fields (check
> `app/models/procurement.py` for `nullable=False` columns without a default).

- [ ] **Step 2: Run it on SQLite (should skip)**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_tenant_isolation_pg.py -v`
Expected: SKIPPED (1 skipped) — proves the gate works and the default suite stays green.

- [ ] **Step 3: Run it against a throwaway Postgres DB**

```bash
# from backend/, with a disposable Postgres (e.g. a scratch Supabase DB or local docker):
TEST_DATABASE_URL="postgresql+psycopg2://user:pass@host:5432/scratch" \
  backend/.venv/Scripts/python.exe -m pytest tests/test_tenant_isolation_pg.py -v
```
Expected: PASS (1 passed) — writes are isolated per schema.

- [ ] **Step 4: Live smoke against the running app (manual)**

Bring up the backend against a **scratch** Postgres (never prod for this check):

```bash
# from backend/
backend/.venv/Scripts/python.exe -m uvicorn app.main:app --port 8000
```

Verify, in order:
1. `GET /api/auth/companies` → returns 101 + 102 (open, no token).
2. Log in with `company: "102"` → `company.code == "102"`; the JWT decodes with `"company":"102"`.
3. Log in with `company: "101"` → `company.code == "101"`.
4. As a staff token, create a supplier/PO in 101 context and confirm it does NOT appear when using a 102 token, and vice-versa (mirror of the Postgres test, but over HTTP).
5. `POST /api/auth/switch-company {"company":"101"}` → new token; subsequent `GET /api/procurement` returns 101's (empty) set, not 102's.
6. Confirm the app still boots and 102 behaves exactly as before (existing suite green; existing 102 data untouched).

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_tenant_isolation_pg.py
git commit -m "test(tenant): Postgres-gated end-to-end company isolation"
```

---

## Self-Review

**1. Spec coverage (against `2026-07-04-multi-company-portal-design.md`):**
- §3/§4.2 per-request `search_path` switch → Tasks 1, 2, 7. ✅
- §4.1 shared vs per-company split → Task 2 (`SHARED_TABLES`), Task 9 (schema creation). ✅
- §4.4 `companies` registry → Tasks 3, 4. ✅
- §5.1 login company picker (backend) + JWT claim → Task 6. ✅
- §5.2 in-app switch → Task 8. ✅
- §6.5 `users.company_id` → Task 5. ✅
- §9 rollout: 102 untouched, isolation tests → Tasks 2/9 (no public migration), Task 10. ✅
- **Deferred to Plan 2/3 (out of scope here, by design):** per-company CRM ingest + upsert `index_elements` change, per-company scheduler loop, mail-fetch attribution (Plan 2); login picker UI, top-bar switcher, light-blue theme, branding (Plan 3). Listed under "Next plans" below.

**2. Placeholder scan:** No TBD/TODO; every code step shows complete code. Two spots defer to reading a specific file for an exact name (the `db_session`/`client` fixture names in `conftest.py`, and `ProcurementRecord`'s NOT-NULL columns) — these are lookups in named files, not missing implementation.

**3. Type consistency:** `get_schema_for_code`, `resolve_login_company`, `schema_from_authorization`, `create_company_schema`, `use_company`, `SHARED_TABLES`, `CompanyBrief`, `Company`, `users.company_id`, the `company` JWT claim, and the `Token.company` field are named identically across the tasks that define and consume them. ✅

---

## Next plans (to be written after Plan 1 is executing/verified)

- **Plan 2 — Per-company background jobs & CRM ingest:** wrap each scheduler job body in a `use_company(schema)` loop over active companies; make `crm_ingest_service` take per-company CRM config (base URL, desk, login, device) with a **per-company token cache**; switch the PO upsert from `constraint="uq_procurement_match_latest"` to `index_elements=["crm_no","supplier_po_no","material_name"]` (so it works in the LIKE-created 101 schema); shared-inbox reply attribution by supplier email; per-schema `schema_evolve` on startup. Add per-company CRM/mail override columns to `companies`.
- **Plan 3 — Frontend multi-company UX:** login company picker (calls `GET /api/auth/companies`), store the active `company` from the login/switch response, top-bar company switcher (calls `POST /api/auth/switch-company`), a company-theme layer that applies the `theme` palette (light-blue for 101) on top of the existing light/dark toggle, and company-driven brand name/logo.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-07-04-multi-company-portal-tenant-foundation.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

**Which approach?**

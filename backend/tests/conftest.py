"""Global test isolation — the single most important guardrail in this suite.

`backend/.env`'s `DATABASE_URL` points at the PRODUCTION Supabase database. The
app's `Settings()` is an `@lru_cache` singleton and `app.database.engine` is a
module-level object built once, from whatever `DATABASE_URL` is present the first
time `app.core.config` is imported. If a test module imports `app.*` before any
SQLite override is in place, the shared engine binds to production for the entire
pytest session — and any code that performs real writes/DDL through that engine
(e.g. `create_company_schema`) would run against prod.

pytest imports this conftest before collecting/importing any test module, so
setting the env var here — at import time, unconditionally — guarantees the app
engine is SQLite no matter what order test modules load in. Do NOT use
`setdefault`; force it, so a stray real `DATABASE_URL` in the environment can't
win.
"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./_test_app.sqlite"
# Never let a schema pin (used for multi-company Postgres isolation) leak into
# the SQLite test engine.
os.environ["DB_SCHEMA"] = ""

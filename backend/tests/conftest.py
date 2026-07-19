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

# Disable every external-I/O integration during tests. `backend/.env` enables
# real LLM/RAG/SMTP/CRM in production; without this, a full-suite run makes live
# API calls to OpenAI/NVIDIA/SMTP/the CRM — slow, costly, and flaky (an LLM
# timeout under load intermittently fails otherwise-isolated tests). Tests that
# exercise these paths patch/mock them explicitly, so forcing the defaults OFF
# here is safe and makes the suite hermetic, fast, and deterministic.
for _flag in (
    "LLM_ENABLED", "OPENAI_ENABLED", "RAG_ENABLED",
    "AI_TRIAGE_ENABLED", "AI_PO_FOLLOWUP_ENABLED",
    "SCHEDULER_ENABLED", "MAIL_INBOX_ENABLED", "SMTP_ENABLED",
    "CRM_INGEST_ENABLED", "CRM_QTY_PROBE_ENABLED", "COURIER_API_ENABLED",
):
    os.environ[_flag] = "false"

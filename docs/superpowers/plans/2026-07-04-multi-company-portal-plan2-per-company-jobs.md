# Multi-Company Portal — Plan 2: Per-Company Jobs, CRM Ingest & Reply Attribution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make company 101 (Enterprise) ingest its **own** POs from its own CRM desk, run its **own** follow-ups/sends per its schema, and route inbound supplier replies from the shared mailbox to the correct company — all without changing the live 102 (Hariom Tech) behaviour.

**Architecture:** Plan 1 gave us `use_company(schema)` (a ContextVar) + an engine `checkout` listener that pins `search_path`. Plan 2 makes the background jobs *tenant-aware*: each scheduler runner loops over active companies and runs the existing job body under `use_company(company.schema_name)`. CRM config becomes per-company (env-based, so no CRM passwords in the DB); the CRM ingest and mail-send worker are refactored to take that context. Because the tenant lives in a ContextVar that does **not** cross thread boundaries, the multi-threaded mail-send worker is made schema-aware explicitly. Inbound replies are fetched once from the shared inbox, then each is attributed to a company by matching the sender against that company's suppliers.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy 2.0, APScheduler, `requests`, python-jose, Postgres (Supabase) / in-memory SQLite in tests. No new dependencies.

## Global Constraints

- **Run backend tooling via the venv:** `backend/.venv/Scripts/python.exe` (conda Python 3.13). Run from `backend/`.
- **TESTING CONVENTION (authoritative):** no `conftest.py`-based fixtures for the DB. Tests are `unittest.TestCase` using an in-memory SQLite `_temp_db()` context manager (copy the header from `backend/tests/test_supplier_portal.py`). HTTP tests use `TestClient` + `app.dependency_overrides[get_db]` (see `test_task_ai_summary.py`). `backend/tests/conftest.py` already forces SQLite + disables external I/O (LLM/SMTP/CRM/scheduler) — never undo that.
- **The default company (102) path must stay byte-for-byte behaviourally identical.** 102 keeps using the existing `CRM_*` / `SMTP_*` / `IMAP_*` settings and the same code path. All per-company logic is additive.
- **No CRM/mail passwords in the database.** Per-company CRM creds come from `.env` as `CRM_<CODE>_*`; the shared mailbox stays global for now (101 shares 102's inbox — Plan 1 decision).
- **Tenant schema must be propagated into worker threads** (`ContextVar` does not auto-cross threads) — any code that opens a `SessionLocal()` in a new thread must re-establish the active schema.
- **No new Python dependencies.**
- Company iteration uses `company_service.list_active(db)` (Plan 1) → each row has `.code`, `.schema_name`, `.is_default`. The companies table is shared (`public`); list it from the default context.
- The procurement match key is `(crm_no, supplier_po_no, material_name)` (constraint `uq_procurement_match_latest`).

---

### Task 1: Per-company CRM config resolver

**Files:**
- Create: `backend/app/services/crm_config.py`
- Modify: `backend/example.env` (document the `CRM_<CODE>_*` keys)
- Test: `backend/tests/test_crm_config.py`

**Interfaces:**
- Produces:
  - `CrmConfig` (frozen dataclass): `base_url: str`, `desk_id: str`, `login_email: str`, `login_password: str`, `device_id: str`.
  - `get_crm_config(code: str, *, is_default: bool) -> CrmConfig | None` — default company reads the legacy `CRM_*` settings; others read `CRM_<code>_*` env vars. Returns `None` when desk id, email, password, or base url is missing (→ ingestion skips that company).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_crm_config.py
import os
import unittest
from unittest.mock import patch

from app.services.crm_config import CrmConfig, get_crm_config


class CrmConfigTests(unittest.TestCase):
    def test_non_default_reads_prefixed_env(self):
        env = {
            "CRM_101_DESK_ID": "101",
            "CRM_101_LOGIN_EMAIL": "e101@x.com",
            "CRM_101_LOGIN_PASSWORD": "secret101",
            "CRM_101_BASE_URL": "http://crm.example:8599",
        }
        with patch.dict(os.environ, env, clear=False):
            cfg = get_crm_config("101", is_default=False)
        assert isinstance(cfg, CrmConfig)
        assert cfg.desk_id == "101"
        assert cfg.login_email == "e101@x.com"
        assert cfg.login_password == "secret101"
        assert cfg.base_url == "http://crm.example:8599"
        assert cfg.device_id == "101"  # falls back to desk_id when not set

    def test_incomplete_config_returns_none(self):
        with patch.dict(os.environ, {"CRM_101_DESK_ID": "101"}, clear=False):
            # No email/password → not usable yet.
            assert get_crm_config("101", is_default=False) is None

    def test_default_company_uses_legacy_settings(self):
        from app.services import crm_config as mod
        with patch.object(mod.settings, "CRM_DESK_ID", "102"), \
             patch.object(mod.settings, "CRM_LOGIN_EMAIL", "e102@x.com"), \
             patch.object(mod.settings, "CRM_LOGIN_PASSWORD", "secret102"), \
             patch.object(mod.settings, "CRM_API_BASE_URL", "http://crm.example:8599"), \
             patch.object(mod.settings, "CRM_DEVICE_ID", "102"):
            cfg = get_crm_config("102", is_default=True)
        assert cfg is not None
        assert cfg.desk_id == "102"
        assert cfg.login_email == "e102@x.com"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_crm_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.crm_config'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/services/crm_config.py
"""Per-company CRM feed configuration.

The default company (102) uses the legacy `CRM_*` settings. Other companies read
`CRM_<CODE>_*` env vars, so CRM passwords never live in the database. A company
whose config is incomplete (missing desk id / credentials / base url) yields None
and is skipped by ingestion until its creds are added.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from ..core.config import settings


@dataclass(frozen=True)
class CrmConfig:
    base_url: str
    desk_id: str
    login_email: str
    login_password: str
    device_id: str


def _env(code: str, name: str) -> str:
    return (os.environ.get(f"CRM_{code}_{name}") or "").strip()


def get_crm_config(code: str, *, is_default: bool) -> CrmConfig | None:
    if is_default:
        desk = str(settings.CRM_DESK_ID or "").strip()
        email = (settings.CRM_LOGIN_EMAIL or "").strip()
        password = (settings.CRM_LOGIN_PASSWORD or "").strip()
        device = (settings.CRM_DEVICE_ID or "").strip() or desk
        base = (settings.CRM_API_BASE_URL or "").rstrip("/")
    else:
        desk = _env(code, "DESK_ID")
        email = _env(code, "LOGIN_EMAIL")
        password = _env(code, "LOGIN_PASSWORD")
        device = _env(code, "DEVICE_ID") or desk
        base = (_env(code, "BASE_URL") or settings.CRM_API_BASE_URL or "").rstrip("/")
    if not (desk and email and password and base):
        return None
    return CrmConfig(
        base_url=base, desk_id=desk, login_email=email,
        login_password=password, device_id=device,
    )
```

Append to `backend/example.env` (near the existing `CRM_*` block):

```
# ── Additional company CRM feeds (multi-company portal) ──────────────────────
# Company 102 (Hariom Tech, default) uses the CRM_* keys above. Extra companies
# read CRM_<CODE>_* (CODE = the companies.code, e.g. 101). Leave blank until the
# desk credentials exist — that company's ingestion stays dormant.
# CRM_101_DESK_ID=101
# CRM_101_LOGIN_EMAIL=
# CRM_101_LOGIN_PASSWORD=
# CRM_101_DEVICE_ID=101
# CRM_101_BASE_URL=            # optional; defaults to CRM_API_BASE_URL
```

- [ ] **Step 4: Run test to verify it passes**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_crm_config.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/crm_config.py backend/example.env backend/tests/test_crm_config.py
git commit -m "feat(mc): per-company CRM config resolver (env-based)"
```

---

### Task 2: CRM ingest — config-driven + per-config token cache + portable upsert

**Files:**
- Modify: `backend/app/services/crm_ingest_service.py`
- Test: `backend/tests/test_crm_ingest_config.py`

**Interfaces:**
- Consumes: `crm_config.CrmConfig` (Task 1), `app.core.tenant` (already present).
- Produces:
  - `get_token(cfg: CrmConfig) -> str` (per-config token cache, keyed by `(base_url, login_email)`).
  - `fetch_desk(cfg: CrmConfig) -> list[dict]`.
  - `poll_and_ingest(db, cfg: CrmConfig | None = None, *, desk_label: str | None = None, trigger: str = "auto") -> dict` — when `cfg is None`, builds the legacy 102 config from settings so existing callers keep working.
  - The bulk upsert now conflicts on `index_elements=["crm_no", "supplier_po_no", "material_name"]` (not the constraint *name*), so it works in the `LIKE`-created 101 schema.

This refactors a live file. The 102 path must behave identically. Below are the exact function replacements; keep everything else in the file unchanged.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_crm_ingest_config.py
import unittest
from unittest.mock import patch

from app.services import crm_ingest_service as ingest
from app.services.crm_config import CrmConfig


CFG_A = CrmConfig(base_url="http://a", desk_id="101", login_email="a@x", login_password="pa", device_id="101")
CFG_B = CrmConfig(base_url="http://b", desk_id="102", login_email="b@x", login_password="pb", device_id="102")


class CrmTokenCacheTests(unittest.TestCase):
    def setUp(self):
        ingest._token_caches.clear()

    def test_token_cache_is_per_config(self):
        calls = []

        def fake_login(cfg):
            calls.append(cfg.login_email)
            # a non-expiring token (exp 0 → treated as fresh)
            return "tok-" + cfg.login_email

        with patch.object(ingest, "_login", side_effect=fake_login), \
             patch.object(ingest, "_token_exp", return_value=0.0):
            t1 = ingest.get_token(CFG_A)
            t1b = ingest.get_token(CFG_A)   # cached — no second login
            t2 = ingest.get_token(CFG_B)    # different config — logs in again
        assert t1 == "tok-a@x" and t1b == "tok-a@x"
        assert t2 == "tok-b@x"
        assert calls == ["a@x", "b@x"]      # exactly one login per distinct config


class CrmUpsertPortabilityTests(unittest.TestCase):
    def test_upsert_conflict_targets_columns_not_constraint_name(self):
        # The pg_insert statement must use index_elements (portable across schemas),
        # never a named constraint that LIKE-copied tables don't carry.
        import inspect
        src = inspect.getsource(ingest._bulk_upsert)
        assert "index_elements=[\"crm_no\", \"supplier_po_no\", \"material_name\"]" in src \
            or "index_elements=['crm_no', 'supplier_po_no', 'material_name']" in src
        assert "constraint=\"uq_procurement_match_latest\"" not in src
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_crm_ingest_config.py -v`
Expected: FAIL — `_token_caches` doesn't exist / `_login` takes no `cfg` / upsert still uses `constraint=`.

- [ ] **Step 3: Write minimal implementation**

In `backend/app/services/crm_ingest_service.py`:

**(a)** Replace the module-level token cache declaration:

```python
# OLD:
# _lock = threading.Lock()
# _token_cache: dict[str, Any] = {"token": None, "exp": 0.0}
# _login_keys_logged = False

# NEW:
_lock = threading.Lock()
_token_caches: dict[tuple[str, str], dict[str, Any]] = {}
_login_keys_logged = False
```

**(b)** Replace `_login` and `get_token`:

```python
def _login(cfg: "CrmConfig") -> str:
    global _login_keys_logged
    base = cfg.base_url.rstrip("/")
    body = {"Email": cfg.login_email, "Password": cfg.login_password, "DeviceId": cfg.device_id}
    resp = requests.post(
        f"{base}/api/login", json=body,
        timeout=settings.CRM_HTTP_TIMEOUT_SECONDS, headers={"Accept": "application/json"},
    )
    resp.raise_for_status()
    try:
        data = resp.json()
    except ValueError:
        data = resp.text
    if not _login_keys_logged:
        shape = list(data.keys()) if isinstance(data, dict) else type(data).__name__
        log.info("[crm] login response shape: %s", shape)
        _login_keys_logged = True
    token = _extract_token(data)
    if not token:
        raise RuntimeError("CRM login succeeded but no token found in the response")
    return token


def get_token(cfg: "CrmConfig", *, force_refresh: bool = False) -> str:
    """Return a valid bearer token for `cfg`, logging in / refreshing as needed.
    Tokens are cached PER config (base_url + login email) so each company's desk
    keeps its own session."""
    key = (cfg.base_url, cfg.login_email)
    with _lock:
        now = time.time()
        cache = _token_caches.get(key) or {"token": None, "exp": 0.0}
        cached = cache["token"]
        exp = cache["exp"]
        fresh_enough = cached and (exp == 0.0 or now < exp - _TOKEN_LEEWAY_SECONDS)
        if cached and fresh_enough and not force_refresh:
            return cached
        token = _login(cfg)
        _token_caches[key] = {"token": token, "exp": _token_exp(token)}
        return token
```

**(c)** Replace `fetch_desk` to take `cfg`:

```python
def fetch_desk(cfg: "CrmConfig") -> list[dict[str, Any]]:
    base = cfg.base_url.rstrip("/")
    url = f"{base}/api/crm/GetPendingUserDesk/{cfg.desk_id}"

    def _call(token: str) -> requests.Response:
        return requests.get(
            url,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=settings.CRM_HTTP_TIMEOUT_SECONDS,
        )

    resp = _call(get_token(cfg))
    if resp.status_code == 401:
        resp = _call(get_token(cfg, force_refresh=True))
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, dict):
        for key in ("data", "Data", "result", "Result", "items", "Items"):
            if isinstance(data.get(key), list):
                return data[key]
    if not isinstance(data, list):
        raise RuntimeError(f"CRM desk feed returned {type(data).__name__}, expected a list")
    _log_row_keys(data)
    return data
```

**(d)** Add the `CrmConfig` import at the top (with the other imports):

```python
from .crm_config import CrmConfig
```

**(e)** In `_bulk_upsert`, change the conflict target (only these lines change):

```python
        stmt = stmt.on_conflict_do_update(
            index_elements=["crm_no", "supplier_po_no", "material_name"],
            set_={
                # ... (leave the entire set_ dict exactly as it is) ...
            },
        )
```

**(f)** Replace `poll_and_ingest` so it takes a config (defaulting to the legacy 102 config) and uses it:

```python
def poll_and_ingest(
    db: Session,
    cfg: CrmConfig | None = None,
    *,
    desk_label: str | None = None,
    trigger: str = "auto",
) -> dict[str, Any]:
    """Fetch a desk feed, keep generated POs, and bulk-upsert them. Failure-safe.

    `cfg` selects which CRM desk/credentials to use; when None, the legacy 102
    config (from CRM_* settings) is used so existing callers keep working. Writes
    go to whatever schema the ambient tenant context selects (caller wraps this in
    `use_company(...)` for non-default companies)."""
    if cfg is None:
        from .crm_config import get_crm_config
        cfg = get_crm_config(str(settings.CRM_DESK_ID or "102"), is_default=True)
    if not settings.CRM_INGEST_ENABLED or cfg is None:
        reason = "CRM_INGEST_ENABLED is false" if not settings.CRM_INGEST_ENABLED else "no CRM config"
        _log_run(status="DISABLED", trigger=trigger, message=reason)
        return {"ok": True, "status": "DISABLED", "message": reason}

    label = desk_label or cfg.desk_id
    t0 = time.time()
    try:
        feed = fetch_desk(cfg)
        generated = [r for r in feed if _is_generated(r)]
        rows = [map_row(r) for r in generated]
        created, updated, skipped = _bulk_upsert(db, rows)
    except Exception as exc:  # noqa: BLE001
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        _log_run(status="ERROR", trigger=trigger, desk=str(label),
                 duration_ms=int((time.time() - t0) * 1000), message=str(exc)[:1000])
        raise

    duration_ms = int((time.time() - t0) * 1000)
    _log_run(status="OK", trigger=trigger, desk=str(label),
             fetched=len(feed), generated=len(generated),
             created=created, updated=updated, skipped=skipped, errors=0,
             duration_ms=duration_ms)
    if created or updated:
        _auto_send_after_ingest(db)

    result = {
        "ok": True, "status": "OK", "desk": str(label),
        "fetched": len(feed), "generated": len(generated),
        "created": created, "updated": updated, "skipped": skipped, "errors": 0,
        "duration_ms": duration_ms,
        "records_processed": created + updated + skipped,
        "records_success": created + updated, "records_failed": 0,
    }
    log.info("[crm] ingest desk=%s fetched=%d generated=%d created=%d updated=%d skipped=%d in %dms",
             label, len(feed), len(generated), created, updated, skipped, duration_ms)
    return result
```

> Note: `_auto_send_after_ingest(db)` internally calls `send_ready_messages()` — Task 3 makes that schema-aware so the auto-send after a 101 ingest sends 101's queue.

- [ ] **Step 4: Run test to verify it passes**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_crm_ingest_config.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Run existing CRM/ingest tests to confirm 102 path intact**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/ -k "crm or ingest or procurement" -q`
Expected: same pass/fail as before this task (report counts; nothing newly failing).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/crm_ingest_service.py backend/tests/test_crm_ingest_config.py
git commit -m "feat(mc): config-driven CRM ingest + per-config token cache + portable upsert"
```

---

### Task 3: Mail-send worker — thread-safe schema propagation

**Files:**
- Modify: `backend/app/workers/mail_send_worker.py`
- Test: `backend/tests/test_mail_send_schema.py`

**Interfaces:**
- Consumes: `app.core.tenant.use_company`, `app.core.tenant.get_current_schema`.
- Produces:
  - `send_ready_messages(limit=None, *, schema: str | None = None) -> dict` — when `schema` is None it uses the ambient `get_current_schema()`; the resolved schema is captured and re-established inside every worker thread.
  - `_send_bucket(message_ids, schema)` — sets the tenant schema at the top of the thread (`with use_company(schema): ...`) so its `SessionLocal()` targets the right schema.

Why: `send_ready_messages` fans work out to a `ThreadPoolExecutor`. A `ContextVar` set by `use_company` in the caller thread is **not** visible in the pool's worker threads (they start with the default `public`). Without this, a per-company send would drain 102's `public` queue instead of the company's.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_mail_send_schema.py
import inspect
import unittest

from app.workers import mail_send_worker as w


class MailSendSchemaPlumbingTests(unittest.TestCase):
    def test_send_ready_messages_accepts_schema_kwarg(self):
        sig = inspect.signature(w.send_ready_messages)
        assert "schema" in sig.parameters

    def test_bucket_reestablishes_schema_in_thread(self):
        # _send_bucket must take a schema and enter use_company(schema) so the
        # thread's SessionLocal targets the right tenant.
        sig = inspect.signature(w._send_bucket)
        assert "schema" in sig.parameters
        src = inspect.getsource(w._send_bucket)
        assert "use_company" in src
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_mail_send_schema.py -v`
Expected: FAIL — `_send_bucket` has no `schema` param / no `use_company`.

- [ ] **Step 3: Write minimal implementation**

Add the import at the top of `mail_send_worker.py`:

```python
from ..core.tenant import use_company, get_current_schema
```

Change `_send_bucket` to take a `schema` and wrap its body:

```python
def _send_bucket(message_ids: list[int], schema: str) -> list[dict[str, Any]]:
    """Send a disjoint slice of messages over a SINGLE reused SMTP connection.

    Runs in its own thread with its own DB session. The tenant schema is passed in
    explicitly and re-established here because ContextVars do not cross thread
    boundaries — without this the thread's SessionLocal would target the default
    (public) schema."""
    with use_company(schema):
        results: list[dict[str, Any]] = []
        db: Session = SessionLocal()
        client: smtplib.SMTP | None = None
        try:
            # ... (leave the entire existing body of the for-loop / try / finally
            #      exactly as it is, just indented one level under `with use_company`)
            ...
        finally:
            if client is not None:
                try:
                    client.quit()
                except Exception:  # noqa: BLE001
                    pass
            db.close()
        return results
```

> Implementer: take the current `_send_bucket` body (everything after the docstring) and indent it under the new `with use_company(schema):` block. Do not change its logic.

Update the two call sites in `send_ready_messages` to pass the schema, and add the `schema` kwarg:

```python
def send_ready_messages(limit: int | None = None, *, schema: str | None = None) -> dict[str, Any]:
    ready, reason = _config_ready()
    if not ready:
        log.info("Mail send worker disabled: %s", reason)
        return {"enabled": False, "reason": reason, "attempted": 0, "results": []}

    active_schema = schema or get_current_schema()

    if limit is None:
        limit = int(getattr(settings, "MAIL_SEND_BATCH_LIMIT", 50) or 50)

    db: Session = SessionLocal()
    try:
        ids = list(
            db.scalars(
                select(CommunicationMessage.id)
                .where(
                    CommunicationMessage.direction == "OUTGOING",
                    CommunicationMessage.status == "READY",
                )
                .order_by(CommunicationMessage.created_at.asc())
                .limit(limit)
            ).all()
        )
    finally:
        db.close()

    if not ids:
        return {"enabled": True, "attempted": 0, "sent": 0, "results": [], "ran_at": datetime.utcnow().isoformat()}

    workers = max(1, min(int(getattr(settings, "SMTP_SEND_WORKERS", 4) or 4), len(ids)))
    results: list[dict[str, Any]] = []
    if workers == 1:
        results = _send_bucket(ids, active_schema)
    else:
        buckets = [b for b in (ids[i::workers] for i in range(workers)) if b]
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(buckets)) as ex:
            for res in ex.map(lambda b: _send_bucket(b, active_schema), buckets):
                results.extend(res)

    sent = sum(1 for r in results if r.get("status") == "SENT")
    return {
        "enabled": True, "attempted": len(ids), "sent": sent, "workers": workers,
        "results": results, "ran_at": datetime.utcnow().isoformat(),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_mail_send_schema.py tests/test_mail_send_retry.py -v`
Expected: `test_mail_send_schema.py` passes (2). `test_mail_send_retry.py` keeps its **pre-existing** 2 failures only (they predate this work — the `_send_bucket` signature change may require the pre-existing tests to pass `schema="public"`; if a mail_send_retry test calls `_send_bucket(ids)` directly and now errors on the missing arg, update that call to `_send_bucket(ids, "public")` — that is a test-only signature fix, not new behaviour).

- [ ] **Step 5: Commit**

```bash
git add backend/app/workers/mail_send_worker.py backend/tests/test_mail_send_schema.py
git commit -m "feat(mc): thread-safe tenant schema propagation in mail-send worker"
```

---

### Task 4: Per-company scheduler runners

**Files:**
- Modify: `backend/app/scheduler/jobs.py`
- Test: `backend/tests/test_scheduler_per_company.py`

**Interfaces:**
- Consumes: `company_service.list_active`, `app.core.tenant.use_company`, `crm_config.get_crm_config`, `send_ready_messages(schema=...)`.
- Produces:
  - `_active_companies() -> list[tuple[str, str, bool]]` — `(code, schema_name, is_default)` for active companies, read from the default (public) context. On any error returns `[("102", "public", True)]`-style fallback so a registry hiccup never stops jobs. (Use the actual default company if present.)
  - The following runners now loop over active companies, running the existing body under `use_company(schema)` and returning a `{code: result}` map: `crm_ingestion_runner`, `mail_send_runner`, `po_followup_mail_runner`, `auto_reply_runner`, `delay_risk_runner`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_scheduler_per_company.py
import unittest
from unittest.mock import patch

from app.scheduler import jobs


class PerCompanyRunnerTests(unittest.TestCase):
    def test_active_companies_fallback_to_default(self):
        # With no DB rows reachable, must still yield the default company.
        with patch.object(jobs, "_list_active_companies", side_effect=Exception("boom")):
            companies = jobs._active_companies()
        assert ("102", "public", True) in companies

    def test_crm_runner_loops_companies_and_wraps_schema(self):
        seen = []

        def fake_poll(db, cfg, *, desk_label=None, trigger="auto"):
            from app.core.tenant import get_current_schema
            seen.append((desk_label, get_current_schema()))
            return {"ok": True, "desk": desk_label}

        companies = [("102", "public", True), ("101", "company_101", False)]
        from app.services.crm_config import CrmConfig
        cfg = CrmConfig(base_url="http://x", desk_id="d", login_email="e", login_password="p", device_id="d")
        with patch.object(jobs, "_active_companies", return_value=companies), \
             patch.object(jobs.settings, "CRM_INGEST_ENABLED", True), \
             patch.object(jobs, "get_crm_config", return_value=cfg), \
             patch("app.services.crm_ingest_service.poll_and_ingest", side_effect=fake_poll):
            out = jobs.crm_ingestion_runner()
        # Each company ran under its own schema.
        assert dict(seen)["102"] == "public"
        assert dict(seen)["101"] == "company_101"
        assert set(out.keys()) == {"102", "101"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_scheduler_per_company.py -v`
Expected: FAIL — `_active_companies` / `_list_active_companies` / `get_crm_config` not present; runner returns a flat dict.

- [ ] **Step 3: Write minimal implementation**

In `backend/app/scheduler/jobs.py`, add imports near the top:

```python
from ..core.tenant import use_company
from ..services.crm_config import get_crm_config
```

Add the helpers (place above the runners):

```python
def _list_active_companies():
    """Read (code, schema_name, is_default) for active companies from the default
    (public) context. Isolated so tests can patch it."""
    from ..services import company_service
    db: Session = SessionLocal()
    try:
        return [(c.code, c.schema_name, c.is_default) for c in company_service.list_active(db)]
    finally:
        db.close()


def _active_companies() -> list[tuple[str, str, bool]]:
    try:
        rows = _list_active_companies()
        if rows:
            return rows
    except Exception:  # noqa: BLE001
        log.exception("Failed to list active companies; falling back to default")
    return [("102", "public", True)]
```

Replace `crm_ingestion_runner`:

```python
def crm_ingestion_runner() -> dict[str, Any]:
    """Poll each active company's CRM desk feed and upsert into its schema."""
    if not getattr(settings, "CRM_INGEST_ENABLED", False):
        return {"enabled": False, "status": "DISABLED"}
    from ..services import crm_ingest_service

    out: dict[str, Any] = {}
    for code, schema, is_default in _active_companies():
        cfg = get_crm_config(code, is_default=is_default)
        if cfg is None:
            out[code] = {"status": "SKIPPED", "reason": "no CRM config"}
            continue
        with use_company(schema):
            db: Session = SessionLocal()
            try:
                out[code] = crm_ingest_service.poll_and_ingest(db, cfg, desk_label=code)
            except Exception:  # noqa: BLE001
                db.rollback()
                log.exception("crm ingest failed for company %s", code)
                out[code] = {"ok": False, "status": "ERROR"}
            finally:
                db.close()
    return out
```

Replace `mail_send_runner`:

```python
def mail_send_runner() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for code, schema, _ in _active_companies():
        with use_company(schema):
            out[code] = mail_send_worker.send_ready_messages(schema=schema)
    return out
```

Replace `po_followup_mail_runner` (wrap its existing body per company):

```python
def po_followup_mail_runner() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for code, schema, _ in _active_companies():
        with use_company(schema):
            db: Session = SessionLocal()
            try:
                out[code] = po_followup_mail_service.queue_due_po_followups(db)
            except Exception:  # noqa: BLE001
                db.rollback()
                log.exception("po_followup_mail_runner failed for %s", code)
                out[code] = {"enabled": True, "queued": 0, "skipped": 0, "error": True}
            finally:
                db.close()
    return out
```

Replace `delay_risk_runner` (wrap its body per company, same pattern, calling `ai_insights_service.rescore_all(db)`):

```python
def delay_risk_runner() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for code, schema, _ in _active_companies():
        with use_company(schema):
            db: Session = SessionLocal()
            try:
                out[code] = ai_insights_service.rescore_all(db)
            except Exception:  # noqa: BLE001
                db.rollback()
                log.exception("delay_risk_runner failed for %s", code)
                out[code] = {"updated": 0, "error": True}
            finally:
                db.close()
    return out
```

Replace `auto_reply_runner` similarly — wrap the entire existing candidate-scan/loop body in `for code, schema, _ in _active_companies(): with use_company(schema):`, opening/closing the `db` inside the loop, and returning `{code: {...}}`. (Keep the inner draft-creation logic identical.)

- [ ] **Step 4: Run test to verify it passes**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_scheduler_per_company.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Run scheduler/engine tests for regressions**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/ -k "scheduler or engine or agent_dispatch or followup" -q`
Expected: baseline unchanged (report counts).

- [ ] **Step 6: Commit**

```bash
git add backend/app/scheduler/jobs.py backend/tests/test_scheduler_per_company.py
git commit -m "feat(mc): per-company scheduler runners (ingest/send/followup/reply/risk)"
```

---

### Task 5: Shared-inbox reply attribution

**Files:**
- Modify: `backend/app/workers/mail_fetch_worker.py`
- Test: `backend/tests/test_mail_fetch_attribution.py`

**Interfaces:**
- Consumes: `company_service.list_active`, `app.core.tenant.use_company`, `communication_message_service.find_supplier_by_email`.
- Produces:
  - `resolve_company_schema_for_sender(sender_email: str | None) -> str` — returns the schema of the first active company whose suppliers include `sender_email` (checked under each company's schema); falls back to the default company's schema when none match (or on error).
  - `_process_one(...)` is now called under `use_company(resolve_company_schema_for_sender(sender))` so each reply is stored in the owning company's schema. The single shared-inbox fetch stays as-is (one mailbox, Plan 1 decision); only the per-message routing is added.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_mail_fetch_attribution.py
import unittest
from unittest.mock import patch

from app.workers import mail_fetch_worker as f


class AttributionTests(unittest.TestCase):
    def test_resolves_default_when_unknown(self):
        with patch.object(f, "_active_companies", return_value=[("102", "public", True), ("101", "company_101", False)]), \
             patch("app.services.communication_message_service.find_supplier_by_email", return_value=(None, None)):
            assert f.resolve_company_schema_for_sender("nobody@x.com") == "public"

    def test_routes_to_company_owning_the_sender(self):
        # 101 owns the sender; 102 does not.
        def fake_find(db, email):
            from app.core.tenant import get_current_schema
            if get_current_schema() == "company_101":
                return (5, "ACME 101")
            return (None, None)

        with patch.object(f, "_active_companies", return_value=[("102", "public", True), ("101", "company_101", False)]), \
             patch("app.services.communication_message_service.find_supplier_by_email", side_effect=fake_find):
            assert f.resolve_company_schema_for_sender("orders@acme101.com") == "company_101"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_mail_fetch_attribution.py -v`
Expected: FAIL — `resolve_company_schema_for_sender` / `_active_companies` not defined.

- [ ] **Step 3: Write minimal implementation**

Add imports + helpers to `mail_fetch_worker.py`:

```python
from ..core.tenant import use_company
from ..services import communication_message_service as _msg_lookup  # find_supplier_by_email
```

```python
def _active_companies() -> list[tuple[str, str, bool]]:
    """(code, schema_name, is_default) for active companies, default first."""
    from ..services import company_service
    db: Session = SessionLocal()
    try:
        rows = [(c.code, c.schema_name, c.is_default) for c in company_service.list_active(db)]
    except Exception:  # noqa: BLE001
        log.exception("attribution: failed to list companies; using default only")
        rows = []
    finally:
        db.close()
    if not rows:
        return [("102", "public", True)]
    # default company first so it wins ties / is the fallback
    return sorted(rows, key=lambda r: (not r[2], r[0]))


def _default_schema_from(companies: list[tuple[str, str, bool]]) -> str:
    for _code, schema, is_default in companies:
        if is_default:
            return schema
    return companies[0][1] if companies else "public"


def resolve_company_schema_for_sender(sender_email: str | None) -> str:
    """Which company owns this sender? Suppliers are disjoint across companies, so
    the first company whose supplier_master contains the sender wins. Falls back to
    the default company's schema when unknown."""
    companies = _active_companies()
    if sender_email:
        for _code, schema, _is_default in companies:
            try:
                with use_company(schema):
                    db: Session = SessionLocal()
                    try:
                        supplier_id, _name = _msg_lookup.find_supplier_by_email(db, sender_email)
                    finally:
                        db.close()
                if supplier_id is not None:
                    return schema
            except Exception:  # noqa: BLE001
                log.exception("attribution lookup failed for schema %s", schema)
    return _default_schema_from(companies)
```

In `_fetch_imap_messages` and `_fetch_pop3_messages`, wrap the `_process_one` call so each message is processed under its owning company's schema. Replace the per-message processing block (both places) with:

```python
            parsed_preview = email.message_from_bytes(bytes(raw_msg)) if isinstance(raw_msg, (bytes, bytearray)) else None
            sender = None
            if parsed_preview is not None:
                from email.utils import parseaddr as _pa
                sender = _pa(_decode(parsed_preview.get("From")))[1] or None
            schema = resolve_company_schema_for_sender(sender)
            with use_company(schema):
                pdb: Session = SessionLocal()
                try:
                    result = _process_one(pdb, raw_uid, bytes(raw_msg))
                finally:
                    pdb.close()
            result["company_schema"] = schema
            processed.append(result)
```

> The outer `db` passed into `_fetch_*_messages` is no longer used for `_process_one` (each message gets its own schema-scoped session). Leave the `db` parameter in place (other calls/signature) but the processing uses `pdb`. The duplicate-check inside `_process_one` (`message_exists`) now runs per-schema, which is correct — a reply is stored once, in its owning company.

- [ ] **Step 4: Run test to verify it passes**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_mail_fetch_attribution.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Regression on mail-fetch tests**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/ -k "mail_fetch or customer_mail or reply" -q`
Expected: baseline unchanged (report counts).

- [ ] **Step 6: Commit**

```bash
git add backend/app/workers/mail_fetch_worker.py backend/tests/test_mail_fetch_attribution.py
git commit -m "feat(mc): shared-inbox reply attribution routes each reply to its company"
```

---

### Task 6: Per-schema column evolution on startup

**Files:**
- Modify: `backend/app/core/schema_evolve.py` (add a schema-scoped variant)
- Modify: `backend/app/seed.py` (`ensure_company_schemas` also evolves columns per schema)
- Test: `backend/tests/test_schema_evolve_per_company.py`

**Interfaces:**
- Consumes: `create_company_schema` (Plan 1), `ensure_columns` (existing).
- Produces:
  - `ensure_columns_in_schema(engine, schema: str) -> list[str]` — runs the same ADD-COLUMN evolution but against tables in `schema` (Postgres only; no-op on SQLite). Lets a company schema pick up columns added to models after its initial `LIKE` copy.
  - `seed.ensure_company_schemas(db)` calls it for each non-public company after creating the schema.

Why: `create_company_schema` copies structure once. When a later release adds a column to a per-company model, `ensure_columns` (default schema only) evolves `public`/102 but not `company_101`. This closes that drift.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_schema_evolve_per_company.py
import unittest

from app.core.schema_evolve import ensure_columns_in_schema
from app.database import engine


class PerSchemaEvolveTests(unittest.TestCase):
    def test_noop_on_sqlite(self):
        # SQLite has no schemas → must be a safe no-op returning [].
        assert ensure_columns_in_schema(engine, "company_101") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_schema_evolve_per_company.py -v`
Expected: FAIL — `ImportError: cannot import name 'ensure_columns_in_schema'`.

- [ ] **Step 3: Write minimal implementation**

Add to `backend/app/core/schema_evolve.py`:

```python
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
```

Update `seed.ensure_company_schemas` (Plan 1) to also evolve columns:

```python
def ensure_company_schemas(db: Session) -> list[str]:
    from .database import create_company_schema, engine
    from .core.schema_evolve import ensure_columns_in_schema
    from .services import company_service

    done: list[str] = []
    for company in company_service.list_active(db):
        if company.schema_name and company.schema_name != "public":
            created_tables = create_company_schema(company.schema_name)
            evolved = ensure_columns_in_schema(engine, company.schema_name)
            if created_tables or evolved:
                done.append(company.schema_name)
    return done
```

- [ ] **Step 4: Run test to verify it passes**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_schema_evolve_per_company.py tests/test_seed_company_schema.py -v`
Expected: PASS (2 passed; the Plan 1 seed test still returns `[]` on SQLite).

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/schema_evolve.py backend/app/seed.py backend/tests/test_schema_evolve_per_company.py
git commit -m "feat(mc): per-schema column evolution so company schemas don't drift"
```

---

### Task 7: Full-suite verification + docs

**Files:**
- Modify: `docs/progress.md` (append a Plan 2 phase note)

- [ ] **Step 1: Run the full backend suite**

Run: `backend/.venv/Scripts/python.exe -m pytest -q`
Expected: only the 2 pre-existing `test_mail_send_retry` failures; all new Plan 2 tests green. Report exact counts.

- [ ] **Step 2: Append a Plan 2 note to `docs/progress.md`**

Add a short phase entry summarising: per-company CRM config (env), config-driven ingest + portable upsert, thread-safe per-company mail send, per-company scheduler runners, shared-inbox reply attribution, per-schema column evolution. Note the env keys `CRM_101_*` needed to activate 101's ingestion.

- [ ] **Step 3: Commit**

```bash
git add docs/progress.md
git commit -m "docs(mc): Plan 2 per-company jobs/CRM/attribution phase note"
```

---

## Self-Review

**1. Spec coverage (against the design doc's Plan 2 scope):**
- Per-company CRM ingest (desk 101) → Tasks 1, 2, 4. ✅
- Per-company scheduler loop → Task 4. ✅
- `index_elements` upsert (LIKE-schema portability) → Task 2. ✅
- Thread-safety of tenant context in the send worker → Task 3. ✅
- Shared-inbox reply attribution → Task 5. ✅
- Per-schema column drift → Task 6. ✅
- 102 path unchanged → enforced in every task (default config + ambient schema = `public`). ✅

**2. Placeholder scan:** Tasks 3, 4, 5 say "leave the existing body as-is / indent it" rather than re-printing long unchanged loops — that's a deliberate *modify-in-place* instruction naming the exact wrapper, not a missing implementation. All *new* code is shown in full. No TBD/TODO.

**3. Type consistency:** `CrmConfig`, `get_crm_config(code, *, is_default)`, `get_token(cfg)`, `fetch_desk(cfg)`, `poll_and_ingest(db, cfg, *, desk_label, trigger)`, `send_ready_messages(..., schema=)`, `_send_bucket(ids, schema)`, `_active_companies()`, `resolve_company_schema_for_sender()`, `ensure_columns_in_schema(engine, schema)` are named identically across defining and consuming tasks. ✅

**Risk note:** Tasks 2–5 modify live-production code paths (102's CRM ingest + mail workers). Every task keeps the default company on the exact same values/branch and adds a per-company loop around it; run the targeted regression sets (Steps in each task) plus the full suite (Task 7) before merge.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-07-04-multi-company-portal-plan2-per-company-jobs.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — fresh subagent per task, review between tasks.

**2. Inline Execution** — batch execution with checkpoints.

**Which approach?**

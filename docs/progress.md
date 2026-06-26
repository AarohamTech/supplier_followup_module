# Progress Log — Persistence & Role-Based Users

> Living document. Every decision and every meaningful change is appended here,
> newest phase at the bottom. Secrets (DB password, JWT secret) live only in the
> gitignored `backend/.env` — never in this file.

---

## Goal

Add to the Supplier Follow-up module:

1. **Persistence** — move the database from local SQLite to a hosted **Supabase
   Postgres** instance so data survives restarts and is shared across users.
2. **Users with roles** — authentication (login) plus **role-based access
   control (RBAC)** so different people see/do different things.
3. Keep everything **modular** — small, single-responsibility modules that slot
   into the existing FastAPI + Next.js structure without rewrites.

---

## Decisions (2026-06-16)

| # | Question | Decision | Rationale |
|---|----------|----------|-----------|
| 1 | Role set | **4-tier: `admin`, `manager`, `user`, `viewer`** | Matches the architecture doc; gives an approver tier (manager) without being heavy. |
| 2 | Phase scope | **Full stack this phase** | Backend auth/RBAC **and** the Next.js login + route guard + role-gated UI. |
| 3 | Supabase rollout | **Test connection (read-only) → then `create_all`** | `create_all` only adds missing tables; it never drops existing data. |

### Role model

Hierarchy (each role includes the powers of the ones below it):

```
admin  (4)  → everything, incl. user management
manager(3)  → approve/send mail, escalate, edit settings/automation
user   (2)  → operational: create drafts, tasks, triage, edit records
viewer (1)  → read-only
```

Permission matrix (target):

| Capability | viewer | user | manager | admin |
|------------|:------:|:----:|:-------:|:-----:|
| Read dashboards / lists / history | ✅ | ✅ | ✅ | ✅ |
| Create/edit drafts, tasks, triage | — | ✅ | ✅ | ✅ |
| Send mail / approve / escalate | — | — | ✅ | ✅ |
| Edit settings, cron, automation toggles | — | — | ✅ | ✅ |
| Manage users & roles | — | — | — | ✅ |

> Implementation note: **the matrix is now enforced** (Phase 3, round 2). A
> method-aware router guard (`require_writer_for_writes`) makes `viewer` read-only
> and requires `user`+ for any write; `require_manager` gates send/approve actions
> (generate, generate-po, auto-queue, mail-history status, comm-hub send/escalate,
> settings writes); `admin` gates user management. Verified live across all tiers.

---

## Architecture (modular layout)

### Backend (`backend/app/`)

| Module | Responsibility |
|--------|----------------|
| `core/roles.py` | Role constants, ranking, `role_at_least()` helper. No deps. |
| `models/user.py` | `User` ORM model (email, hashed_password, role, is_active). |
| `core/security.py` | bcrypt password hash/verify + JWT encode/decode. |
| `core/deps.py` | `get_current_user`, `require_roles(...)` RBAC dependencies. |
| `schemas/user.py` | Pydantic DTOs: `UserOut`, `UserCreate`, `UserUpdate`, `Token`, `LoginRequest`. |
| `services/user_service.py` | User CRUD + `authenticate()`. No FastAPI imports. |
| `routers/auth.py` | `POST /api/auth/login`, `GET /api/auth/me`, `POST /api/auth/change-password`. |
| `routers/users.py` | Admin user management CRUD under `/api/users`. |

`config.py` already declares `JWT_SECRET` / `JWT_ALGORITHM` /
`ACCESS_TOKEN_EXPIRE_MINUTES`; `database.py` already switches SQLite↔Postgres on
`DATABASE_URL`. `requirements.txt` already ships `python-jose`, `passlib[bcrypt]`,
`psycopg2-binary`. So no new dependencies are needed.

### Frontend (`frontend/`)

| Module | Responsibility |
|--------|----------------|
| `lib/auth.tsx` | Auth context: token (localStorage), `user`, `login`, `logout`. |
| `lib/api.ts` | Inject `Authorization: Bearer`; on 401 → clear + redirect to `/login`. |
| `components/layout/AppShell.tsx` | Client shell: gates the app, shows login bare, else Topbar+Sidebar. |
| `app/login/page.tsx` | Login form. |
| `app/admin/users/page.tsx` | Admin-only user management UI. |
| `components/layout/Sidebar.tsx` / `Topbar.tsx` | Role-gated nav + real user + logout. |

---

## Progress

### Phase 0 — Setup _(done, 2026-06-16)_
- [x] Studied current persistence/config/auth surface.
- [x] Created this `docs/progress.md`.
- [x] Local Python env: created `backend/.venv` (conda Python 3.13) + installed requirements.

### Phase 1 — Backend persistence + auth + RBAC _(done, 2026-06-16)_
- [x] Supabase connection verified (PostgreSQL 17.6, direct host, port 5432, `sslmode=require`).
- [x] `core/roles.py`, `models/user.py`, `core/security.py`, `core/deps.py`,
      `schemas/user.py`, `services/user_service.py`, `routers/auth.py`, `routers/users.py`.
- [x] `main.py`: auth + webhooks open; `users` admin-guarded; all business routers
      require login; manager+ guards on send/escalate + settings writes.
- [x] Default admin seeded from env (`SEED_ADMIN_EMAIL`). Verified bcrypt verify=True.
- [x] Created 17 app tables on Supabase; admin user present (role=admin).

**Decisions & gotchas discovered during Phase 1:**
- **Wrong DB first / shared-DB collision:** the original URL pointed at a project
  whose `public` schema already held another app's 15+ tables incl. a foreign
  `users` table (no `hashed_password`) → collision. User supplied a **new dedicated
  DB** (`db.wwdxxnzwzvoxsscabugq…`), confirmed empty. We point at it now.
  - _Stray cleanup TODO:_ ~16 empty tables were created in the OLD project's DB
    before the switch; offered to drop them (only the ones we created).
- **Schema isolation feature:** added optional `DB_SCHEMA` env var → pins the
  connection `search_path` so all tables live in a dedicated schema. Left **empty**
  (uses `public`) for the dedicated DB, but available if the DB is ever shared.
- **psycopg2 on Python 3.13:** pinned `2.9.9` has no cp313 wheel → bumped to
  `>=2.9.10`.
- **passlib is broken with bcrypt 5.x on 3.13** → replaced `passlib[bcrypt]` with
  the `bcrypt` library used directly in `core/security.py`.

### Phase 2 — Frontend login + RBAC UI _(done, 2026-06-16)_
- [x] `lib/auth-token.ts` (shared token store), `lib/auth.tsx` (AuthProvider + `useAuth` + `roleAtLeast`).
- [x] `lib/api.ts`: injects `Authorization: Bearer`, clears token + redirects on 401; added
      `login`/`me`/`changePassword` + admin user-management calls.
- [x] `components/layout/AppShell.tsx`: gates the app — `/login` renders bare, every other
      route requires a user (else redirect to `/login`). `layout.tsx` now wraps in
      `AuthProvider` + `AppShell`.
- [x] `app/login/page.tsx` login form.
- [x] `Sidebar` role-gates items (Settings = manager+, Users = admin); `Topbar` shows the real
      user + role + logout.
- [x] `app/admin/users/page.tsx`: list/create/role-change/activate/reset-password/delete.

### Verification (2026-06-16)
- Backend (live, against Supabase) — all passed:
  - admin login → token; `/me` → admin; no-token → **401**; admin list-users → **200**;
    create viewer → **201**; viewer read → **200**; viewer list-users → **403**;
    viewer send-mail → **403**; bad password → **401**.
- Frontend: `tsc --noEmit` clean; `next build` succeeded (14/14 routes incl. `/login`,
  `/admin/users`).
- Startup seed is idempotent (re-running left admin untouched; templates/procurement seeded).

### Default credentials (change after first login)
- `admin@example.com` / `ChangeMe!123` (from `SEED_ADMIN_*` in `.env`).
- A `viewer@example.com` / `ViewerPass1` test user was created during verification.

### How to run
```
# backend (from backend/)
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
# frontend (from frontend/)
npm run dev
```

### Phase 3 — Logic-gap review + fixes _(in progress, 2026-06-16)_
- Ran a full review → **45 findings** in [REVIEW_FINDINGS.md](REVIEW_FINDINGS.md) (the live backlog/checklist).
- Round 1 fixes committed (clear-cut, no decisions): #1 escape import (PO mail was fully
  broken — restored), #8 duplicate-send guard, #10 reuse-of-failed-drafts, #12 escalation KPI,
  #13 customer-mail→PO link, #40 reply key, #41 login flash/401 toast.
- Verified: 35/35 backend tests pass; frontend `tsc` clean.
- Round 2 fixes committed (decisions made): #2 RBAC enforced (viewer read-only, user writes,
  manager send/approve, admin user-mgmt — live-tested); #5 auto-reply now a DRAFT (needs approval);
  #3 webhooks require `X-Webhook-Secret`; #4 left as-is by choice.
- Round 3 fixes committed (engine decisions): #6 RED day counts from when it went late
  (`red_since` column + Supabase ALTER); #7 critical/AI orders auto-chased (no more freeze);
  #9 follow-up count once per email; #15 "Save & Notify" removed.
- Round 4 fixes committed (clear P2/P3 basics): #19 wrong-PO match, #25 schema-evolve now
  Postgres-aware (auto-adds columns), #39 N+1, #43 DB_SCHEMA validation, #45 demo data gated to
  DEBUG, #30 store error split, #32/#33 customer-workspace selection/refresh.
- Round 5: built the **#14 customer reply feature** (Phase 1+2+approvals) — reply/send, persisted
  conversation, server smart-draft from order data, and a manager `/approvals` page for auto-reply
  drafts. Plugged in real POP3/SMTP creds (tested OK). Scheduler ON; auto PO-blast OFF.
- **Next:** remaining P2/P3 backlog in REVIEW_FINDINGS.md (several need a quick product decision — *).

### Phase 4 — AI / LLM + HTML mail _(2026-06-16)_
- **Dedicated AI module** (kept separate so endpoints don't mix): `services/ai_service.py`
  (single place that talks to the LLM) + `routers/ai.py` under its own `/api/ai/*` prefix.
  OpenAI-compatible client pointed at **NVIDIA NIM** (`gpt-oss-120b`), config via `LLM_*` env.
- **Assistant page** (`/assistant`, all roles) — chatbot via `POST /api/ai/chat`. Agentic tools later.
- **HTML emails:** customer replies now send a branded HTML body (plain-text fallback kept).
- **AI reply drafts:** `POST /api/customer-mails/{id}/draft-reply?ai=true` polishes the reply with
  the LLM, grounded in order data; **default is the instant deterministic template** (no LLM call).
  Frontend shows the template instantly + an "Improve with AI" button (on-demand, to respect the
  free-tier rate limit).
- **Speed/robustness:** `reasoning_effort=low` + token cap → ~2-5s chat; 30s timeout, no retry,
  graceful fallback to the template on timeout.
- ⚠️ The NVIDIA **free tier rate-limits** bursts → calls can queue/timeout; the fallback covers it.
  Rotate the NVIDIA key (shared in chat). Verified: chat live; 35/35 tests; frontend build (16 routes).

### Follow-ups / not in this phase
- Tighten per-endpoint RBAC to the full matrix (currently: auth everywhere + admin on user
  mgmt + manager+ on send/escalate & settings writes; other mutations are auth-only).
- Self-service "change password" UI (endpoint exists: `POST /api/auth/change-password`).
- Optional: drop the ~16 stray empty tables left in the OLD project's DB.
- Optional: switch table creation to Alembic migrations (currently `create_all` on startup).
- Rotate the Supabase password + set a fresh `JWT_SECRET` for any shared/prod environment.

### Phase 5 — Agentic AI + RAG memory + insights _(2026-06-17)_
Tier 1 + Tier 2 of the AI follow-up roadmap. All AI lives under `/api/ai/*`; every feature is
flag-gated and degrades gracefully (LLM off → templates/heuristics; RAG off → SQL-only agent).

- **Agentic Assistant** — `POST /api/ai/chat` now tool-calls the live DB. Tools in
  `services/ai_tools_service.py`: `get_overview`, `list_red_pos`, `get_po_status`,
  `search_supplier`, `get_mail_thread`, and `search_knowledge` (RAG; only exposed when RAG on).
  Loop in `ai_service.chat_with_tools()`; the assistant page shows which tools were used.
- **Auto-triage** (`AI_TRIAGE_ENABLED`) — incoming customer mails classified on fetch
  (category / urgency / action / summary) → persisted on `customer_mails.ai_*`. LLM with a
  keyword-heuristic fallback. On-demand: `POST /api/ai/triage/customer-mail/{id}`. Badges in the
  mail queue + a triage banner + "Triage"/"Summarize" buttons in the workspace.
- **AI PO follow-up** (`AI_PO_FOLLOWUP_ENABLED`) — RED/BLACK follow-up bodies polished by the LLM,
  grounded in PO facts (+ RAG precedent of how the supplier replied before). Keeps the structured
  material + reply tables; falls back to the template on any error.
- **Predictive delay risk** — heuristic scorer (`ai_insights_service.compute_delay_risk`) writes
  `procurement_records.risk_score/risk_band/risk_reason/risk_scored_at`. Cron `delay_risk_cron`
  (60 min) + `POST /api/ai/insights/delay-risk/rescore`. Listed via `GET .../delay-risk`.
- **Supplier scorecards** — `GET /api/ai/insights/suppliers` (grouped-query heuristic: signal mix,
  overdue, avg follow-ups, reply rate → score + A–D grade).
- **Conversation summary** — `POST /api/ai/summary/customer-mail/{id}` summarises mail + replies.
- **RAG memory (pgvector)** — `services/vector_store.py` (raw SQL, **Postgres-only**, no-op on
  SQLite, no new Python dep), `embeddings_service.py` (NVIDIA `nv-embedqa-e5-v5`, 1024-dim,
  input_type-aware), `knowledge_indexer.py` (embed mails/replies on fetch + backfill). Cron
  `knowledge_index_cron` (30 min). `GET /api/ai/memory/stats`, `POST /api/ai/memory/backfill`.
- **Frontend** — new `/insights` page (delay-risk table + supplier scorecards + memory status &
  backfill), sidebar "AI Insights", triage badges/summary in customer mails, tool chips on the
  assistant. `lib/api.ts` + `lib/types.ts` extended.
- **New cols** added online by `schema_evolve` (Postgres): `customer_mails.ai_*`,
  `procurement_records.risk_*`. Vector table created by `vector_store.ensure_store()` on startup
  when `RAG_ENABLED`.
- **Verified:** 35/35 backend tests; `tsc --noEmit` clean; isolated SQLite smoke test (risk,
  scorecards, triage, all agent tool executors); **live NVIDIA tool-calling confirmed** (called
  `list_red_pos`, correct grounded answer). Free-tier 70B tool-calling is ~30-40s/round →
  `LLM_AGENT_TIMEOUT_SECONDS=60` for the agent path (triage/drafts stay fail-fast at 30s).

#### To enable on EC2 (env additions — see `backend/example.env`)
- Agentic chat is **on by default** once `LLM_ENABLED=true` (already set).
- Triage/PO-AI: set `AI_TRIAGE_ENABLED=true` / `AI_PO_FOLLOWUP_ENABLED=true`.
- RAG: set `RAG_ENABLED=true` (Postgres only). `EMBED_API_KEY` blank reuses `LLM_API_KEY`. The
  Supabase **session pooler** is fine for pgvector; `ensure_store()` runs `CREATE EXTENSION vector`.
  After enabling, call `POST /api/ai/memory/backfill` once (manager) to embed existing mail.

### Phase 6 — Supplier Portal + supplier logins + ASN _(2026-06-26)_
Opened the system to **external suppliers** (it was internal-staff-only) with three additions.

- **Account model** — `users.supplier_id` (nullable FK) now discriminates accounts:
  NULL → internal staff (unchanged 4-tier RBAC); set → a `role="supplier"` portal account scoped
  to that supplier. `supplier` is a known role at **rank 0** (never satisfies a staff guard). New
  `users.must_change_password` flag. Both columns auto-added to Supabase by `schema_evolve`.
- **Guards** (`core/deps.py`) — `get_current_staff` (rejects supplier accounts) now backs the
  internal `/api/*` business + AI routers, and `require_writer_for_writes` rejects suppliers on
  **all** methods (closes the prior read-leak where any logged-in user could GET). `get_current_supplier`
  backs the new `/api/portal/*` surface. Verified: supplier→`/api/procurement` 403; staff→`/api/portal/*` 403.
- **Login provisioning** (`services/supplier_account_service.py`) — saving an Email Master mapping
  reconciles **TO** emails → one supplier login each (temp password, force-change), emails branded
  credentials (reuses `queue_outgoing_message`+`send_message_now`+`brand_email`; no-ops if SMTP off,
  temp passwords also returned to the admin). Removing a TO email deactivates its login (never deleted);
  staff/other-supplier emails are skipped as conflicts. Admin reset via `/api/supplier-accounts/{id}/reset-password`.
- **ASN feature** (`models/asn.py`, `services/asn_service.py`, `routers/portal.py` + `routers/asns.py`)
  — full shipment-tracking lifecycle (DRAFT→SUBMITTED→DISPATCHED→IN_TRANSIT→AT_CUSTOMS→INBOUND_HUB→
  OUT_FOR_DELIVERY→DELIVERED, +CANCELLED), progress %, alert flag, and a per-leg events timeline.
  Suppliers create/advance ASNs against their POs; staff see all ASNs at `/api/asns`. A PO counts as
  **Completed** once it has a DELIVERED ASN (drives the portal dashboard counts).
- **Frontend** — `AppShell` branches on account type: suppliers get a dedicated `SupplierShell`
  (Dashboard, My POs, ASN Portal) and a forced first-login change-password gate; staff get the
  existing app plus a new **Shipments (ASN)** page. Email Master surfaces the provisioning result +
  a per-supplier **Supplier Logins** panel (reset/activate). New `APP_BASE_URL` env (optional; used in
  the credential email link, falls back to the first CORS origin).
- **Verified** — 38/38 backend tests (the 2 `mail_send_retry` failures pre-date this work — stale tests
  from the concurrent-SMTP refactor); new `tests/test_supplier_portal.py` (roles, ASN lifecycle/summary/
  completion, provisioning); a hermetic TestClient smoke (29/29) over the real HTTP surface; frontend
  `tsc --noEmit` clean + `next build` (24 routes incl. `/portal`, `/portal/asn`, `/portal/pos`, `/asns`).
  DEBUG seed adds a demo supplier login (`orders@superbtools.example.com` / `Supplier!123`) + mapping + ASNs.

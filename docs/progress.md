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
- **Next:** plan #14 (customer reply feature). Remaining P2/P3 backlog tracked in REVIEW_FINDINGS.md
  (several need a quick product decision — marked with *).

### Follow-ups / not in this phase
- Tighten per-endpoint RBAC to the full matrix (currently: auth everywhere + admin on user
  mgmt + manager+ on send/escalate & settings writes; other mutations are auth-only).
- Self-service "change password" UI (endpoint exists: `POST /api/auth/change-password`).
- Optional: drop the ~16 stray empty tables left in the OLD project's DB.
- Optional: switch table creation to Alembic migrations (currently `create_all` on startup).
- Rotate the Supabase password + set a fresh `JWT_SECRET` for any shared/prod environment.

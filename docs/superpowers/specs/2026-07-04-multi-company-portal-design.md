# Multi-Company Portal — Design Spec

> Add a second company (**101 "Enterprise"**) alongside the existing
> **102 "Hariom Tech" / H-Connect**, served by the **same** application. A staff
> user picks a company at login (or switches in-app); each company's business data
> is fully isolated in its own Postgres schema; 101 is skinned light-blue. No
> second server, no rewrite — the app code stays identical, only *which schema a
> request reads/writes* changes.

- **Date:** 2026-07-04
- **Status:** Approved design → ready for implementation plan
- **Scope owner:** Chinmay Pisal
- **Related:** `docs/progress.md`, `docs/ARCHITECTURE.md`, `backend/app/database.py`,
  `backend/app/core/config.py`, `backend/app/core/security.py`, `backend/app/core/deps.py`

---

## 1. Goal & non-goals

**Goal.** Run companies **101 (Enterprise)** and **102 (Hariom Tech)** from one
deployment. Everything a user sees and can do is identical between them; only the
data, the branding (name + light-blue accent), and the data sources (CRM desk,
eventually mailbox) differ. Any staff member can move between the two.

**Non-goals (explicitly out of scope for this spec):**

- **Per-user personal mailboxes** ("send/receive as each individual user" via
  per-user SMTP/IMAP). This was explored and **dropped**. Mail stays at the
  **company** level. (Recorded here so it isn't silently reintroduced.)
- **Per-company access restrictions** for staff. Decision: *every staff account can
  enter both companies*. There is no "101-only employee" gate in v1.
- A **dedicated mailbox for 101**. 101 shares 102's central mailbox for now
  (see §7). Wiring a separate mailbox later is a config change, not a redesign.
- A **third+ company**. The design supports N companies (add a `companies` row + a
  schema), but only 101 + 102 are in scope now.

---

## 2. Decisions (from brainstorming)

| # | Question | Decision |
|---|----------|----------|
| 1 | How do 101 & 102 run under the hood? | **One app, pick company at login.** Schema-per-company on the single Supabase DB. Reuses the existing `DB_SCHEMA` / `search_path` mechanism, made per-request. Lowest risk, fits the 2 GB box. |
| 2 | How do staff accounts work across companies? | **One shared account per person; everyone can enter both.** `users` stays a single global table. No per-company access control. |
| 3 | Where do 101's POs come from? | **101's own CRM desk feed** (e.g. desk 101) with its own credentials, ingested alongside 102's. Creds can be added later; 101 starts empty until then. |
| 4 | How does 101 handle email? | **Shares 102's central mailbox for now.** Outbound sends fine; inbound replies are attributed to a company by matching the sender to that company's (disjoint) suppliers. Dedicated 101 mailbox deferred. |
| 5 | 102 data placement | **102 stays in the `public` schema — no migration.** 101 gets a new `company_101` schema. |
| 6 | In-app company switch | **Yes — a top-bar company switcher** for staff (re-issues the token), in addition to the login-time picker. |
| 7 | Company display names | **"Enterprise" (101)** and **"Hariom Tech" (102)**. |
| 8 | Per-user personal email identity | **Dropped** (see §1 non-goals). |

---

## 3. Architecture overview

```
                         ┌─ login: pick company ─┐
   staff user  ─────────►│  Enterprise (101)     │
   (one shared account)  │  Hariom Tech (102)    │
                         └───────────┬───────────┘
                                     │ JWT carries company_id
                                     ▼
                        FastAPI (single app, business code unchanged)
                                     │ per-request middleware:
                                     │   SET search_path = <company schema>, public
                        ┌────────────┴─────────────┐
                        ▼                           ▼
              schema: public                schema: company_101
        (102 business data +          (101 business data —
         shared `users`, `companies`)   its own suppliers/POs/mail/…)
```

One process, one database, two schemas. The only new machinery is a **tenant
resolver** that turns the JWT's `company_id` into the correct `search_path` for the
duration of a request (and per company inside background jobs).

---

## 4. Data model & schema isolation

### 4.1 Shared vs per-company tables

**Shared (live in `public`, one copy for the whole system):**

- `users` — staff identity (one account works in both companies). Supplier and
  employee *portal* accounts also live here but are pinned to a single company via
  a new `users.company_id` column (see §6.3).
- `companies` — **new** registry table (one row per company; see §4.4).

**Per-company (one copy in each company's schema — `public` for 102,
`company_101` for 101):** everything else, i.e.

```
procurement_records, status_change_log,
supplier_master, supplier_emails, supplier_email_audit, supplier_material_commitments,
mail_history, mail_templates, mail_parse_rules, followup_attempts,
communication_tasks, communication_messages, task_comments, task_activity_logs,
customer_mails, asns, asn_items, asn_events,
crm_ingest_logs, engine_jobs, engine_job_logs,
notifications, ai_feedback, agent_subscriptions, hi_agent_chat_messages,
app_settings
```

Rule of thumb: **shared = {`users`, `companies`}; per-company = every other table.**

### 4.2 The tenant switch (core mechanism)

Today `database.py` pins `search_path` **once** at engine creation from the global
`DB_SCHEMA`. We make it **per-request**:

1. A lightweight **ASGI middleware / dependency** decodes the JWT, reads
   `company_id`, looks up the company's `schema_name`, and stores it in a
   `ContextVar` (`current_company`).
2. `get_db()` (or a thin wrapper) issues `SET search_path TO "<schema>", public`
   on the session's connection at the **start of every request**, keyed off that
   `ContextVar`. For 102 the schema is `public` → `SET search_path TO public`.
3. Because it is set at the start of *every* request, a pooled connection reused
   across companies can never leak the previous company's schema.

**Why this is low-risk:** no ORM model gains a `schema=`; no query in any router,
service, or worker changes. Unqualified business tables resolve to the company
schema; the shared `users`/`companies` tables resolve to `public` via the
`, public` fallback in the search path.

### 4.3 Cross-schema references

Per-company tables reference `users` by id (e.g. `mail_history.sent_by`,
`notifications.user_id`, task assignees). Postgres resolves these to `public.users`
through the search path — cross-schema FKs are allowed and fine.

**Exception:** `users.supplier_id` / `users.emp_code` point at *per-company* data
(`supplier_master` exists in **both** schemas), so a single hard FK can't target
both. These become **soft references resolved within the account's own company**
(via `users.company_id`); we avoid a hard cross-schema FK constraint on them.

### 4.4 `companies` registry table

One row per company. Holds the per-company configuration that used to be global env:

| Column | 102 (Hariom Tech) | 101 (Enterprise) | Notes |
|--------|-------------------|------------------|-------|
| `id` | 102 | 101 | Stable company id (used in JWT). |
| `code` / `display_name` | Hariom Tech | Enterprise | UI label. |
| `schema_name` | `public` | `company_101` | Target Postgres schema. |
| `theme` | `red` | `blue` | Drives the CSS-variable palette (§8). |
| `brand_name` / `logo` | H-Connect | Enterprise | Top-bar + email-wrap identity. |
| `crm_*` (base url, desk id, login, device) | current desk 102 | **desk 101 + own creds** | May be blank for 101 until provided. |
| `mail_*` (IMAP/SMTP/from/customer domains) | current | **inherits 102's for now** | Overridable later for a dedicated 101 mailbox. |
| `is_active` | true | true | Gate a company on/off. |

Existing `CRM_*` / `SMTP_*` / `IMAP_*` / `CUSTOMER_MAIL_DOMAINS` env values remain
the **default (102)**; a company row's non-empty fields override them for that
company. Secrets (CRM/mail passwords) are stored the way the app already stores
mail creds; no new plaintext-secret surface beyond what exists today.

---

## 5. Auth & company selection

### 5.1 Login flow

1. Login screen gains a **company toggle** (Enterprise / Hariom Tech).
2. On successful auth, the chosen `company_id` is written into the JWT via the
   **existing** `create_access_token(extra={...})` bag — no new token plumbing.
3. Every subsequent request is scoped to that company by the tenant resolver (§4.2).

### 5.2 In-app company switch

- A **top-bar company switcher** lets staff jump companies without logging out. It
  calls a small endpoint that re-issues a token with the new `company_id` (subject
  to the user being a staff account). The frontend swaps the theme on switch.

### 5.3 Portal accounts (supplier / employee)

- Supplier and employee portal accounts are **pinned to one company** via
  `users.company_id`; their token's `company_id` is forced to that value and the
  login picker / switcher is hidden for them.
- Existing guards (`get_current_staff` / `get_current_supplier` /
  `get_current_employee` in `core/deps.py`) are unchanged in behavior; they gain
  company-awareness only through the shared tenant resolver.

---

## 6. Backend changes (summary)

1. **`database.py`** — add a `ContextVar`-driven per-request `search_path`; keep the
   global `DB_SCHEMA` path working (it becomes the default/102 behavior). Add a
   helper to create a company's schema + its per-company tables **without** creating
   the shared `users`/`companies` tables (the create-all guard).
2. **Tenant middleware/dependency** — decode JWT → resolve `company_id` →
   `schema_name` → set `ContextVar`. Reject requests whose token company is unknown
   or inactive.
3. **`companies` model + registry service** — CRUD + "resolve config for company"
   helper that layers a company row over the env defaults.
4. **Auth router** — accept `company_id` at login; validate it; embed in token. Add
   the switch endpoint (staff only).
5. **`users.company_id`** column (nullable; NULL/any for staff, set for portal
   accounts) added online by the existing `schema_evolve`.
6. **Scheduler / jobs** — wrap each job body in a **per-active-company loop** that
   sets the tenant context (schema + that company's CRM/mail config) before running:
   - **CRM ingest** runs once per company (desk 102 → `public`, desk 101 →
     `company_101`), each with its own creds and `ON CONFLICT` upsert.
   - **Signal recompute / follow-up dispatch / escalation** run per schema.
   - **Mail fetch (shared inbox):** fetch the single central inbox once, then
     **attribute each message to a company by matching the sender against each
     company's supplier emails** (suppliers are disjoint between companies), and
     process it in that company's context. When 101 gets its own mailbox, this
     becomes a straight per-company fetch and the attribution shim is removed.
   - **Outbound send** already carries company context from the record that
     produced the message.
7. **Seeding** — create the `companies` rows (102 from current env, 101 with its
   overrides), create the `company_101` schema + per-company tables, seed 101's
   default `mail_templates` and any starter `app_settings`. **Zero writes to 102's
   existing data.**

---

## 7. Mail (company-level, unchanged model)

- **Outbound:** company SMTP / `SMTP_FROM` (102's for both, until 101 gets its own).
  Outgoing mail is still auto-wrapped in brand-HTML; the wrap identity reads from
  the active company (Enterprise vs H-Connect).
- **Inbound:** one shared central inbox; replies attributed to a company by supplier
  email (§6, "Mail fetch"). Customer-mail queue, reply parser, and follow-up tracking work
  unchanged, now scoped per company.
- **No per-user SMTP/IMAP.** (Dropped — see §1.)

---

## 8. Branding & light-blue theme

- Colors are already 100% CSS variables (`--brand-red`, `--brand-dark`, …) toggled
  by a class on `<html>` (`frontend/tailwind.config.ts`, `globals.css`). Re-theming
  is a variable swap — **no component edits**.
- Add a **company-theme layer** on top of the existing light/dark toggle: on login
  or switch, apply the active company's palette. **101 = light-blue accent set;
  102 = today's red.** Both continue to support dark mode.
- App name in the top bar, the login logo, and the brand-HTML email wrap read from
  the active company.

---

## 9. Rollout & verification (staged, safe)

1. Ship behind a flag; **102 keeps running exactly as-is** until 101 is switched on.
2. Create the `companies` table + rows; create the `company_101` schema and its
   per-company tables; seed 101's admin/templates. **No changes to 102's data.**
3. Turn on 101 for staff and verify:
   - Login picker + top-bar switcher work; switching flips **both** data and theme.
   - **Isolation:** a 101 PO never appears in 102 and vice-versa; a 101-scoped API
     request cannot read 102 rows (and vice-versa).
   - RBAC still holds across companies; supplier/employee logins land in the right
     company only.
4. Paste desk-101 CRM creds → verify ingest fills **only** `company_101`.
5. Backend test suite stays green; **add multi-company isolation tests** (a request
   scoped to 101 cannot read/write 102 data; the `search_path` resets per request on
   a reused pooled connection).

---

## 10. Risks & mitigations

- **`search_path` leak on pooled connections** → set it at the **start of every
  request** (and per company in jobs), never assume a reused connection is clean.
- **`create_all` duplicating shared tables into `company_101`** → the schema
  creator explicitly creates only the per-company table subset, never
  `users`/`companies`.
- **Shared-inbox reply misattribution** → relies on suppliers being **disjoint**
  between companies (true today). Revisit if a supplier ever serves both; the fix is
  giving 101 its own mailbox (already the planned end-state).
- **Cross-schema `users.supplier_id`** → treated as a soft reference scoped by
  `users.company_id`; no hard cross-schema FK.
- **Forgotten hard-coded schema/branding** → sweep for any place that assumes a
  single schema or the H-Connect name; route branding through the active company.

---

## 11. Open follow-ups (post-v1)

- Give 101 its own dedicated mailbox (drops the attribution shim).
- Optional per-company access control for staff, if ever needed.
- Optional: move 102 out of `public` into a named `company_102` schema for symmetry
  (deferred to avoid migrating live data now).

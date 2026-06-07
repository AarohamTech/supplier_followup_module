# Supplier Follow-up Agent — Architecture

> Enterprise procurement control tower for industrial manufacturing teams.
> ERP/User-Desk APIs → FastAPI → PostgreSQL → Decision Engine → Predefined / AI Mail → Supplier → Reply Parser → Dashboard.

---

## 1. High-level System Flow

```
ERP / User Desk API
        │  (APScheduler – every N min)
        ▼
FastAPI sync service ─► PO Matching Engine ─► PostgreSQL
                                              │
                          ┌───────────────────┼─────────────────────┐
                          ▼                   ▼                     ▼
                 Follow-up Decision    Escalation Engine     Reply Parser (AI)
                 Engine (cron)         (cron)                (inbound mail)
                          │
              ┌───────────┴───────────┐
              ▼                       ▼
     Predefined Template         AI Follow-up Engine
     (GREEN / YELLOW /          (RED >2d, BLACK,
      RED D1 / RED D2)           no-reply, escalation)
              │                       │
              └──────────┬────────────┘
                         ▼
                 User Approval Queue
                         ▼
                   Mail Service
            (Gmail API / Graph / SMTP)
                         ▼
                  Mail History
                         ▼
                Next.js Dashboard
```

---

## 2. Backend Folder Structure (FastAPI)

```
backend/
├── app/
│   ├── main.py                 # FastAPI entrypoint, lifespan, CORS
│   ├── core/
│   │   ├── config.py           # Pydantic Settings (env)
│   │   ├── security.py         # JWT, password hashing
│   │   ├── logging.py
│   │   └── deps.py             # FastAPI dependencies (db, current_user)
│   ├── db/
│   │   ├── base.py             # Declarative Base
│   │   ├── session.py          # engine, SessionLocal
│   │   └── init_db.py          # bootstrap + seed
│   ├── models/                 # SQLAlchemy ORM
│   │   ├── user.py
│   │   ├── supplier.py
│   │   ├── supplier_email.py
│   │   ├── procurement.py      # procurement_records + history
│   │   ├── mail_template.py
│   │   ├── mail_history.py
│   │   ├── supplier_reply.py
│   │   ├── escalation.py
│   │   ├── api_sync_log.py
│   │   ├── followup_note.py
│   │   └── setting.py
│   ├── schemas/                # Pydantic v2 DTOs
│   ├── repositories/           # DB access layer
│   ├── services/
│   │   ├── erp_sync.py         # pull from ERP API
│   │   ├── matching.py         # CRM+PO+SupplierPO+Material match
│   │   ├── signals.py          # GREEN/YELLOW/RED/BLACK calc
│   │   ├── followup_engine.py  # decision flow
│   │   ├── ai_engine.py        # LLM mail generation + reply parsing
│   │   ├── mail_service.py     # Gmail/Graph/SMTP send
│   │   ├── escalation.py
│   │   └── reports.py
│   ├── scheduler/
│   │   ├── __init__.py         # APScheduler setup
│   │   └── jobs.py             # sync, followup, escalation jobs
│   ├── api/
│   │   ├── deps.py
│   │   └── v1/
│   │       ├── auth.py
│   │       ├── dashboard.py
│   │       ├── procurement.py
│   │       ├── suppliers.py
│   │       ├── emails.py
│   │       ├── mail_history.py
│   │       ├── replies.py
│   │       ├── escalations.py
│   │       ├── reports.py
│   │       ├── templates.py
│   │       └── settings.py
│   └── utils/
├── alembic/                    # migrations
├── tests/
├── requirements.txt
└── Dockerfile
```

---

## 3. PostgreSQL Schema (overview)

| Table                 | Key columns                                                                       |
| --------------------- | --------------------------------------------------------------------------------- |
| `users`               | id, email, hashed_password, full_name, role, is_active                             |
| `suppliers`           | id, supplier_code (uniq), supplier_name, gst, address, contact_person, type, status |
| `supplier_emails`     | id, supplier_id (FK), primary_email, cc_email, bcc_email, escalation_email, active, mail_preference |
| `procurement_records` | id, **uniq(crm_no, po_no, supplier_po_no, material_name)**, all ERP fields + signal_status, red_status_start_date, followup_count, last_followup_date, last_reply_date, last_supplier_reply, commitment_date, delay_reason, ai_required, escalation_level, overdue_days, acknowledgement_received |
| `procurement_history` | id, procurement_id (FK), changed_field, old_value, new_value, changed_at          |
| `mail_templates`      | id, template_name, applicable_status, applicable_day, subject_template, body_template, active |
| `mail_history`        | id, procurement_id (FK), supplier_id, template_id (nullable), engine ('template'/'ai'), to_email, cc, bcc, subject, body, status, sent_by, sent_at, message_id |
| `supplier_replies`    | id, mail_history_id (FK), raw_body, parsed_po_no, parsed_material, parsed_dispatch_date, parsed_qty, parsed_delay_reason, parsed_courier, dispatch_confirmed, received_at |
| `escalations`         | id, procurement_id, level, reason, raised_by, raised_at, resolved_at              |
| `api_sync_logs`       | id, source, started_at, finished_at, fetched_count, created_count, updated_count, status, error |
| `followup_notes`      | id, procurement_id, user_id, note, created_at                                     |
| `settings`            | id, key (uniq), value (jsonb), updated_at                                         |

Indexes on: `(signal_status)`, `(shipment_date)`, `(supplier_id)`, `(po_no)`, `(overdue_days)`, `(escalation_level)`.

---

## 4. PO Matching Engine

Unique key: `(crm_no, po_no, supplier_po_no, material_name)`.

```python
def upsert(record):
    existing = repo.find_by_unique(record.unique_key)
    if not existing:
        repo.insert(record)
        return "created"
    diff = diff_fields(existing, record, tracked=[
        "qty", "shipment_date", "signal", "po_status",
        "supplier_qty", "supplier_date"
    ])
    if diff:
        repo.write_history(existing.id, diff)
        repo.update(existing.id, record)
    return "updated"
```

History rows are written per changed field — full audit trail.

---

## 5. Signal & Follow-up Decision Flow

```
signal = compute_signal(record)        # GREEN/YELLOW/RED/BLACK

if signal == GREEN and not acknowledgement_received:
    template("GREEN_PO_RELEASE")

elif signal == YELLOW:
    template("YELLOW_REMINDER")

elif signal == RED:
    days = (today - red_status_start_date).days
    if days == 1:  template("RED_DAY1")
    elif days == 2: template("RED_DAY2")
    else:           ai_engine.generate(record, history)   # AI takes over

elif signal == BLACK:
    ai_engine.generate(record, history, escalate=True)
    escalation.raise(level=2)
```

All generated mails land in an **Approval Queue** before send (configurable per template via `auto_send` setting).

---

## 6. AI Engine

Pluggable provider (`OpenAI` / `AzureOpenAI` / `Ollama`) configured via env.

**Triggers:** RED > 2d, BLACK, no reply after N follow-ups, manual escalate.

**Inputs:** procurement record, last N mail-history rows, supplier replies, overdue days, criticality, customer impact, escalation level.

**Outputs:** `subject`, `body`, `tone`, `suggested_cc[]`, `suggested_bcc[]`, `next_action`.

**Reply parser:** every inbound mail (Gmail/Graph push or polled) → LLM extracts `{po_no, material, dispatch_date, qty, delay_reason, courier, dispatch_confirmed}` → updates procurement record + `supplier_replies`.

Prompts live in `app/services/ai_prompts/` for easy iteration.

---

## 7. Scheduler (APScheduler)

| Job                 | Cron              | Action |
| ------------------- | ----------------- | ------ |
| `erp_sync`          | every 30 min      | pull ERP API → matching engine |
| `signal_recompute`  | every hour        | recompute signals + overdue_days |
| `followup_dispatch` | 09:00 & 15:00 IST | enqueue mails per decision flow |
| `escalation_scan`   | every 2 hours     | raise escalations on rules |
| `reply_poller`      | every 15 min      | fetch new supplier replies |

---

## 8. API Endpoints (v1)

```
POST   /api/v1/auth/login
GET    /api/v1/auth/me

GET    /api/v1/dashboard/kpis
GET    /api/v1/dashboard/charts/{name}

GET    /api/v1/procurement                  # filters: signal, supplier, due, overdue, search
GET    /api/v1/procurement/{id}
GET    /api/v1/procurement/{id}/history
POST   /api/v1/procurement/{id}/note
POST   /api/v1/procurement/{id}/generate-mail   # template OR ai
POST   /api/v1/procurement/{id}/escalate
POST   /api/v1/procurement/{id}/mark-dispatched

GET/POST/PUT/DELETE /api/v1/suppliers
GET/POST/PUT/DELETE /api/v1/supplier-emails
GET/POST/PUT/DELETE /api/v1/templates
GET/POST/PUT/DELETE /api/v1/settings

GET    /api/v1/mail-history
POST   /api/v1/mail-history/{id}/send         # approve & send
GET    /api/v1/replies
GET    /api/v1/escalations
GET    /api/v1/reports/{name}

POST   /api/v1/sync/run                       # manual ERP sync
```

---

## 9. Frontend Architecture (Next.js 14)

```
frontend/
├── app/
│   ├── layout.tsx              # sidebar shell, top bar, notifications
│   ├── page.tsx                # Dashboard (matches mock)
│   ├── po-followups/page.tsx
│   ├── suppliers/page.tsx
│   ├── emails/page.tsx
│   ├── mail-history/page.tsx
│   ├── reports/page.tsx
│   └── settings/page.tsx
├── components/
│   ├── layout/Sidebar.tsx, Topbar.tsx
│   ├── dashboard/{KpiCard, SyncCard, AlertsCard, AIInsights, OverdueDonut, StatusDonut, ActionCenter, RecentReplies, NoReplySince}.tsx
│   ├── procurement/{FiltersBar, QuickFilters, PoTable, RowActions, MailModal}.tsx
│   ├── ui/                     # ShadCN primitives
│   └── charts/                 # Recharts wrappers
├── lib/
│   ├── api.ts                  # axios + JWT
│   ├── hooks/                  # useProcurement, useDashboard
│   └── types.ts
└── styles/globals.css
```

Theme tokens (Tailwind):
- background `#FFFFFF`, surface `#F7F8FA`
- accent red `#E11D2E`, dark `#111827`, muted `#6B7280`
- signal: green `#16A34A`, yellow `#F59E0B`, red `#E11D2E`, black `#111827`

---

## 10. Deployment

```
deploy/
├── docker-compose.yml          # postgres, backend, frontend, nginx
├── nginx/default.conf          # reverse proxy + TLS-ready
├── .env.example
└── systemd/                    # optional bare-metal
```

Production target: Ubuntu 22.04 VPS, Docker Engine, Let's Encrypt via certbot sidecar.

---

## 11. Phase-wise Implementation Plan

| Phase | Scope |
| ----- | ----- |
| **P0 — Foundation** | Repo, Docker, DB, auth, base layout, sidebar, empty modules |
| **P1 — Data backbone** | ERP sync service, matching engine, history, suppliers, supplier_emails, settings |
| **P2 — Dashboard & PO module** | KPIs, charts, ERP-style table, filters, quick filters, row actions |
| **P3 — Predefined mail engine** | Templates CRUD, GREEN/YELLOW/RED D1/D2 flow, approval queue, mail history |
| **P4 — Mail provider integration** | Gmail API + Graph + SMTP fallback, OAuth flows, send + status webhook |
| **P5 — AI follow-up** | LLM provider, prompt library, RED>2d & BLACK triggers, escalation tone |
| **P6 — Reply parser** | Inbound mail polling, AI extraction, auto-update commitments |
| **P7 — Escalation & reports** | Escalation dashboard, supplier performance, delay analytics |
| **P8 — Hardening** | Audit, RBAC, alerts, rate limits, Sentry, backups, HA |

---

## 12. Best Practices Applied

- Repository + Service layering, no DB in routes.
- Pydantic v2 strict schemas at boundary; ORM kept internal.
- Idempotent ERP sync with sync logs.
- Field-level history for full audit (compliance-ready).
- Mail send is **two-step** (generate → approve → send) to prevent AI mishaps.
- Prompts versioned in repo, never hard-coded inline.
- All scheduler jobs have advisory Postgres locks → safe horizontal scale.
- JWT short-lived + refresh; RBAC roles: `admin`, `procurement_mgr`, `procurement_user`, `viewer`.
- 12-factor config via `.env`.

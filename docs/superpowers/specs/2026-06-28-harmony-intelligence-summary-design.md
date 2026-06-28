# Harmony Intelligence Summary — Scheduled Admin Digest

**Date:** 2026-06-28
**Status:** Approved (design), pending implementation plan
**Author:** Chinmay Pisal (with Claude)

## 1. Overview

A new scheduled worker that, once per day at an admin-configured time, emails a
branded HTML summary of the current procurement state to a configurable list of
recipients. Everything — recipients, send time, timezone, which sections appear,
and per-section row limits — is editable from the admin Settings page. No data is
hardcoded; the digest reads live from the existing tables.

The email is titled **Harmony Intelligence Summary** and follows the existing
brand template (`brand_email.py`): brand-red wordmark header, white card on a
light surface, hairline section dividers, minimal/flat UI, no icons or emoji.

A rendered reference mock of the final email lives at
`backend/app/services/templates/digest_sample.html` (committed alongside this spec).

## 2. Scope

**In scope**
- New APScheduler job `admin_digest_cron` registered in the existing engine registry.
- New `admin_digest_service` that gathers data, renders HTML, and sends via SMTP.
- New `AppSetting` key `admin_digest` holding all admin-editable config.
- Backend routes `GET`/`PUT /api/settings/admin-digest` (manager-guarded) and
  `POST /api/settings/admin-digest/test` (send a one-off digest to the caller).
- A "Daily Summary" card in the Settings frontend page.

**Out of scope (YAGNI)**
- Per-recipient personalization or per-recipient section choices.
- Multiple digest schedules / multiple digest definitions.
- Persisting historical digests or an in-app archive view.
- A brand-new sentiment model — we reuse the existing LLM wrapper.

## 3. Email content & layout

Sections, top to bottom (each maps 1:1 to a `sections` toggle):

1. **Header / title** — brand-red bar + "Harmony Intelligence Summary", dated line
   (`27 June 2026 · 09:00 IST · covering the last 24 hours`). Always present.
2. **At a glance (counts)** — Active POs, Open follow-ups, Overdue, Critical,
   New replies (24h); plus a thin signal-mix bar (Green/Yellow/Red/Black counts).
3. **Summary** — one short paragraph written by the LLM over the aggregated numbers.
4. **Most critical** — table of top-N POs where `signal=BLACK` or
   `escalation_level in (CRITICAL, LEVEL_2)`, sorted by `risk_score` desc.
5. **Heated conversations** — top-N PO threads scored for tense/frustrated tone
   by the LLM, with a tone label + score, message counts, and the triggering quote.
6. **Top delay-risk POs** — `risk_band=HIGH` ordered by `risk_score`, with reason.
7. **Overdue & due today** — `shipment_date <= today` and not closed.
8. **CTA + footer** — "Open dashboard" link; footer points to Settings → Daily Summary.

All markup is table/`div` based with inline styles only (Gmail / Outlook /
Apple Mail safe), reusing `brand_email.header_html` / `shell` / `footer_html`.

## 4. Configuration (`AppSetting` key `admin_digest`)

```json
{
  "enabled": true,
  "recipients": ["ops@hariom.com"],
  "send_hour": 9,
  "timezone": "Asia/Kolkata",
  "sections": {
    "counts": true, "summary": true, "critical": true,
    "heated": true, "risk": true, "overdue": true
  },
  "limits": { "critical": 10, "heated": 5, "risk": 10, "overdue": 15 },
  "last_sent_date": "2026-06-27"
}
```

- Accessed via new `get_admin_digest()` / `set_admin_digest()` helpers in
  `settings_service.py`, mirroring the existing `scheduler_intervals` pattern.
- `last_sent_date` is written by the service (not user-editable in the UI); it is
  the once-per-day dedup guard.
- Defaults: `enabled=false` (safe — admin opts in), empty `recipients`,
  `send_hour=9`, `timezone="Asia/Kolkata"`, all sections on.

## 5. Scheduling mechanics

The scheduler registry is interval-based (`engine_jobs.interval_minutes`), so
rather than a one-off cron trigger (which doesn't fit the registry and can miss
fires across restarts), `admin_digest_cron` registers as a **short-interval
ticker** (default 15 min, configurable like every other job). Its runner is
idempotent and "due"-gated:

```
send_digest_if_due(db):
    cfg = get_admin_digest(db)
    if not cfg.enabled or not cfg.recipients: return {skipped: "disabled"}
    now_local = utcnow() -> cfg.timezone
    if now_local.hour < cfg.send_hour: return {skipped: "before send_hour"}
    if cfg.last_sent_date == now_local.date(): return {skipped: "already sent today"}
    html = build_digest_html(db, cfg)
    send_via_smtp(cfg.recipients, subject, html)
    set last_sent_date = now_local.date()
    return {sent: len(recipients)}
```

This guarantees exactly one send per local calendar day, on or after the
configured hour, surviving restarts and ticker drift. Honors the global
`SCHEDULER_ENABLED` and the per-job `engine_jobs.enabled` toggle already in place.

## 6. Components

- **`backend/app/scheduler/jobs.py`** — add `admin_digest_runner()` and a
  `JOB_SPECS` entry (`job_name="admin_digest_cron"`, default 15 min,
  display/description). Runner opens a `SessionLocal`, calls the service,
  returns a record-count dict for `EngineJobLog`.
- **`backend/app/services/admin_digest_service.py`** — single focused module.
  Public: `send_digest_if_due(db)`, `build_digest_html(db, cfg)`,
  `send_test_digest(db, to_email)`. Private helpers per section:
  `_gather_counts`, `_gather_critical`, `_gather_heated`, `_gather_risk`,
  `_gather_overdue`, `_ai_summary`, `_render_html`. Each helper is independently
  testable and respects its `sections`/`limits` config.
- **`backend/app/services/settings_service.py`** — `get_admin_digest` /
  `set_admin_digest` with schema defaults + validation.
- **`backend/app/routers/settings.py`** — `GET`/`PUT /api/settings/admin-digest`
  (`require_manager`) and `POST /api/settings/admin-digest/test` (sends to the
  current user's email; `require_manager`).
- **`frontend/app/settings/page.tsx`** — "Daily Summary" card: enabled toggle,
  recipients chip input, send-hour select, timezone, section checkboxes,
  per-section limits, and a "Send test to me" button.

## 7. Heated-conversation detection

Candidate selection (cheap, deterministic): POs ranked by recent thread activity
— `CommunicationMessage` count + count in last 24h + `followup_count` +
`escalation_level`. The top handful of candidates are passed to the LLM
(`ai_service`, NIM llama-3.3-70b) which classifies tone and returns a label
(`calm` / `tense` / `frustrated`) and a 0–1 score; we keep those above a heat
threshold, up to `limits.heated`.

**Fallback:** if `LLM_ENABLED` is false or any LLM call fails, the section falls
back to the heuristic ranking alone (label derived from escalation/activity), so
the digest never breaks. The summary paragraph degrades the same way: when the
LLM is unavailable, a templated sentence is generated from the counts.

## 8. Data sources (all existing)

| Section | Source | Filter |
|---|---|---|
| Counts | `ProcurementRecord` | active; group by `signal`; overdue = `shipment_date < today` |
| New replies | `CommunicationMessage` | `direction=INCOMING`, `received_at >= now-24h` |
| Critical | `ProcurementRecord` | `signal=BLACK` or `escalation_level in (CRITICAL, LEVEL_2)`, order `risk_score` desc |
| Heated | `CommunicationMessage` + `ProcurementRecord` | activity ranking → LLM tone |
| Risk | `ProcurementRecord` | `risk_band=HIGH`, order `risk_score` desc |
| Overdue | `ProcurementRecord` | `shipment_date <= today`, not closed |

Admin recipients are free-form emails from config, not derived from roles.

## 9. Error handling

- Service catches and logs per-section gather errors; a failing section is omitted
  rather than aborting the whole digest. The runner reports partial success in the
  `EngineJobLog` message.
- SMTP send failures are raised so the `EngineJobLog` row records `ERROR`;
  `last_sent_date` is **not** stamped on failure, so the next ticker retries.
- If `SMTP_ENABLED` is false, the runner logs `skipped: smtp disabled` and does
  not stamp `last_sent_date`.
- Empty data → the digest still sends with "None" / zero states (so admins get a
  daily heartbeat), unless a future toggle opts out (out of scope now).

## 10. Testing

- **Unit:** each `_gather_*` helper against a seeded session (counts math,
  critical filter/order, overdue boundary at `== today`, risk filter).
- **Due logic:** `send_digest_if_due` table-driven — before hour, after hour,
  already-sent-today, disabled, no recipients, smtp disabled.
- **LLM fallback:** heated + summary with `LLM_ENABLED=false` and with a raising
  LLM stub → heuristic/templated output, no exception.
- **Render:** `build_digest_html` produces valid HTML containing each enabled
  section and omitting disabled ones; snapshot against the sample.
- **Route:** GET returns defaults, PUT round-trips and validates, test endpoint
  triggers a send to the caller.

## 11. Open questions

None blocking. Default `send_hour=9` IST and `enabled=false` chosen as safe
defaults; admin enables and adds recipients on first use.

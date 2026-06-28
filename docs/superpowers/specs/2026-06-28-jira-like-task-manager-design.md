# Jira-like Task Manager — Real-user Assignment, Comments/Progress, AI Summary, Analytics

**Date:** 2026-06-28
**Status:** Approved (design)

## Problem

The task manager (`communication_task`) is functional — Kanban + table views, status
workflow, priority, signal, due dates — but three gaps keep it from being a real
"Jira-like" work tracker:

1. **Assignees are dummy free-text.** `assigned_to` / `watchers` are plain strings
   (e.g. `"Purchase Head"`, `"Sourcing Head"` hardcoded in escalation). No link to real
   accounts, no validation, no way to filter/report by person.
2. **No AI summary** of a task's discussion, and **progress** is only implied by the
   Kanban column (no explicit progress indicator, weak unified timeline).
3. **Logging isn't analyzable.** Changes are recorded in `TaskActivityLog` but there is
   no analytics view or export to "extract all data for analysis".

## Goals

- Replace dummy assignees with **real users** (staff + employees), with a searchable
  picker, and **remap existing** dummy data to real accounts.
- Make the task drawer feel like Jira: a unified **activity timeline**, a manual
  **progress %**, real-author **comments**, and an on-demand **AI summary**.
- Provide an **analytics dashboard + export** computed from the (extended) append-only
  activity log.

## Non-goals (YAGNI)

Subtasks, file attachments, task dependencies, sprints/epics, multi-assignee. Not in
this iteration.

---

## Design

### 1. Real-user assignment

**Model — `communication_task` (online-migrated via `core/schema_evolve.ensure_columns`)**
- Add `assigned_to_user_id: int | None` — FK → `user.id`, indexed. Source of truth.
- Keep `assigned_to: str | None` as a **denormalized display name**, auto-filled from the
  assigned user's `full_name` (fallback `username`/`email`). Lets Kanban cards render with
  no join and preserves backward compatibility.
- `watchers` (existing JSON) holds **user IDs** going forward; display names resolved
  client-side from the assignees list.
- Add `assigned_at: datetime | None`, set whenever the assignee changes.

**Assignee source — new endpoint**
- `GET /api/communication/assignees` (any staff writer; `require_writer`-level) returns
  `[{id, label, role, type}]` for all **active staff + employee** accounts
  (`supplier_id IS NULL`, `is_active = true`). Suppliers excluded.
- `type` ∈ `"staff" | "employee"`; `label` = `full_name` (fallback `username`).

**Schema/router**
- `CommunicationTaskCreate/Update` accept `assigned_to_user_id` (and `watchers` as
  `list[int]`). On write, the router resolves the user, validates it is assignable, sets
  the denormalized `assigned_to` name + `assigned_at`, and logs an ASSIGNEE_CHANGED
  activity. Free-text `assigned_to` writes are still tolerated but discouraged.

**Frontend**
- Replace the free-text assignee input in the drawer ([tasks/page.tsx:649]) and the
  create modal with a searchable dropdown fed by `/api/communication/assignees`.
- Watchers field becomes a multi-select over the same list.
- Cards/table show the resolved display name + avatar initials.

**Remap existing dummy data — `backend/scripts/remap_task_assignees.py`**
(standalone, `--yes` guarded, run on the Mumbai box venv against the pooler; prints a
before/after report.)
- Seed real **manager-role** staff users for the escalation role-titles
  (`Purchase Head`, `Sourcing Head`) as dedicated named accounts (admin can rename/
  reassign later). Replace the hardcoded strings in
  [communication_hub.py:1107] escalation so new escalations assign a real `user_id`.
- Back-fill `assigned_to_user_id` on existing tasks by matching the current `assigned_to`
  / `watchers` strings (case-insensitive, against `full_name`/`username`) to real users.
  Unmatched strings are left intact and listed in the report.

### 2. Comments + progress

- **Comments**: add `created_by_id: int | None` (FK) to `TaskComment` so the dashboard
  and export attribute by user, not just a name string. Comment endpoints stamp the
  current user.
- **Progress %**: add `progress_percent: int` (0–100, default 0) to the task. Editable in
  the drawer; thin progress bar on each Kanban card. Convenience rule: status → DONE
  auto-sets 100; status → BACKLOG resets to 0; otherwise fully manual.
- **Unified timeline**: extend `task_collaboration_service.record_task_changes()` to also
  log PROGRESS_CHANGED, AI_SUMMARY_GENERATED, and ESCALATED, in addition to the existing
  STATUS/ASSIGNEE/PRIORITY/DUE_DATE/COMMENT events. The drawer renders one chronological
  feed merging comments + activity (Jira-style), newest first.

### 3. AI summary

- `POST /api/tasks/{id}/ai-summary` (staff): builds a transcript from the task
  description + all comments + activity, calls existing
  `ai_service.summarize_thread()` ([ai_service.py:430]).
- Cache on the task: `ai_summary: text`, `ai_summary_at: datetime`,
  `ai_summary_by: str`. Shown at the top of the drawer with a **Summarize / Regenerate**
  button. If `LLM_ENABLED` is false, the endpoint returns 503 and the button is disabled
  with a tooltip.
- Each generation logs an AI_SUMMARY_GENERATED activity (counts in analytics).

### 4. Analytics dashboard + export

- New page `frontend/app/tasks/analytics/page.tsx` (staff) backed by
  `GET /api/communication/analytics`, computed from `communication_task` +
  `TaskActivityLog`:
  - **Throughput**: created vs. completed over time (last N weeks).
  - **Cycle time**: avg TODO→DONE duration; time-in-status.
  - **Workload by assignee**: open / overdue / done per real user.
  - **Breakdowns**: by supplier, by source, by priority; overdue & due-today counts.
- **Export**: `GET /api/communication/analytics/export` streams an Excel workbook
  (openpyxl) — sheet 1: one flat row per task (all fields + counts + resolved assignee);
  sheet 2: the raw activity log. Download button on the analytics page.
- The durable "log everything" requirement is met by the **existing append-only
  `TaskActivityLog`**, extended in §2 to cover all event types with actor `user_id`,
  timestamp, and old→new values. No separate audit table is introduced.

---

## Files at a glance

**Backend new:** `scripts/remap_task_assignees.py`.
**Backend edit:** `models/communication_task.py`, `models/task_collaboration.py`,
`schemas/communication_task.py`, `routers/communication.py`,
`routers/communication_hub.py` (escalation real-user assign + analytics + assignees +
ai-summary endpoints), `services/task_collaboration_service.py`, `seed.py` (seed role
accounts).
**Frontend new:** `app/tasks/analytics/page.tsx`, assignee-picker component.
**Frontend edit:** `app/tasks/page.tsx` (drawer + create modal + card progress bar +
timeline + AI summary), `lib/types.ts`, `lib/api.ts`.

## Reused building blocks

`core/schema_evolve.ensure_columns` (online migration), `task_collaboration_service`
(activity/comments), `ai_service.summarize_thread()` (AI), `core/deps` RBAC
(`require_writer`/staff), the existing supplier-email-audit Excel/openpyxl export pattern,
the purge-script pattern for the one-time remap.

## Verification

1. Schema: restart backend → `schema_evolve` adds `assigned_to_user_id`, `assigned_at`,
   `progress_percent`, `ai_summary*` to `communication_task` and `created_by_id` to
   `task_comment`.
2. Assignment: `/api/communication/assignees` lists staff + employees only; assigning a
   task sets FK + display name + `assigned_at` + logs ASSIGNEE_CHANGED.
3. Remap: run `remap_task_assignees.py --yes` on the box → role accounts seeded, existing
   tasks back-filled, report printed; escalation now assigns a real user.
4. Progress/timeline: progress bar updates; DONE→100; unified timeline shows comments +
   all activity types.
5. AI summary: button generates + caches a summary; disabled when LLM off.
6. Analytics: dashboard renders throughput/cycle/workload; Excel export downloads with
   both sheets.
7. Frontend: `npx tsc --noEmit` + `npm run build` clean; suppliers cannot reach the
   assignee list or analytics.
8. Deploy: push → GitHub Actions to Mumbai box; `/healthz` 200.

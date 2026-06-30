# Role dashboards: enrich employee + supplier to admin depth

**Date:** 2026-06-30
**Branch:** feat/portal-admin-parity
**Status:** Approved (enrich both)

Both the employee (`/eportal`) and supplier (`/portal`) landing pages already exist but are
lighter than the admin dashboard. Enrich them to the admin's depth (KPI strip + charts +
insights + activity), with role-scoped data. Reuse admin dashboard components where possible.
No DB changes; the needed endpoints already exist.

## Part A — Employee dashboard (`frontend/app/eportal/page.tsx`)
Switch the page to the shared zustand store at `employee` scope (same pattern as
`/eportal/followups`: `setScope("employee")` on mount, `setScope("staff")` on unmount) so the
admin dashboard components work scoped, then compose:
- **KpiStrip** (reused) — scoped KPIs from `/api/eportal/procurement/dashboard`.
- **StatusDonut** + **OverdueDonut** (reused) — scoped signal + workload charts.
- **AIInsights** (reused) — scoped narrative from `kpis` + `list`.
- **Tasks summary** card — new small card reading `/api/eportal/tasks/dashboard`
  (todo / waiting / overdue / critical).
- **Owned-PO / recent list** — keep the existing employee PO table (top owned POs) or
  `RecentReplies`; choose the PO table (already employee-shaped).
- **Quick actions** — employee links (My POs · Black Follow-ups · Communication · My Tasks).
The existing per-page `eportalSummary` fetch is dropped in favour of the store (kpis/list);
`eportalTasksDashboard` is added for the tasks card.

## Part B — Supplier dashboard (`frontend/app/portal/page.tsx`)
Suppliers don't use the store and have a different data shape (`PortalSummary` /
`PortalPoListResponse`), so enrich in place reusing `StatCard` / `AsnCards`:
- **PO signal donut** — derived client-side by counting `overall_signal` across the
  `portal/pos` items (GREEN/YELLOW/RED/BLACK). No backend change.
- Keep the **4 PO tiles** (total / pending / completed / blocked) + **ASN tiles** + **Critical POs**.
- **Tasks summary** card — `/api/portal/tasks/dashboard` (already exists).
- Tidy the quick links.
A small reusable `SignalDonut` (theme-aware, like the dashboard chart) takes explicit
counts as props so both the supplier page (derived counts) and any future caller can use it.

## Components
- Reused as-is (read scoped store): `KpiStrip`, `StatusDonut`, `OverdueDonut`, `AIInsights`.
- New: `EmployeeTasksCard` (or a shared `TasksSummaryCard` taking a counts object + base href),
  a `SignalDonut` taking `{green,yellow,red,black}` counts for the supplier page, and an
  employee quick-actions block.
- Dark mode is inherited (all are token-based / theme-aware).

## Verification
- `tsc --noEmit`.
- No new backend endpoints (employee/supplier summary, tasks-dashboard, dashboard KPIs all
  already exist). No DB migration.
- Not run live (local `.env` → prod DB).

## Out of scope (YAGNI)
- No new analytics/metrics beyond what the existing endpoints return.
- Admin-only cards (SupplierMaster, EmailMaster, SyncCard, MailEngineStatus) are not added to
  the role dashboards.

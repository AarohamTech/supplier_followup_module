# Employee Black Follow-ups panel + system-wide dark mode

**Date:** 2026-06-30
**Branch:** feat/portal-admin-parity
**Status:** Approved (build both, in sequence)

Two independent sub-projects, built in order.

---

## Part 1 — Employee Black Follow-ups panel (replaces the grouped table)

Give employees the exact admin **Black Follow-ups** panel (`/black-followups`), scoped to the
POs they own (`owner_emp_code == user.emp_code`), with draft **and** send.

### Decisions
- **Replace** the employee `/eportal/followups` grouped all-signal table with the Black panel.
  The grouped-table components (`PoTable`/`FiltersBar`/`QuickFilters`) stay (admin `/po-followups`
  still uses them) — the employee page just stops rendering them.
- Employees can **draft + send** follow-ups on their owned POs (no `require_manager`).
- Sidebar label "PO Follow-ups" → **"Black Follow-ups"** in the employee sidebar.

### Frontend
- Extract a `BlackFollowupsAdapter` from `app/black-followups/page.tsx` (mirrors `CommHubAdapter`):
  `{ list(limit), history(params), command(po, instruction, send) }`. `BlackFollowupsPage` +
  `DetailDrawer` + history become a shared component taking the adapter; behavior unchanged.
- Admin `/black-followups` passes the existing `api.getBlackFollowups / getFollowupHistory /
  blackFollowupCommand`.
- Employee `app/eportal/followups/page.tsx` renders the shared panel with an **employee adapter**
  hitting the new eportal endpoints.

### Backend (employee router, scoped to owned POs)
- `GET /api/eportal/ai/insights/black-followups` — same shape as admin, only the employee's BLACK POs.
- `GET /api/eportal/ai/insights/followup-history` — their POs only (BLACK default).
- `POST /api/eportal/ai/insights/black-followups/command` — `get_current_employee`; 404 if the PO
  isn't owned; otherwise reuse the existing admin command service (draft/preview + send). No
  `require_manager`.
- Reuse the existing `ai_insights` service functions; the eportal router only adds the scope guard
  (owned-PO set) and delegates, matching the established `eportal_hub` pattern.

### Tests (pytest, in-memory SQLite)
- Employee sees only owned BLACK POs (foreign BLACK PO excluded).
- History scoped to owned POs.
- `command` on a foreign PO → 404; on an owned PO → draft/preview ok (send path mockable).

---

## Part 2 — System-wide dark mode (full sweep, one pass)

Minimalist dark theme across all three portals (staff / employee / supplier).

### Infrastructure
- `tailwind.config.ts`: `darkMode: 'class'`. Redefine `brand-*` / `signal-*` as
  `rgb(var(--token) / <alpha-value>)` (opacity modifiers keep working) and add semantic tokens:
  `surface` (page bg), `card`, `text`, `text-muted`, `border`. The ~1,089 existing semantic-token
  usages then flip automatically.
- `globals.css`: `:root` (light) and `.dark` (dark) variable sets; make `.card/.input/.badge/
  .btn-*/.table-shell/.empty-state`, selection and focus styles theme-aware.
- Theme state in the zustand store: `'light' | 'dark' | 'system'`, persisted to `localStorage`,
  default **follow OS**. A tiny inline script in `app/layout.tsx` applies `<html class="dark">`
  before paint (no flash-of-wrong-theme). A `useTheme` hook + a minimalist sun/moon **toggle** in
  all three topbars (admin `Topbar`, `SupplierShell`, `EmployeeShell`).

### The sweep (~90 files)
- Map common hardcoded utilities to dark-aware tokens: `bg-white`→`bg-card`, `bg-gray-50/100` /
  `bg-slate-50`→`bg-surface` (or subtle), `text-gray-*`→`text` / `text-muted`, `border-gray/slate-*`
  →`border`. Hover / focus / badge fills get dark variants.
- Recharts (`StatusDonut`, `OverdueDonut`): pull colors from the theme instead of hardcoded hex.
- Done with parallel sub-agents over file batches; verify each portal renders dark-correct.

### Dark palette (minimalist, single red accent)
page `#0D1117` · surface `#11151B` · card `#161B22` · border `#262C36` · text `#E6EAF0` ·
muted `#9BA3AE` · accent red `#E11D2E` (kept). Greens/yellows kept; badges shift to translucent
dark fills.

---

## Verification
- Backend pytest for the eportal Black endpoints (scoping + 404 + command).
- Frontend `tsc --noEmit`.
- Visual check of each portal in both themes. The live app is not run (local `.env` → prod DB).

## Out of scope (YAGNI)
- No new follow-up analytics or AI behavior — Part 1 only re-skins/scopes the existing panel.
- No per-component theme overrides or multiple dark palettes — one light, one dark.

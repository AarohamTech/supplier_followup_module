# Design — Four Features (PO identity, Other-Mails toggle, Compose page, Workload-by-customer)

Date: 2026-07-03
Branch: `feat/four-features-po-identity`
Status: Approved (recommended options chosen). Build order: **4 → 1 → 3 → 2**.

Four independent features requested together. Each section is self-contained so
implementation can proceed and be reviewed per-feature.

---

## Feature 4 — Same PO number across different suppliers

### Problem (verified read-only against prod, 2026-07-03)
`procurement_records.supplier_po_no` (from CRM `PoNo`) is a **recycled counter, not
unique per supplier**: PO `004531` spans 6 suppliers, `000889` 6, `001819` 5;
~169 PO numbers are reused across multiple suppliers. Vedant Tools + Alfa Toolings
collide on `000449` (the reported `000440` is Vedant-only).

`procurement_records` rows survive because `crm_no` (unique per line) is in the key
`(crm_no, supplier_po_no, material_name)`. But code keyed by `supplier_po_no` **alone**
conflates suppliers:
- `supplier_material_commitments` unique key was `(supplier_po_no, material_name)` — no supplier.
- Customer Workspace context fetch: `listProcurement({supplier_po_no})` + `listCommitments({supplier_po_no})` (CustomerWorkspace.tsx:163-166) — unscoped.

### Decision
The canonical PO identity is **`(supplier_name, supplier_po_no)`** (matches PoTable's
existing `SUPPLIER|PO` grouping key and the supplier_name columns already on the
commitment/mail/task tables).

### Changes
1. **Migration (Alembic):** `supplier_material_commitments` unique constraint
   `uq_commitment_po_material` → `uq_commitment_supplier_po_material`
   on `(supplier_name, supplier_po_no, material_name)`. Handle existing rows
   (dedupe if any duplicate supplier collisions exist — none today, but guard).
2. **Commitment service:** upsert/lookup by `(supplier_name, supplier_po_no, material_name)`.
   `commitments()` API already accepts optional `supplier_name` (CommHub passes it);
   make the customer-side callers pass it too.
3. **Customer Workspace:** pass `supplier_name` alongside `supplier_po_no` when fetching
   procurement + commitments so shared PO numbers don't mix suppliers. Requires the
   customer mail to carry/derive a supplier_name for the linked PO (derive from the first
   procurement row's supplier when a PO number resolves to exactly one supplier; if it
   resolves to >1, surface all and let the linked mail's supplier disambiguate).
4. **Audit script:** keep the read-only shared-PO report under `backend/scripts/` for future checks.

### Out of scope
No synthetic PO id column (too invasive; supplier_name scoping is sufficient and
consistent with existing code).

### Tests
- Commitment upsert for two suppliers sharing a PO number + material name creates two rows.
- Lookup scoped by supplier returns only that supplier's commitment.

---

## Feature 1 — "Other Mails" toggle (Communication Hub)

### Problem
`CommunicationHub.tsx` (~1214-1257) renders the "Other Mails (no PO)" list *below* the
full PO list in one scroll container. Suppliers with hundreds of POs bury it.

### Decision
Replace the stacked expand with a **two-tab segmented control** in the lower-left panel:
`Purchase Orders (n)` | `Other (n)`. Selecting a tab swaps which list renders; the other
is hidden. Unread badge stays on the "Other" tab.

### Changes (frontend only)
- Replace `showOtherMails: boolean` with `poView: "pos" | "other"`.
- Render segmented control where the current "Purchase Orders" header + "Other" button sit.
- Show only the PO list when `poView==="pos"`, only the Other-Mails list when `"other"`.
- Keep lazy-load of Other Mails on first switch to that tab.
- Selecting a PO switches back to (or stays on) the appropriate view as today.

### Tests
- Component/interaction: switching tabs swaps lists; PO list not present while on "Other".

---

## Feature 3 — Workload "By customer" + detailed columns

### Part (a) — Ingest customer fields (data plumbing)
Today `customer_name` (0 rows), `po_date` (0 rows) are empty; `po_no` is a copy of
`supplier_po_no`. The CRM desk feed carries customer fields we don't map yet.

- In `crm_ingest_service.map_row` + `_col_values`: map end-customer name, customer PO no,
  and customer PO date from their CRM source fields. **The exact CRM field names must be
  confirmed against the live feed on the prod box (creds are not local) or provided by the
  user.** Isolate them behind clearly-named constants so implementation fills them in one place.
- Stop overwriting `po_no` with `supplier_po_no`.
- Add `_HASH_FIELDS` entries for the new fields so changes trigger re-ingest.
- Alembic migration only if a column is missing (customer_name, po_no, po_date already exist).
- Backfill happens naturally on next ingest (source_hash change).

**Fallback:** if a customer field is genuinely absent from the feed, that column renders "—";
the by-customer grouping degrades to "(no customer)" bucket rather than breaking.

### Part (b) — Report tab + columns
- **Backend** `GET /api/reports/workload`: add a `customers` array mirroring `suppliers`,
  grouping procurement by `customer_name` (PO/signal/overdue/task rollups). Reuse
  `_po_measures`/`_task_measures`. Export (xlsx) gains a customers sheet.
- **Frontend** `app/reports/workload/page.tsx`: add a "By customer" tab (mirror "By supplier"),
  with filter + drill-through (customer detail page mirrors supplier detail, or reuse the
  detailed PO-line table).
- **Detailed columns (Option A):** extend the main dashboard PO table
  (`components/procurement/PoTable.tsx`) material rows to include the full column set:
  customer name, customer PO no, PO date, material, signal, qty, supplier PO no,
  supplier PO date, stock, ship date, overdue, commitment date, supplier remark.
  Add a lightweight **column-visibility toggle** (the table gets wide) with sensible defaults;
  commitment date + supplier remark come from the commitment join already used elsewhere.

### Types
`WorkloadCustomerRow` in `lib/types.ts`; extend `WorkloadReport` with `customers`.

### Tests
- Report returns a customers array grouped by customer_name.
- PoTable renders the new columns; hidden columns respected.

---

## Feature 2 — Compose Mail page (new)

### Decision
Real send via the mail engine (logged in mail_history, appears in threads). New top-level
route `/compose` with a "Compose" nav item. Writer role (admin/manager/user), same as other
send actions.

### UI (`app/compose/page.tsx` + `components/compose/*`)
Focused mail-client layout:
- **Audience toggle:** Supplier ↔ Customer (drives recipient source).
- **To / Cc / Bcc:** multi-select chips.
  - Supplier recipients from `/api/supplier-emails` (auto-fill mapped to/cc/escalation on pick).
  - Customer recipients from customer-mail contacts.
  - Internal users (Cc) from `/api/communication/assignees`.
  - Free-typed email addresses allowed (validated).
- **Optional PO link** (`supplier_name` + `supplier_po_no`) so the mail threads correctly.
- **Subject + body.**
- **HI assist:** "Draft with HI" and inline refine, reusing existing AI-reply/agent plumbing.
- **Send** (primary) + **Save draft** (secondary).

### Backend
New `POST /api/communication-hub/compose` (writer role): validates recipients, creates the
communication message + `mail_history` row, and triggers the existing SMTP send path
(reuse logic from `communication_hub.py` send-mail / reply, ~1404-1591). Returns send status.
Threads under the linked PO when provided; otherwise a standalone/customer thread.

### Tests
- Compose endpoint with recipients + body creates a mail_history row and invokes send.
- Validation rejects empty recipients / body.
- Role guard: viewer denied.

---

## Cross-cutting notes
- Backend tests run in `backend/.venv` (pytest, in-memory SQLite). 2 pre-existing
  `test_mail_send_retry` failures are known-unrelated.
- Do not push; commit per-feature on `feat/four-features-po-identity`.
- Feature 3(a) CRM field names are the one open input; everything else is fully specified.

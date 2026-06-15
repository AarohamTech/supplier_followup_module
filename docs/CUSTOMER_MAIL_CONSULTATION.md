# Consultation: Customer Mail Auto-Reply & Module Review

**Date:** 2026-06-15
**Scope:** Live walkthrough of all modules + code study, focused on customer-mail handling and how to automate replies using existing PO + supplier-commitment data.

---

## 1. Executive Summary

The platform already has a strong **Supplier Communication Hub** and well-structured procurement data, but the **Customer Mail** module is **triage-only** — today there is no way to reply to a customer from inside the app.

The good news: the data needed to answer the most common customer question ("where is my order / what's the dispatch date?") **already exists** in `procurement_records` and `supplier_material_commitments`. This means most customer replies can be generated **deterministically from data**, without requiring an LLM.

> Important caveat discovered during review: the README advertises a "pluggable LLM provider," but **no LLM is actually wired up**. The current "AI Reply" simply renders a static template. Automation should therefore be built **data-template-first**, with an optional LLM layer added later.

---

## 2. Module-by-Module Findings

### 2.1 Supplier Communication Hub (`/mail-history`) — Strong
- Supplier list with health %, PO list, message thread.
- Parsed material reply tables (CRM No, Material, Qty, Due Date, Status, Commitment Date, Remark).
- AI Summary, reply tone templates (Professional / Reminder / Strong Follow-up / Escalation).
- Actions: Reply, Send Mail, Escalate, Create Task, Reminder.
- **This is the UX gold standard** the other modules should match.

### 2.2 Customer Mails (`/customer-mails`) — Triage-only (main gap)
Backend `routers/customer_mails.py` exposes only:
- `GET` list / detail
- `PATCH /{id}/assign` (assigned_to, priority, status, customer_name, mail_type)
- `POST /{id}/resolve`
- `POST /{id}/create-task`

Frontend `app/customer-mails/page.tsx`:
- Filters, KPIs, triage panel, create-task, mark-resolved.
- **No reply box, no send action, no AI/auto draft.**

**Consequence:** customers cannot be replied to from the app at all.

### 2.3 Inbound Mail Routing — Partially wired
`workers/mail_fetch_worker.py`:
- Mail from an **unknown sender with no PO match** is routed to the customer inbox.
- Classified by simple keyword rules (`_classify_customer_mail`) into DISPATCH / QUALITY / FINANCE / COMPLAINT / SUPPLIER / CUSTOMER / GENERAL.
- **`linked_supplier_po_no` is defined on the model but never populated** — customer mails are never connected to the related order, even when a PO/CRM number is present.

---

## 3. The Data You Already Have (key enabler)

| Source | Useful fields |
| ------ | ------------- |
| `procurement_records` | `customer_name`, `supplier_po_no`, `crm_no`, `material_name`, `shipment_date`, `po_status`, `commitment_date` |
| `supplier_material_commitments` | latest `commitment_date`, `supplier_status`, `supplier_remark` per (PO + material) |

When a customer asks about an order, the mail can be joined to these tables on PO/CRM number and answered with the **live committed dispatch date and status** — deterministically.

Example auto-reply body:
> "Your order PO 2526-008696 (Milling Cutter AHX640W) is currently **APPROVED** and committed for dispatch on **23-May-2026**. We will update you on dispatch confirmation."

---

## 4. Recommended Plan

### Phase 1 — Make replies possible (must-have)
1. `POST /api/customer-mails/{id}/reply` — compose + send via existing SMTP `mail_send_worker`.
2. Reply composer in the customer-mails page (mirror the Comm Hub composer).
3. Populate `linked_supplier_po_no`: in the fetch worker, extract PO/CRM numbers from subject/body and match a `ProcurementRecord` even for customer senders, so each mail shows its related order.

### Phase 2 — Suggested auto-draft (the core automation)
4. `POST /api/customer-mails/{id}/draft-reply` that:
   - Detects intent (order-status / delivery-date / invoice / complaint) — extend `_classify_customer_mail`.
   - Looks up linked PO(s) + latest `SupplierMaterialCommitment`.
   - Fills a data template and returns subject + body for one-click review/send.
5. Add an **"Order Status Reply" template set**: acknowledge / status-update / delay-apology / dispatch-confirmation.

### Phase 3 — Full automation (opt-in, guarded)
6. Scheduler job + setting (default **OFF**, like existing `*_ENABLED` flags) that auto-sends the draft **only** for high-confidence "order status" mails matching a single PO. Everything else stays manual. Always log to mail history.

---

## 5. What to Include vs Exclude

**Include (safe to automate):**
- Order-status / dispatch-date questions with a single confident PO match.
- Acknowledgement of receipt.
- Dispatch confirmation once commitment status = DISPATCHED.

**Exclude (draft-only, human approval required):**
- Complaints, Quality / NCR, Finance / payment / invoice disputes.
- Multi-PO or ambiguous mails (no confident match).
- Anything where no linked order is found.

**Do NOT do first:**
- Don't build the LLM integration before data templates — deterministic templates cover ~80% of order-status questions safely and cheaply.

---

## 6. Broader UX "Ease-out" Fixes Noticed
- **Customer Mails parity:** add the linked-order panel and reply actions that the Comm Hub already has (biggest inconsistency).
- **Comm Hub data binding:** every supplier shows "No subject / —" and a repeated "12% Health" — subject/health mapping looks broken; worth a data-binding check.
- **Assignee field:** `assigned_to` is free text (typo-prone) — switch to a user dropdown.
- **Bulk actions:** allow assign/resolve on multiple mails at once.
- **SLA / age indicator:** show how long a customer mail has been waiting.
- **Canned-response picker:** quick insert of standard replies in the composer.

---

## 7. Suggested Build Order (incremental, low-risk)
1. Reply endpoint + composer (Phase 1.1–1.2)
2. PO-linking on inbound customer mails (Phase 1.3)
3. Data-driven draft-reply endpoint + template set (Phase 2)
4. Guarded auto-send behind an off-by-default flag (Phase 3)

Each step is shippable on its own and keeps automation behind explicit toggles, consistent with the existing safety-first config pattern.

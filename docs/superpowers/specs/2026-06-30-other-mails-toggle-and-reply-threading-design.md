# Communication Hub: "Other Mails" toggle + reply threading fix

**Date:** 2026-06-30
**Branch:** feat/portal-admin-parity
**Status:** Approved (build now)

Two related changes to the shared Communication Hub:

- **Part A** — a toggle to view supplier mails that have **no PO number** ("Other Mails"), today stored but invisible.
- **Part B** — fix outbound replies so they **thread** under the original conversation in the recipient's mailbox (currently sent as brand-new mails).

No database migration is required for either part (important: the local env's `DATABASE_URL` points at production).

---

## Part A — "Other Mails" (non-PO supplier mails)

### Definition
An **incoming** `CommunicationMessage` from a **known/mapped supplier** with **no PO**:
`direction == "INCOMING"` AND `supplier_po_no IS NULL` AND (`supplier_id` set OR `supplier_name` matches the supplier).

These are produced today in `mail_fetch_worker` when a mapped supplier emails without a parseable PO. They are **not** customer mails — customer-domain senders go to `CustomerMail` / the Customer Emails view and are out of scope for this toggle.

### Grouping
Non-PO mails are grouped into threads by **normalized subject** per supplier:
strip leading `re:`/`fwd:`/`fw:` tokens, trim, lowercase, collapse internal whitespace. The normalized string is the `thread_key`; the display subject is the most recent message's subject.

### Backend (mirrored in `communication_hub.py` admin + `eportal_hub.py` employee)
1. `/suppliers` — add `non_po_count: int` per supplier (count of incoming non-PO messages, matched by `supplier_id` or uppercased `supplier_name`).
2. New `GET .../suppliers/{supplier_id}/other-mails` (admin) and the eportal equivalent → returns `OtherMailThread[]`:
   `{ thread_key, subject, supplier_id, supplier_name, sender_email, message_count, unread_inbound, last_activity_at }`.
3. Extend `GET /thread` to accept `supplier_id` + `non_po_subject` → returns the existing `CommHubThread` shape with `procurement_record_id=null`, `supplier_po_no=null`, `thread_id="OTHER-<supplier_id>-<thread_key>"`, and `messages` = all non-PO messages in that subject group (ordered by `created_at`).
4. Extend `mark-read` to accept `supplier_id` + `non_po_subject` (marks the group's incoming messages read).
5. `/reply` already accepts a null PO; pass `supplier_id`, `subject`, `body`. Threading handled by Part B.
6. **eportal scoping:** every non-PO endpoint verifies the supplier is in the employee's owned-supplier set via existing `_owned_supplier_names()`; otherwise 404. No cross-employee leakage.

A shared helper `normalize_subject(subject) -> str` lives in `communication_message_service.py` and is used by both routers and the grouping query.

### Frontend (`CommunicationHub.tsx`, shared by both portals)
1. Toggle in the **PURCHASE ORDERS** header (`POs | Other`). POs remain visible; when "Other" is active an **OTHER MAILS** subsection renders below the PO list with thread rows + unread badge.
2. Selecting an other-mail thread loads it via `thread({ supplier_id, non_po_subject })` into the center panel.
3. For a non-PO thread: composer/templates/HI stay enabled (reply works); **Materials dropdown, Details panel, Escalate, and Tasks are hidden** (all PO-centric).
4. New adapter method `otherMails({ supplier_id?, supplier_name? })` wired to admin (`/api/communication-hub/*`) and employee (`/api/eportal/hub/*`) in `mail-history/page.tsx` and `eportal/communication/page.tsx`; new `OtherMailThread` type + `non_po_count` on `CommHubSupplier` in `lib/types.ts`; new calls in `lib/api.ts`; `thread`/`markThreadRead` params extended with optional `supplier_id` + `non_po_subject`.

---

## Part B — Reply threading (no schema change)

### Root cause
`_build_email()` in `mail_send_worker.py` never sets `Message-ID`, `In-Reply-To`, or `References` headers, so every reply is a new mail to the recipient's client. Inbound `Message-ID` is already captured (`message_uid`) and the customer path already stores `in_reply_to`; the supplier path doesn't pass it.

### Fixes
1. **`_build_email()`** — generate a `Message-ID` (`email.utils.make_msgid` using the SMTP-from domain) and set the header. If `msg.in_reply_to` looks like a real Message-ID (contains `@`), set both `In-Reply-To` and `References` to it.
2. **Supplier reply path** (`communication_hub.py reply_now` + the eportal mirror) — before queueing, look up the latest **incoming** message in the thread (by `procurement_record_id`/`supplier_po_no`, or `supplier_id`+normalized subject for non-PO) and pass its `message_uid` as `in_reply_to`. Ensure subject is `Re: <original>` via a shared `reply_subject()` helper.
3. **Customer path** — already correct; the `_build_email` change makes it thread.

### Why no migration
Threading is driven by headers the recipient's client reads. We don't reconstruct threads from headers on our side, so persisting our own outbound Message-ID is unnecessary. `In-Reply-To` + a consistent `Re:` subject thread reliably in Gmail/Outlook.

---

## Testing
- Backend (pytest, in-memory SQLite): `_build_email` emits `Message-ID` always and `In-Reply-To`/`References` when `in_reply_to` is set; the non-PO thread query groups by normalized subject; reply populates `in_reply_to` from the latest inbound. (Pre-existing 2 `test_mail_send_retry` failures are unrelated.)
- Frontend: TypeScript build (`tsc`) + manual check; no component test harness exists.

## Out of scope (YAGNI)
- No tasks/escalation/materials on non-PO threads.
- No `sent_message_id` column / multi-hop `References` chain.
- Customer mails unchanged except they now thread (Part B).

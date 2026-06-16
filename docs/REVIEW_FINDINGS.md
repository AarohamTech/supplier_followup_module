# Logic-Gap Review — Findings Backlog

> Full review of the (vibe-coded) app, 2026-06-16. Fix these one by one and tick them off.
> Severity: **P0** broken/critical · **P1** high · **P2** medium · **P3** low.
> Each item: file → problem → fix. Line numbers are approximate (pre-fix).

---

## 📌 Status / Work Log (so we can resume after a session reset)

**Session 2026-06-16 — round 1 (clear-cut fixes, no decisions):** committed.
- ✅ #1 escape import (PO mail generation restored — verified at runtime)
- ✅ #8 send-mail duplicate-send guard
- ✅ #10 find_today_draft no longer reuses FAILED/CANCELLED drafts
- ✅ #12 escalation tasks now set `task_source="ESCALATION"`
- ✅ #13 customer mails now populate `linked_supplier_po_no`
- ✅ #40 reply key uses a counter (no Date.now collisions)
- ✅ #41 login flash + noisy 401 toast suppressed
- Verified: 35/35 backend tests pass; frontend `tsc` clean.

**⏳ Waiting on your decision (discuss before coding):** #2 RBAC tiers · #5 auto-reply approval ·
#3 webhook auth · #4 default secrets · #6 RED day anchor · #7 BLACK/AI re-follow-up ·
#9 followup_count meaning · #14 customer reply feature · #15 "Save & Notify".

**Not started yet:** all other P2/P3 items below.

---

## P0 — Broken core features & security holes

- [x] **1. PO follow-up mail generation crashes (`escape` not imported).** ✅ FIXED `services/po_followup_mail_service.py:105` uses `escape(...)` but `html.escape` is never imported → **runtime-verified `NameError`**. The error is swallowed by `po_followup_mail_runner` (`scheduler/jobs.py:137`) and the manual `generate-po` path, so **no PO follow-up mail is ever produced**. _Fix: `from html import escape`._
- [ ] **2. The `viewer`/`user` RBAC tier is unenforced — read-only users can mutate everything.** `main.py:87-98` mounts all business routers with only `Depends(get_current_user)`. `require_writer` exists (`core/deps.py:86`) but is used nowhere. A viewer can edit procurement, generate drafts, edit suppliers/escalation emails, create/delete tasks, **mark mail dispatched** (`mail_history.py:92`), and **bulk auto-queue follow-ups** (`po_followups.py:72`). _Fix: apply `require_writer` to mutations and `require_manager` to send/approve/dispatch/auto-queue._
- [ ] **3. Unauthenticated webhooks can trigger real outbound mail.** `routers/webhooks.py` is mounted bare; `POST /api/webhooks/mail-send` runs the SMTP worker. Anyone who can reach the host can flush mail to suppliers. _Fix: require a shared-secret header (or manager JWT)._
- [ ] **4. Known default admin + JWT secret.** `config.py` defaults `SEED_ADMIN_PASSWORD="ChangeMe!123"`; `.env.example` ships `JWT_SECRET=change-me`. A deploy that forgets to override boots with public admin creds and a public signing key (full takeover + forgeable tokens). _Fix: refuse to start when secrets equal defaults outside DEBUG._
- [ ] **5. Auto-reply acks are auto-SENT without approval.** `scheduler/jobs.py:88` creates acks with `status="READY"`; the send worker (`mail_send_worker.py:211`) sends every `OUTGOING/READY` with no `mail_type` filter. Any parser false-positive emails the supplier unsolicited. _Fix: create acks as `DRAFT`/`PENDING_APPROVAL`, or exclude `AUTO_ACK` from the sender until approved._

## P1 — Follow-up engine correctness (the app's core purpose)

- [ ] **6. RED "day index" is anchored to `shipment_date`, not RED onset.** `services/followup_engine.py:28` `red_day_index = days_since(shipment_date)`. A PO that just turned RED but shipped 10 days ago jumps straight to AI/escalation, skipping Day-1/Day-2; one with a near ship date is stuck at Day-1 forever. _Fix: base on `followup_count` or a `red_since` timestamp._
- [ ] **7. BLACK/AI records never get a `next_followup_date`, so the highest-risk POs stall.** `followup_engine.py:113-118`: with `db is None` (the sync, procurement-update, and mail-draft callers) `hours=None` for LEVEL_2/CRITICAL → `next_followup_date=None`. Combined with `po_followup_mail_service.py:397` treating SENT-with-null-next-date as **not due**, BLACK/AI POs get at most one auto-mail then freeze. _Fix: always pass `db`, and treat null-next SENT as due._
- [x] **8. `send-mail` "idempotent" guard is broken → duplicate escalation sends.** ✅ FIXED `communication_hub.py:1060` has a dead `existing` query and the real dedup loop only inspects `status=="READY"`, so an already-`SENT` mail re-queues a fresh READY row and re-sends. _Fix: drop the dead query; match `mail_history_id` across READY **and** SENT._
- [ ] **9. `followup_count` over-counts.** `mail_send_worker.py:166-172` increments per matched procurement record; for a PO-group mail `_target_procurement_rows` returns **all** rows on the PO, so one email bumps N records, and resends bump again. Escalation logic keyed on the count misfires. _Fix: increment once per mail._
- [x] **10. `find_today_draft` ignores `sent_status`.** ✅ FIXED `po_followup_service.py:335` reuses any same-day mail incl. `FAILED`/`CANCELLED`, so regenerating after a failure returns the dead draft and blocks a fresh send. _Fix: filter `sent_status IN ACTIVE_AUTO_STATUSES`._
- [ ] **11. IMAP fetch marks mail `\Seen` before processing → replies lost on transient error.** `mail_fetch_worker.py:259` fetches `(RFC822)` (sets `\Seen`); if `_process_one` throws (swallowed at :267) the reply is gone with no DB row. _Fix: use `BODY.PEEK[]`, set `\Seen` only after a successful commit._
- [x] **12. Escalation tasks never set `task_source="ESCALATION"`.** ✅ FIXED `communication_hub.py:1014` leaves the model default `"SUPPLIER"`, so the `escalation_tasks` KPI (`communication.py:175`) is permanently 0 and escalations are mis-bucketed. _Fix: pass `task_source="ESCALATION"`._
- [x] **13. `linked_supplier_po_no` is never populated.** ✅ FIXED `mail_fetch_worker.py:160-175` builds a `CustomerMail` but drops the already-parsed PO. The column/serializer (`models/customer_mail.py:51`) is always null → customer mails never link to orders. _Fix: set `linked_supplier_po_no=parsed.get("supplier_po_no")`._
- [ ] **14. Customer "Send Response" sends nothing.** `CustomerWorkspace.tsx:217` only appends local state + flips status; there is no reply endpoint/API call. The reply isn't persisted and is lost on refresh; the optimistic bubble is never rolled back on failure. _Fix: add `POST /api/customer-mails/{id}/reply` (backend) + real API call, update UI only on success. (Pairs with the consultation doc's Phase 1.)_
- [ ] **15. "Save & Notify" behaves identically to "Save".** `CustomerTaskModal.tsx` calls `onSave(payload, notify)` but `handleSaveTask` (`CustomerWorkspace.tsx:252`) ignores the flag. _Fix: honor `notify` or remove the button._

## P2 — Medium

- [ ] **16. Timezone inconsistency (`date.today()`/local vs `utcnow()`).** `followup_engine.is_overdue`, the procurement dashboard "overdue/due today", and the dedup windows (`po_followup_service.py:345`, `po_followup_mail_service.py:174`) use local `date.today()` while everything else uses `utcnow()` → off-by-a-day flags and duplicate/missed mails near midnight. _Fix: standardize on UTC dates._
- [ ] **17. Intake identity vs grouping mismatch.** Unique key is `(crm_no, supplier_po_no, material_name)` (no supplier_name) but grouping/mailing buckets on `(supplier_name, supplier_po_no)`; `supplier_name` is updatable in place, so a re-import silently moves a material between groups with no history. _Fix: make intake and grouping agree on identity._
- [ ] **18. PO dedup is per-`mail_type` → escalation re-mails same day.** When a group's signal flips GREEN→RED the `mail_type` changes, so the "already mailed today" guard misses and a 2nd mail goes out. _Fix: dedup on supplier+PO+window only (drop mail_type), or document the intent._
- [ ] **19. Substring PO matching links replies to the wrong PO.** `communication_message_service.find_procurement_record` matches `po in subject+body`; a short/prefix PO matches inside a longer one. _Fix: word-boundary/anchored match._
- [ ] **20. Supplier "health %" is fake; "last subject" is wrong.** `communication_hub._build_supplier_entry` maps signal→one of 4 hardcoded numbers, and `last_subject` takes the newest `MailHistory` (usually our own draft) ignoring inbound `communication_messages`. _Fix: compute real aggregates; derive last activity from newest of mail history + inbound messages._
- [ ] **21. Unread badge totals don't reconcile.** Dashboard counts all unread INCOMING globally; per-PO badges only count those linked to a record/PO. Orphan unread replies inflate the global badge and can't be cleared. _Fix: always link inbound on ingest and/or add an "unmatched" bucket._
- [ ] **22. Send retries have no backoff.** `mail_send_worker.py:228-251` leaves the row `READY`; the next ~5-min tick retries immediately, burning all 3 retries in ~15 min then `FAILED` forever. _Fix: add `next_retry_at` backoff._
- [ ] **23. Customer-mail status/links get stuck.** `customer_mail_service.create_task_from_mail` overwrites `linked_task_id` with the latest task and only bumps OPEN→IN_PROGRESS; `resolve_mail` ignores still-open tasks. _Fix: rely on the `customer_mail_id` reverse link; gate resolve on `open_task_count`._
- [ ] **24. Classifier strands supplier-ish mail in the customer inbox.** `mail_fetch_worker._classify_customer_mail` can stamp `SUPPLIER` (on "supplier"/"vendor"/" po ") for mail that reached the customer inbox precisely because no supplier matched. _Fix: drop those keywords here, or auto-link instead of labeling._
- [ ] **25. `schema_evolve` strips NOT NULL unconditionally + auto-DDL on every startup.** `core/schema_evolve.py:72` ternary is a no-op (always `""`), so evolved columns are always nullable; `main.py` runs `create_all`+`ALTER` every boot with errors swallowed, and Postgres `create_all` won't add new columns at all (silent drift). _Fix: move to Alembic migrations; fix the NOT NULL clause._
- [ ] **26. Last-admin guard race + self-demote/deactivate allowed.** `user_service.update_user` last-admin check is TOCTOU (no row lock) and `PATCH /users/{id}` lets an admin demote/deactivate themselves (only self-*delete* is blocked) → lockout. _Fix: `SELECT … FOR UPDATE`; block self-demotion/deactivation._
- [ ] **27. Password silently truncated to 72 bytes (mid-codepoint).** `core/security.py:20` slices UTF-8 bytes; two long/Unicode passwords sharing a 72-byte prefix authenticate interchangeably. _Fix: SHA-256 pre-hash then bcrypt the digest._
- [ ] **28. CORS `allow_credentials=True` is needless and risky with bearer tokens.** `main.py:69`; dangerous if `CORS_ORIGINS` is ever set to `*`. _Fix: `allow_credentials=False`; reject `*`._
- [ ] **29. Dashboard insights analyze only the current 25-row page.** `dashboard/AIInsights.tsx` + `PoTable.tsx` compute "top supplier"/grouped POs from `list.items` (one page) while showing full-set totals → wrong insights, PO materials split across pages. _Fix: drive from a backend aggregate endpoint._
- [ ] **30. StoreBootstrap shared-error race + mid-load 401 bounce.** `store.ts` `refresh`/`loadSuppliers` overwrite one `error` field concurrently; a token expiring between `me()` and these calls triggers the global redirect. _Fix: separate error state; guard fetches on a confirmed session._
- [ ] **31. Inbound reply-table failures are swallowed; remark-only replies aren't audited.** `mail_fetch_worker.py:220` bare-excepts `apply_material_reply_table`; `status_change_service.apply_parsed_reply` returns `None` for remark-only changes (no `StatusChangeLog`). _Fix: record a parse-error flag; log remark-only updates._
- [ ] **32. Selected customer mail can vanish but effects keep fetching.** `CustomerWorkspace.tsx:107` only auto-selects when `selectedId` is null; if the selected mail leaves the filtered list, `selected` becomes null while task/context effects keep firing for a hidden id. _Fix: reset `selectedId` when it's no longer in `items`._
- [ ] **33. Task create doesn't refresh the mail list → stale tab counts.** `CustomerWorkspace` bumps `taskReloadKey` but not `reloadKey`, so `open_task_count`-based buckets/counts go stale. _Fix: also refresh the list._

## P3 — Low

- [ ] **34. POP3 re-downloads the whole window every cycle** (no high-water UIDL) — wasteful, can starve old mail. `mail_fetch_worker.py:303`.
- [ ] **35. `pick_template` dead `day>2` branch** — RED-past-AI still resolves to the day-2 template. `mail_template_service.py:278`.
- [ ] **36. `highest_signal` coerces unknown signals to GREEN** — bad ERP data makes an at-risk PO look healthy. `po_followup_service.py:41`.
- [ ] **37. Date-format inconsistency** — PO-group mails render ISO dates while single-record mails use `dd-mm-yyyy`. `mail_template_service.py:221`.
- [ ] **38. `status_change_runner` is a no-op dead query.** `scheduler/jobs.py:42`.
- [ ] **39. N+1 in customer-mail list** — 2 count queries per mail × up to 500. `customer_mails.py:47`.
- [x] **40. `LocalReply` key uses `Date.now()`** — duplicate React keys on rapid sends. `CustomerWorkspace.tsx:221`. ✅ FIXED
- [x] **41. Auth UX nits** — `/login` flashes for authed users; the 401 handler throws a noisy toast during redirect. `AppShell.tsx`, `api.ts:64`. ✅ FIXED (login flash + 401 toast; full-reload redirect left as-is)
- [ ] **42. `receivedQty` hardcoded `null`** — the "Received Qty" card always shows "—". `CustomerWorkspace.tsx:155`.
- [ ] **43. `DB_SCHEMA` search_path is unquoted/unvalidated.** `database.py:16`. _Fix: validate `^[a-z_][a-z0-9_]*$`._
- [ ] **44. JWT has no `aud`/`iss` and 8h non-revocable tokens.** `core/security.py`. _Fix: add claims; consider refresh/jti deny-list._
- [ ] **45. `seed_procurement` re-injects sample POs on every startup.** `seed.py:212`. _Fix: gate behind `DEBUG`/`SEED_SAMPLE_DATA`._

---

### Not a bug (checked)
- ~~BCC leak in `mail_send_worker._build_email`~~ — Python's `smtplib.send_message` strips `Bcc`/`Resent-Bcc` headers before transmitting, so recipients don't see them.

### Suggested order
P0 #1 (one line, unblocks the whole PO-mail feature) → P0 #2 (RBAC) → rest of P0 → P1 engine bugs (#6-13) → P1 frontend (#14-15) → P2 → P3.

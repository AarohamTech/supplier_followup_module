# Revert per-user mail → Supplier-to-People assignment

**Date:** 2026-07-05
**Status:** Approved, implementing

## Context

The per-user "send as" mail feature (editable main mailbox + per-user personal SMTP
identities) was built but is not wanted. Replace it with a simpler need: map each
supplier to one or more people so that a supplier's incoming email is routed to those
people in-app.

## Part A — Revert the mail-credentials feature (entirely)

Restore every file the feature commits (`8d52fe1`, `c516b0a`, `367d4bf`, `a42e25c`)
touched to their pre-feature state (from `fcecd88`), and delete the files they added.
Result: Settings returns to the read-only `.env` SMTP/IMAP snapshot; no editable
mailbox, no send-as page, no per-company fetch loop, no encryption/identity code.

- **Delete:** `secret_crypto.py`, `mail_config_service.py`, `mail_identity_service.py`,
  `user_mail_identity.py`, `mail_identities.py` router, `MainMailboxSettings.tsx`, the
  `settings/sending-identities` page, their tests, and the old feature spec.
- **Restore:** the ~15 modified backend/frontend files (workers, routers, services,
  `main.py`, `database.py`, `models/__init__.py`, settings page, sidebar, api client,
  types).
- The PO API docs (`docs/PROCUREMENT_PO_API.md`) are unrelated and stay.
- Drop the 2 stale `test_mail_send_retry` tests that were already failing before this
  work (they patch send-worker internals that an earlier refactor changed), so the
  suite stays green.

## Part B — Supplier → People assignment

### Data model

New **per-company** table `supplier_assignment` (not shared; suppliers are
per-company, like `supplier_master`):

```
id           PK
supplier_id  FK supplier_master (indexed)
user_id      FK users (soft ref; users live in public)
created_at
UNIQUE (supplier_id, user_id)          -- many-to-many: multiple people per supplier
```

New column on `communication_messages` (auto-added by `schema_evolve`):

```
assigned_user_ids  JSON   -- user ids an incoming supplier mail was routed to
```

### Routing on incoming mail

In `mail_fetch_worker._process_one`, on the branch that stores an incoming email as a
supplier-linked `CommunicationMessage` (known supplier), after the message is created:
1. Resolve the supplier's assignees via `supplier_assignment_service`.
2. Stamp `assigned_user_ids` on the message.
3. Create one in-app notification per assignee via
   `notification_service.notify_users(db, ids, type="SUPPLIER_MAIL", title=…, body=…,
   link="/mail-history", supplier_id=…)`.

No external email is sent. Fail-safe: wrap in the existing `notification_service.safe`
pattern so a routing hiccup never breaks ingestion.

### Service — `supplier_assignment_service`

- `list_all(db)` → `[{supplier_id, supplier_name, assignees:[{user_id, full_name, email}]}]`
- `get_assignee_ids(db, supplier_id)` → `[user_id]`
- `set_assignees(db, supplier_id, user_ids)` → replace the set (dedupe, ignore unknown)
- `assignable_users(db)` → active **staff** users (admin/manager/user/viewer)

Assignees are **staff** users: they can open the supplier mail in the Communication
Hub, so the notification link works. (Assigning to employee-portal accounts would need
a dedicated eportal view — out of scope; can be added later.)

### API — router `/api/supplier-assignments` (manager+ for writes)

- `GET  /` — every supplier with its assignees
- `GET  /assignable-users` — users that can be assigned
- `PUT  /{supplier_id}` — body `{ user_ids: [int] }`, replaces that supplier's assignees

Reads open to any staff user; `PUT` requires manager+.

### Frontend — page **Supplier Assignments**

Route `/supplier-assignments` (Administration group, sidebar link, manager+). A
searchable list of suppliers; each row shows current assignees and a multi-select of
people with a Save action. Reuses the app's existing table/card/modal conventions.

## Testing

- Unit: `set_assignees` replace/dedupe/multiple; `get_assignee_ids`; `assignable_users`
  excludes portal accounts.
- Worker: an incoming supplier mail stamps `assigned_user_ids` and creates a
  notification per assignee.
- API: `GET`/`PUT` shapes; manager+ guard on `PUT`; unknown supplier → 404.
- Reuse the in-memory SQLite + hermetic conftest.

## Out of scope

- Assigning suppliers to employee-portal accounts (needs an eportal view).
- A dedicated "supplier mail assigned to me" inbox view (the `assigned_user_ids` column
  enables it later; MVP delivers via notifications).

# Mail Credentials Management + Per-User "Send As" Identities

**Date:** 2026-07-04
**Status:** Approved, implementing

## Problem

Today the mail system uses a single global mailbox hard-configured in `backend/.env`
(`settings.SMTP_*` / `settings.IMAP_*`). It is immutable at runtime — changing
credentials means editing `.env` and restarting. The `/settings` page shows only a
read-only masked snapshot. Every outgoing mail is sent `From: settings.SMTP_FROM`
regardless of who composed it; `sender_email` is stored per-message but ignored at
send time.

Two capabilities are wanted:

1. **Editable main mailbox** — an admin-only, first-position section of `/settings`
   to edit IMAP + SMTP credentials for the mail system, taking effect at runtime.
2. **Per-user "send as" identities** — a page where the **admin** enters personal
   SMTP credentials on behalf of any user; once mapped, all outgoing mail attributed
   to that user is sent through their own mailbox as themselves.

## Decisions (locked with the user)

- **Main mailbox scope:** per-company. Each company's admin edits that company's own
  IMAP/SMTP config.
- **Who manages personal identities:** admin only. Users do not self-serve; the admin
  enters credentials for each user in their company.
- **Which mail sends as the user:** all mail attributable to them — interactive
  compose/replies AND automated follow-ups queued on their behalf.
- **On personal-send failure:** fall back to the main mailbox so delivery still
  happens; log the personal-creds error for the admin.

## Architecture

### Data model & storage

**Main mailbox config → per-company `app_settings`** (already a per-schema table).
New key `mail_config`:

```json
{ "smtp": {"enabled": bool, "host": str, "port": int, "user": str, "password_enc": str, "from": str},
  "imap": {"enabled": bool, "protocol": "IMAP"|"POP3", "use_ssl": bool, "host": str, "port": int,
           "user": str, "password_enc": str, "folder": str} }
```

Resolver precedence: DB row for the current schema wins; the **default/public** schema
falls back to the env `settings.*` values (and is seeded from env on first read) so the
existing 102 mailbox keeps working untouched. A non-default company with no row = "no
mailbox configured" (fetch skips it, send reports disabled).

**Personal identities → new shared table `user_mail_identity`** (added to
`SHARED_TABLES`, lives in `public` alongside `users`):

```
id, user_id (FK users, unique), enabled,
smtp_host, smtp_port, smtp_user, smtp_password_enc, from_email,
use_ssl, created_at, updated_at
```

**Encryption:** passwords stored Fernet-encrypted at rest. The key is derived from the
existing `JWT_SECRET` (SHA-256 → urlsafe-b64), so no new ops burden and no new
dependency (`cryptography` is already present via `python-jose[cryptography]`). A small
`core/secret_crypto.py` handles encrypt/decrypt. API responses only ever return masked
values, never plaintext.

### Backend services & workers

- **`services/mail_config_service.py`** — the single source workers read:
  - `get_smtp_config(db)` / `get_imap_config(db)` → effective decrypted config for the
    current company (DB row, else env fallback for the default schema).
  - `set_smtp_config(db, ...)` / `set_imap_config(db, ...)` → admin writes (encrypt
    password, "leave blank keeps existing").
  - `smtp_config_masked(db)` / `imap_config_masked(db)` → snapshot for the API.
- **`mail_send_worker` refactor** — `_config_ready`, `_open_client`, `_build_email` are
  parameterized by an `SmtpConfig` object + From address instead of reading the global
  `settings`. `_send_bucket` (runs inside `use_company(schema)`) resolves per message:
  1. Owning user via `msg.sender_email` (falling back to the linked PO's owner email).
  2. If that user has an **enabled** `user_mail_identity` → send through it (From = their
     address). Else → company main mailbox.
  3. On personal-send failure → retry once through the main mailbox; log the personal
     error. Clients are opened per distinct identity and reused within the batch.
- **`services/mail_identity_service.py`** — resolve `sender_email` → `User` (active) →
  enabled identity → `SmtpConfig`; CRUD for the admin API.
- **Attribution wiring** — stamp `sender_email` at queue time where missing: staff hub
  compose and employee compose (composing user's email), and automated PO follow-ups
  (the PO owner's user email). Manual portal/employee replies already stamp it.
- **`mail_fetch_worker` / `mail_fetch_runner` refactor** — loop active companies; for
  each, load that company's effective IMAP config and poll **its own** mailbox inside
  `use_company(schema)`. Mailbox→company is direct now (no cross-company supplier
  routing). Default company keeps polling today's inbox via env fallback; unconfigured
  companies are skipped.

### API

Main config (under `/api/settings`, **admin-gated writes** via a new `_ADMIN` dep):
- `GET  /api/settings/mail-config` — effective config, masked.
- `PUT  /api/settings/mail-config/smtp` — admin save.
- `PUT  /api/settings/mail-config/imap` — admin save.
- `POST /api/settings/test-smtp`, `POST /api/settings/test-imap` — test the effective
  (or an optional draft) config.

Personal identities — new admin router `/api/mail-identities` (`require_admin`):
- `GET    /` — users in the admin's company + masked identity status.
- `PUT    /{user_id}` — set/update a user's SMTP identity.
- `DELETE /{user_id}` — remove.
- `POST   /{user_id}/test` — live-test that user's creds.

### Frontend

- `/settings` — new **first** section "Main Mailbox" with editable SMTP + IMAP forms
  (masked passwords, "leave blank to keep"), Save + Test. Read-only for non-admins;
  only admins see the edit/save controls.
- New admin page **Sending Identities** at `/settings/sending-identities` (linked from
  settings; admin-only): table of company users with a "personal mailbox:
  configured / not set / disabled" badge, an edit drawer for SMTP host/port/user/
  password/from + enable toggle, and a per-row "Test" button.

## Security & back-compat

- Passwords encrypted at rest; API returns masked only; write endpoints admin-only; a
  user's identity is editable only by an admin in the same company.
- Default company (102) behavior is byte-identical until an admin edits anything.
  Company 101 has no mailbox until configured.
- Pre-existing plaintext secrets in `backend/.env` are out of scope here (noted).

## Testing

- Unit: crypto round-trip; config resolver precedence (DB > env-default, unconfigured
  company); attribution resolver; send-as selection + main-mailbox fallback on failure
  (mocked SMTP); masked serialization never leaks plaintext.
- Integration: admin can save/read masked main config; non-admin blocked; identity CRUD
  scoped to company; fetch loops per-company config.
- Reuse the in-memory SQLite + hermetic conftest already in place.

## Phasing

1. `secret_crypto` + `mail_config_service` + resolver; worker refactor to read effective
   config (no behavior change).
2. Editable main-mailbox config: API + `/settings` section.
3. Per-company fetch loop.
4. `user_mail_identity` model + `mail_identity_service` + identities API + admin page.
5. Send-as attribution wiring + send-worker send-as + main-mailbox fallback.

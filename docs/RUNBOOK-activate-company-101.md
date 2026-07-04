# Runbook — Activate Company 101 (Enterprise) in Production

**Context.** The multi-company portal (Plans 1–3) is merged to `main`. Deploys are
automated: pushing `main` auto-deploys the **backend to EC2** (`.github/workflows/deploy-backend.yml`,
on `backend/**` changes → `git reset --hard origin/main` → reinstall → `systemctl restart sfa-backend`)
and the **frontend to Vercel**. So the code is (almost certainly) already live. **102 (Hariom Tech)
is unchanged; 101 (Enterprise) is dormant** — an empty `company_101` schema, no CRM feed, no data.

This runbook does the one thing CI does **not**: give 101 its CRM credentials so it starts
ingesting its own POs. **Nothing here touches 102.** Do this only when you have the desk-101
CRM login.

SSH key: the Mumbai box (`MUMBAI_SERVER.pem` / whichever key your `deploy` secret uses).
Backend path on box: `~/supplier_followup_module`. Service: `sfa-backend`.

---

## 0. Pre-check — confirm the new code actually deployed
```bash
ssh -i <your-key>.pem ubuntu@<ec2-host>
cd ~/supplier_followup_module
git log --oneline -1                 # expect the Plan 2 merge (e2f486b) or later on the box
curl -fsS http://localhost:8000/healthz && echo         # {"ok":true}
sudo systemctl is-active sfa-backend # active
```
If `git log` is behind `origin/main`, the auto-deploy didn't run — trigger it manually:
```bash
git fetch origin main && git reset --hard origin/main
cd backend && uv pip install --python .venv/bin/python -r requirements.txt
sudo systemctl restart sfa-backend
```

Confirm the tenant tables exist (proves Plan 1/2 booted). In the app: log in as staff → the
top-bar **company switcher** should be present, and switching to **Enterprise** should turn the
UI **light-blue** (empty data). If you see that, the backend + frontend are live.

---

## 1. Add the desk-101 CRM credentials
```bash
cd ~/supplier_followup_module/backend
cp .env .env.bak.$(date +%Y%m%d-%H%M%S)     # backup first
nano .env
```
Append (or fill) these keys — CODE `101` matches `companies.code`:
```
CRM_101_DESK_ID=101
CRM_101_LOGIN_EMAIL=<desk-101 login email>
CRM_101_LOGIN_PASSWORD=<desk-101 password>
# optional (defaults shown):
# CRM_101_DEVICE_ID=101                       # defaults to CRM_101_DESK_ID
# CRM_101_BASE_URL=                           # defaults to the shared CRM_API_BASE_URL
```
Notes:
- `CRM_INGEST_ENABLED=true` is already set globally (102 uses it) — you do **not** add a new
  enable flag. The per-company loop picks up 101 automatically once `CRM_101_*` resolves.
- If any of desk-id / email / password is missing, 101 ingestion simply stays skipped (safe).

---

## 2. Restart + verify
```bash
sudo systemctl restart sfa-backend
curl -fsS http://localhost:8000/healthz && echo
# watch the first ingest cycle (runs on the CRM_INGEST_INTERVAL, ~3 min):
sudo journalctl -u sfa-backend -f | grep -Ei "crm|ingest|company_101|101"
```
Expect a log line like `[cron] crm_ingestion_runner ... {"101": {"status":"OK", "desk":"101", "created":N,...}, "102": {...}}`.
Then in the app: switch to **Enterprise** → **My POs / dashboard** should start showing 101's POs.

You can also force one run from the app: **CRM Ingestion** page → **Sync now** (while switched
to Enterprise) — it now resolves the *current* company, so it ingests 101 (not 102).

---

## 3. If something looks wrong (rollback is trivial — 102 is never affected)
- **101 ingest logs errors** (bad creds / desk): fix the `CRM_101_*` values, `sudo systemctl restart sfa-backend`. 102 keeps running throughout.
- **Turn 101 ingestion back off:** remove/blank the `CRM_101_*` lines and restart — 101 goes dormant again; its already-ingested data stays in `company_101`.
- **Full revert of the app:** `git reset --hard <previous-good-sha>` in `~/supplier_followup_module` + reinstall + restart (and revert the Vercel deployment from its dashboard). Not expected to be needed.

---

## Deferred / not in this activation
- **101's own mailbox:** 101 currently **shares 102's inbox**; replies are auto-attributed to
  101 by matching the sender against 101's suppliers (disjoint from 102). Give 101 a dedicated
  mailbox later by making the IMAP/SMTP config per-company (future work).
- **101 supplier/employee portal logins:** provision once 101 has suppliers (the accounts are
  pinned per company via `users.company_id`).
- **Staff access:** any existing staff account can already enter Enterprise via the switcher —
  no new users needed.

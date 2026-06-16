# Deploy on Vercel (frontend + FastAPI backend)

Both the Next.js frontend and the FastAPI backend deploy as **Vercel Services**
from this one repo. `vercel.json` (repo root) tells Vercel the two service roots
(`frontend`, `backend`). If Vercel's import screen shows a slightly different
`vercel.json`, prefer the one it generates and just merge in nothing else needed.

> ⚠️ The backend runs **serverless** on Vercel, so it is configured to NOT run the
> in-process scheduler or per-cold-start DB init. See the env vars + cron below.

---

## 0. Push the code first
The deploy uses GitHub `main`. Make sure this branch is merged/pushed to `main`
(otherwise Vercel builds the old code).

## 1. One-time database setup (run locally, once)
Vercel cold starts skip `create_all`/seed (`RUN_STARTUP_INIT=false`), so create the
tables + admin once against the **same DB you'll use in prod**:

```powershell
# from backend/, with the prod DATABASE_URL in .env
.\.venv\Scripts\python.exe -c "from app import seed; print(seed.run())"
```

## 2. Use the Supabase connection POOLER (not the direct host)
Serverless opens many short-lived connections. In the Supabase dashboard →
*Project Settings → Database → Connection string → "Connection pooling"* copy the
**Transaction** pooler URL (port **6543**) and use it as `DATABASE_URL`:

```
postgresql+psycopg2://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:6543/postgres?sslmode=require
```

## 3. Environment variables

### Backend service (Vercel → Project → Settings → Environment Variables)
| Key | Value |
|-----|-------|
| `DATABASE_URL` | the **pooler** URL from step 2 |
| `DB_USE_NULLPOOL` | `true` |
| `RUN_STARTUP_INIT` | `false` |
| `SCHEDULER_ENABLED` | `false` (serverless can't run APScheduler — use cron, step 4) |
| `DEBUG` | `false` |
| `APP_NAME` | `Supplier Follow-up Agent` |
| `CORS_ORIGINS` | `["https://<your-frontend>.vercel.app"]` |
| `JWT_SECRET` | a long random secret |
| `JWT_ALGORITHM` | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `480` |
| `SEED_ADMIN_EMAIL` / `SEED_ADMIN_PASSWORD` / `SEED_ADMIN_NAME` | your admin |
| `WEBHOOK_SECRET` | a long random secret (used by the cron in step 4) |
| `RED_AI_AFTER_DAYS` | `2` |
| `MAIL_INBOX_ENABLED` / `SMTP_ENABLED` | `true` |
| `MAIL_FETCH_PROTOCOL` | `POP3` |
| `MAIL_INBOX_USE_SSL` | `false` |
| `IMAP_HOST/PORT/USER/PASSWORD/FOLDER` | your mailbox |
| `SMTP_HOST/PORT/USER/PASSWORD/FROM` | your SMTP |
| `AUTO_PO_FOLLOWUP_ENABLED` | `false` (keep auto supplier-blasts off until you want them) |
| `LLM_ENABLED` | `true` |
| `LLM_BASE_URL` | `https://integrate.api.nvidia.com/v1` |
| `LLM_API_KEY` | your NVIDIA key |
| `LLM_MODEL` | `meta/llama-3.3-70b-instruct` |
| `*_INTERVAL_MINUTES` | the cron intervals (informational on serverless) |

### Frontend service
| Key | Value |
|-----|-------|
| `NEXT_PUBLIC_API_BASE` | the backend service's URL, e.g. `https://<backend>.vercel.app` |

The frontend's `next.config.mjs` rewrite proxies `/api/*` → `NEXT_PUBLIC_API_BASE`,
so the browser sees same-origin (no CORS headaches).

## 4. Scheduler replacement (external cron)
APScheduler can't run serverless. Vercel Cron on **Hobby is once-per-day** (too rare),
so use a free external cron — [cron-job.org](https://cron-job.org) — to call the
already-built webhook endpoints every few minutes:

| URL (POST) | Header | Suggested interval |
|------------|--------|--------------------|
| `https://<backend>.vercel.app/api/webhooks/mail-fetch` | `X-Webhook-Secret: <WEBHOOK_SECRET>` | every 10 min |
| `https://<backend>.vercel.app/api/webhooks/mail-send` | `X-Webhook-Secret: <WEBHOOK_SECRET>` | every 5 min |

(If you go Vercel **Pro**, you can use native Vercel Cron instead.)

## 5. Deploy
Click **Deploy**. After it's up:
- Frontend: `https://<frontend>.vercel.app` → log in with the seeded admin.
- Backend docs: `https://<backend>.vercel.app/docs`.

---

### Notes / gotchas
- **Cold starts**: first request after idle is slower (~1–3s) while the function warms.
- **Function timeout**: the LLM (`llama-3.3-70b`) is ~0.5s so it's fine; keep heavy/long
  work on the cron path, not the request path.
- **Secrets**: never commit `.env`; set everything in Vercel's env-var UI. Rotate the
  keys that were shared during development.
- Prefer this only if you specifically want all-Vercel. A container host (AWS App
  Runner / Railway / Hetzner) runs the backend **with the scheduler intact, no refactor**.

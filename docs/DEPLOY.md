# Deploy: Frontend on Vercel + Backend on EC2

The browser only ever talks to the Vercel domain; Next.js **rewrites** proxy
`/api/*` server-side to the backend (`NEXT_PUBLIC_API_BASE`). So the backend can
even be plain HTTP without mixed-content errors — though HTTPS is recommended.

---

## A. Frontend → Vercel
On the Vercel "New Project" import screen:
1. **Root Directory → Edit → `frontend`** → Continue. Preset auto-detects **Next.js**.
2. **Environment Variables** → add:
   - `NEXT_PUBLIC_API_BASE` = your backend URL, e.g. `http://<ec2-public-ip>:8000`
     (or `https://api.yourdomain.com`). You can set this after the backend is up,
     then **redeploy** (rewrites are baked at build time).
3. **Deploy.**

Done → `https://<project>.vercel.app`. Log in with the seeded admin.

---

## B. Backend → EC2 (Ubuntu, simplest path)

### 1. Launch
- Ubuntu 22.04/24.04, `t3.small` (or `t2.micro` free tier; small is safer).
- **Security group inbound:** `22` (your IP), `8000` (0.0.0.0/0) — or `80/443` if you add nginx.

### 2. Install + clone
```bash
sudo apt update && sudo apt install -y python3-venv python3-pip git
git clone https://github.com/AarohamTech/supplier_followup_module.git
cd supplier_followup_module/backend
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

### 3. Configure `.env`
Create `backend/.env` from `.env.example` with **production** values. Keep the
container/VM defaults (NOT the serverless ones):
```
SCHEDULER_ENABLED=true       # the scheduler runs in-process here (good)
RUN_STARTUP_INIT=true
DB_USE_NULLPOOL=false
DATABASE_URL=postgresql+psycopg2://postgres:<pw>@db.<ref>.supabase.co:5432/postgres?sslmode=require
CORS_ORIGINS=["https://<your-frontend>.vercel.app"]
JWT_SECRET=<long random>
WEBHOOK_SECRET=<long random>
# + the IMAP/SMTP and LLM_* values
```
Tables + admin already exist in your Supabase DB, so first boot just verifies them.

### 4. Run as a service (systemd)
Copy `deploy/backend.service` to `/etc/systemd/system/`, edit the paths/user if
needed, then:
```bash
sudo cp ../deploy/backend.service /etc/systemd/system/sfa-backend.service
sudo systemctl daemon-reload
sudo systemctl enable --now sfa-backend
sudo systemctl status sfa-backend      # check it's running
curl http://localhost:8000/healthz     # {"ok":true}
```

### 5. Wire the frontend
Set Vercel's `NEXT_PUBLIC_API_BASE` to `http://<ec2-public-ip>:8000` and redeploy
the frontend. Test login.

### 6. (Recommended) Add HTTPS
The Vercel→EC2 hop is over the public internet. For real use, put **Caddy** or
**nginx + certbot** in front (terminate TLS on `443`, proxy to `127.0.0.1:8000`),
point a domain at the EC2 IP, and set `NEXT_PUBLIC_API_BASE=https://api.yourdomain.com`.

---

### Notes
- Because the scheduler runs in-process on EC2, you do **not** need the external
  cron — mail fetch/send run on their intervals automatically.
- 🔐 Rotate every secret shared during development and use fresh ones in prod.
- Logs: `journalctl -u sfa-backend -f`.

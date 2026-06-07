# Supplier Follow-up Agent

AI-driven industrial procurement control tower. PO-wise & material-wise automated supplier follow-up system.

## Stack

| Layer        | Tech |
| ------------ | ---- |
| Frontend     | Next.js 14 (App Router) · TypeScript · Tailwind · ShadCN UI · Recharts · TanStack Table |
| Backend      | FastAPI · SQLAlchemy 2.0 · Pydantic v2 · APScheduler |
| Database     | PostgreSQL 15 |
| Auth         | JWT (OAuth2 password flow) |
| Mail         | Gmail API / Outlook Graph API (with SMTP fallback) |
| AI           | Pluggable LLM provider (OpenAI / Azure OpenAI / Local) |
| Deploy       | Docker · docker-compose · Nginx · Ubuntu VPS |

## Repo Layout

```
backend/    FastAPI service, models, services, scheduler
frontend/   Next.js 14 app
deploy/     docker-compose, nginx, env templates
docs/       Architecture, schema, phase plan
```

## Quick start

```powershell
# 1. copy env
Copy-Item deploy/.env.example deploy/.env

# 2. start everything
docker compose -f deploy/docker-compose.yml up --build
```

- Frontend: http://localhost:3000
- Backend:  http://localhost:8000/docs
- DB:       localhost:5432 (postgres/postgres)

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full design, schema, AI strategy and phase-wise rollout plan.

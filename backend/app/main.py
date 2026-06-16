from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from fastapi import Depends

from .core.config import settings
from .core.deps import get_current_user
from .core.logging import setup_logging
from .core.schema_evolve import ensure_columns
from .database import Base, engine, ensure_schema
from .routers import (
    auth,
    customer_mails,
    procurement,
    suppliers,
    supplier_emails,
    mail_drafts,
    mail_history,
    communication,
    communication_hub,
    users,
    webhooks,
    po_followups,
    settings as settings_router,
)
from .scheduler import register_all_specs, start_scheduler, stop_scheduler
from . import seed as seed_module

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging("DEBUG" if settings.DEBUG else "INFO")
    try:
        ensure_schema()
    except Exception:  # noqa: BLE001
        log.exception("Schema bootstrap failed (continuing)")
    Base.metadata.create_all(bind=engine)
    try:
        changes = ensure_columns(engine)
        if changes:
            log.info("Schema evolve added columns: %s", ", ".join(changes))
    except Exception:  # noqa: BLE001
        log.exception("Schema evolve failed (continuing)")
    try:
        register_all_specs()
    except Exception:  # noqa: BLE001
        log.exception("Engine job registration failed (continuing)")
    try:
        result = seed_module.run()
        log.info("Seed result: %s", result)
    except Exception:  # noqa: BLE001
        log.exception("Seed failed (continuing)")
    try:
        start_scheduler()
    except Exception:  # noqa: BLE001
        log.exception("Scheduler start failed (continuing)")
    try:
        yield
    finally:
        stop_scheduler()


app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Open routers (no auth): login + machine-to-machine webhooks.
app.include_router(auth.router)
app.include_router(webhooks.router)

# Admin-only user management (guards itself at the router level).
app.include_router(users.router)

# All business routers require a logged-in user. Fine-grained role checks are
# applied inside the routers that expose sensitive actions (send/escalate,
# settings writes). See docs/progress.md for the permission matrix.
_auth = [Depends(get_current_user)]
app.include_router(procurement.router, dependencies=_auth)
app.include_router(suppliers.router, dependencies=_auth)
app.include_router(supplier_emails.router, dependencies=_auth)
app.include_router(mail_drafts.router, dependencies=_auth)
app.include_router(mail_history.router, dependencies=_auth)
app.include_router(communication.router, dependencies=_auth)
app.include_router(communication.tasks_router, dependencies=_auth)
app.include_router(communication_hub.router, dependencies=_auth)
app.include_router(customer_mails.router, dependencies=_auth)
app.include_router(po_followups.router, dependencies=_auth)
app.include_router(settings_router.router, dependencies=_auth)


@app.get("/")
def root():
    return {"app": settings.APP_NAME, "status": "ok", "docs": "/docs"}


@app.get("/healthz")
def healthz():
    return {"ok": True}

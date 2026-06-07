from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .core.config import settings
from .core.logging import setup_logging
from .core.schema_evolve import ensure_columns
from .database import Base, engine
from .routers import (
    customer_mails,
    procurement,
    suppliers,
    supplier_emails,
    mail_drafts,
    mail_history,
    communication,
    communication_hub,
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

app.include_router(procurement.router)
app.include_router(suppliers.router)
app.include_router(supplier_emails.router)
app.include_router(mail_drafts.router)
app.include_router(mail_history.router)
app.include_router(communication.router)
app.include_router(communication.tasks_router)
app.include_router(communication_hub.router)
app.include_router(customer_mails.router)
app.include_router(webhooks.router)
app.include_router(po_followups.router)
app.include_router(settings_router.router)


@app.get("/")
def root():
    return {"app": settings.APP_NAME, "status": "ok", "docs": "/docs"}


@app.get("/healthz")
def healthz():
    return {"ok": True}

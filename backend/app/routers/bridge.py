"""Machine-to-machine door for ZanFlow Materials.

ZanFlow assigns a material line to somebody; that line has to become a task
here, in front of the same person, in the portal they already have open. This
router is the inbound half of that. The outbound half — status and comments
travelling back — lives in `services/bridge_service.notify_zanflow`, called
from `routers/communication.py`.

Authentication is the shared secret, reusing `webhooks.require_webhook_secret`
verbatim: same threat model, same header, same fail-closed behaviour when no
secret is configured. There is no user session behind these calls, so none of
the RBAC guards apply and none would mean anything.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.tenant import DEFAULT_SCHEMA, reset_current_schema, set_current_schema
from ..database import get_db
from ..models.user import User
from ..schemas.bridge import BridgeCommentIn, BridgeTaskIn, BridgeTaskOut
from ..services import bridge_service as bridge
from ..services import company_service
from ..services import task_assignment_service as assign
from ..services import task_collaboration_service as collab
from .webhooks import require_webhook_secret

log = logging.getLogger(__name__)


async def use_zanflow_company():
    """Bind the company whose schema bridged tasks belong in.

    **Async on purpose.** FastAPI runs a *sync* generator dependency in a
    threadpool, and the code before and after the `yield` can end up in
    different contexts — so the token from `set_current_schema` cannot be reset
    and the teardown raises `ValueError: <Token> was created in a different
    Context`, turning every call into a 500 *after* the handler has already
    committed. An async dependency stays on one task, so setup and teardown
    share a context; the value still reaches the sync handler because
    `run_in_threadpool` copies the context in. `TenantMiddleware` avoids the
    same trap by being raw ASGI rather than `BaseHTTPMiddleware`.

    `TenantMiddleware` reads the company from the JWT, and this router has no
    JWT — its caller is a machine holding a shared secret. So without this
    every bridged task lands in the *default* company, and anyone signed in to
    a different one sees nothing ZanFlow has sent. That is not a visible
    failure: the push reports SYNCED, the task exists, and it is simply in a
    schema the person looking is not reading.

    Set before the handler runs, which is early enough: the engine pins
    `search_path` when a connection is *checked out*, and the session from
    `get_db` has not issued a query yet.
    """
    schema = DEFAULT_SCHEMA
    code = (settings.ZANFLOW_COMPANY or "").strip()
    if code:
        try:
            schema = company_service.get_schema_for_code(code)
        except Exception:  # noqa: BLE001 — a bad code must not take the door down
            log.warning("bridge: ZANFLOW_COMPANY=%r did not resolve; using %s",
                        code, DEFAULT_SCHEMA)
    token = set_current_schema(schema)
    try:
        yield
    finally:
        reset_current_schema(token)


router = APIRouter(
    prefix="/api/bridge",
    tags=["bridge"],
    dependencies=[Depends(require_webhook_secret), Depends(use_zanflow_company)],
)


@router.get("/assignees")
def bridge_assignees(db: Session = Depends(get_db), email: str | None = None) -> list[dict]:
    """The accounts ZanFlow may map its own users onto.

    Wraps `task_assignment_service.list_assignees` — active staff and employee
    accounts, suppliers excluded — and adds the email address, which the plain
    assignee picker does not need but a mapping screen in another system does.
    `email` narrows the result to one address.

    Query parameters are plain defaults rather than `Query(...)` throughout this
    router: the test suite calls these functions directly, and a `Query` object
    arriving as a literal value is a failure mode with no upside here.
    """
    rows = assign.list_assignees(db)
    by_id = {
        u.id: u
        for u in db.query(User).filter(User.id.in_([r["id"] for r in rows] or [0])).all()
    }
    out = [{**r, "email": getattr(by_id.get(r["id"]), "email", None)} for r in rows]
    if email:
        needle = email.strip().lower()
        out = [r for r in out if (r.get("email") or "").lower() == needle]
    return out


@router.post("/tasks", response_model=BridgeTaskOut, status_code=200)
def upsert_bridge_task(payload: BridgeTaskIn, db: Session = Depends(get_db)) -> BridgeTaskOut:
    """Create or update the task mirroring one external record.

    Deliberately `200` rather than `201`: the caller is retrying an upsert, not
    asking whether this is the first time. Whether a row was created is in the
    body, where it is information rather than a status code the caller has to
    branch on.
    """
    task, created, unmapped = bridge.upsert_external_task(
        db,
        external_system=payload.external_system,
        external_ref=payload.external_ref,
        title=payload.title,
        external_url=payload.external_url,
        description=payload.description,
        material_name=payload.material_name,
        priority=payload.priority,
        status=payload.status,
        due_date=payload.due_date,
        assignee=payload.assignee.model_dump() if payload.assignee else None,
        assigned_by=payload.assigned_by,
    )

    if created:
        collab.log_activity(
            db,
            task_id=task.id,
            activity_type="CREATED",
            new_value=task.title,
            created_by=payload.assigned_by or payload.external_system,
        )

    db.commit()
    db.refresh(task)

    if unmapped:
        log.info(
            "bridge: %s/%s has no account here for %r — left on the staff board",
            payload.external_system, payload.external_ref,
            payload.assignee.display_name if payload.assignee else None,
        )

    return BridgeTaskOut(
        task_id=task.id,
        created=created,
        status=task.status,
        assigned_to_user_id=task.assigned_to_user_id,
        assigned_to=task.assigned_to,
        unmapped_assignee=unmapped,
    )


@router.post("/tasks/{external_ref}/comments", status_code=201)
def add_bridge_comment(
    external_ref: str,
    payload: BridgeCommentIn,
    db: Session = Depends(get_db),
    external_system: str = "zanflow",
) -> dict:
    """A comment made on the material line, mirrored onto the task.

    Deliberately NOT routed through `communication.add_task_comment`, which is
    what the staff board and the portals use. That function calls
    `notify_zanflow` on the way out — so reusing it here would send this very
    comment straight back to the system it came from, which would write it to
    the line again, which would push it here again. The two directions stay
    loop-free because each one enters by a door the other never uses.
    """
    task = bridge.find_external_task(
        db, external_system=external_system, external_ref=external_ref
    )
    if task is None:
        raise HTTPException(404, f"No bridged task for {external_ref!r}")

    text = (payload.comment or "").strip()
    if not text:
        raise HTTPException(422, "comment is required")

    author = (payload.author or "").strip() or "ZanFlow"
    row = collab.add_comment(
        db,
        task_id=task.id,
        # Attributed in the text: the author has no account here, and
        # `created_by` is what the card shows.
        comment=text,
        created_by=author,
        created_by_id=None,
    )
    db.commit()
    return {"id": row.id, "task_id": task.id, "created_by": author}


@router.get("/tasks/{external_ref}")
def read_bridge_task(
    external_ref: str,
    db: Session = Depends(get_db),
    external_system: str = "zanflow",
) -> dict:
    """What this system currently holds for one external record.

    The sending system uses it to reconcile after its own callback log shows a
    gap — cheaper and less alarming than re-pushing to find out.
    """
    task = bridge.find_external_task(
        db, external_system=external_system, external_ref=external_ref
    )
    if task is None:
        return {"found": False}
    return {
        "found": True,
        "task_id": task.id,
        "title": task.title,
        "status": task.status,
        "progress_percent": task.progress_percent,
        "assigned_to": task.assigned_to,
        "assigned_to_user_id": task.assigned_to_user_id,
        "updated_at": task.updated_at,
    }

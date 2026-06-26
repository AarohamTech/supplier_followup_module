"""In-app notifications — available to ANY logged-in user (staff or supplier).

Mounted with `get_current_user` (not the staff/supplier guards) so both
audiences read their own notifications from the same endpoints.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..core.deps import get_current_user
from ..database import get_db
from ..models.user import User
from ..schemas.notification import NotificationOut
from ..services import notification_service as svc

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationOut])
def list_notifications(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    only_unread: bool = Query(default=False),
    limit: int = Query(default=30, ge=1, le=100),
):
    return svc.list_for_user(db, user.id, only_unread=only_unread, limit=limit)


@router.get("/unread-count")
def unread_count(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return {"count": svc.unread_count(db, user.id)}


@router.post("/{notification_id}/read")
def mark_read(
    notification_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return {"ok": svc.mark_read(db, user.id, notification_id)}


@router.post("/read-all")
def mark_all_read(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return {"ok": True, "updated": svc.mark_all_read(db, user.id)}

"""Staff file attachments (chat / communication hub uploads).

Upload first (unbound), then the message-send endpoints bind the returned ids
to the created `communication_messages` row. Downloads are proxied from the
private S3 bucket. Employee- and supplier-scoped variants live in their own
routers (`employee_portal.py`, `portal.py`) with own-PO visibility rules; staff
can download any attachment.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..core.deps import get_current_staff
from ..database import get_db
from ..models.message_attachment import MessageAttachment
from ..models.user import User
from ..schemas.attachment import AttachmentOut
from ..services import attachment_service

router = APIRouter(prefix="/api/attachments", tags=["attachments"])


@router.post("/upload", response_model=AttachmentOut, status_code=201)
async def upload(
    file: UploadFile = File(...),
    user: User = Depends(get_current_staff),
    db: Session = Depends(get_db),
) -> dict:
    if not attachment_service.storage_enabled():
        raise HTTPException(503, attachment_service.disabled_reason())
    data = await file.read()
    try:
        att = attachment_service.save_upload(
            db,
            data=data,
            filename=file.filename,
            content_type=file.content_type,
            uploaded_by_kind="staff",
            uploaded_by_id=user.id,
            uploaded_by_label=user.full_name or user.email,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return attachment_service.out(att)


def attachment_response(att: MessageAttachment) -> Response:
    """Stream the stored bytes back as a download (shared by the scoped routers)."""
    try:
        data = attachment_service.get_bytes(att)
    except Exception:  # noqa: BLE001
        raise HTTPException(502, "Could not fetch the file from storage")
    return Response(
        content=data,
        media_type=att.content_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{att.filename}"'},
    )


@router.get("/{attachment_id}/download")
def download(
    attachment_id: int,
    user: User = Depends(get_current_staff),
    db: Session = Depends(get_db),
) -> Response:
    att = db.get(MessageAttachment, attachment_id)
    if att is None:
        raise HTTPException(404, "Attachment not found")
    return attachment_response(att)

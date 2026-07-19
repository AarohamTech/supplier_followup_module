from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class MessageAttachment(Base):
    """A user-uploaded file (or inbound mail attachment) stored in S3.

    Uploaded first (unbound), then bound to a `communication_messages` row when
    the message is sent — an unbound row is a draft attachment. `uploaded_by_*`
    records who uploaded it (staff / employee / supplier) so the scoped download
    endpoints can enforce visibility, and `supplier_id` pre-scopes supplier
    uploads before they are bound to a message.
    """

    __tablename__ = "message_attachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[int | None] = mapped_column(
        ForeignKey("communication_messages.id"), index=True
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(128))
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Object key in the S3 bucket (never exposed to clients).
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    uploaded_by_kind: Mapped[str] = mapped_column(String(16), nullable=False)  # staff/employee/supplier
    uploaded_by_id: Mapped[int | None] = mapped_column(Integer)
    uploaded_by_label: Mapped[str | None] = mapped_column(String(128))
    supplier_id: Mapped[int | None] = mapped_column(Integer, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

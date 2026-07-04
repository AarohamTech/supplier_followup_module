"""Per-user personal SMTP identity ("send as" credentials).

An admin maps a user's own outgoing mail server here so that all outgoing mail
attributed to that user is sent through their mailbox, as them. Passwords are
stored encrypted at rest (``core.secret_crypto``). Lives in ``public`` (shared,
like ``users``) since a user belongs to exactly one company.
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class UserMailIdentity(Base):
    __tablename__ = "user_mail_identity"

    id: Mapped[int] = mapped_column(primary_key=True)
    # One identity per user. FK to the shared `users` table (same schema).
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), unique=True, index=True, nullable=False
    )
    # When false, the user's mail falls back to the company main mailbox.
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    smtp_host: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    smtp_port: Mapped[int] = mapped_column(Integer, default=587, nullable=False)
    smtp_user: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    smtp_password_enc: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # The From address recipients see. Defaults to smtp_user / the account email.
    from_email: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    use_ssl: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

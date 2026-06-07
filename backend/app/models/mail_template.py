from datetime import datetime
from sqlalchemy import String, Integer, Boolean, DateTime, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from ..database import Base


class MailTemplate(Base):
    __tablename__ = "mail_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    template_name: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    signal: Mapped[str] = mapped_column(String(16), index=True)         # GREEN|YELLOW|RED|BLACK
    day_no: Mapped[int] = mapped_column(Integer, default=0)              # 0=any/initial, 1=day1, 2=day2
    subject_template: Mapped[str] = mapped_column(String(500))
    body_template: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

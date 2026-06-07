from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class MailTemplateBase(BaseModel):
    template_name: str
    signal: str
    day_no: int = 0
    subject_template: str
    body_template: str
    active: bool = True


class MailTemplateCreate(MailTemplateBase):
    pass


class MailTemplateUpdate(BaseModel):
    template_name: Optional[str] = None
    signal: Optional[str] = None
    day_no: Optional[int] = None
    subject_template: Optional[str] = None
    body_template: Optional[str] = None
    active: Optional[bool] = None


class MailTemplateOut(MailTemplateBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    updated_at: datetime

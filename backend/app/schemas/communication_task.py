from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


TaskStatus = Literal[
    "BACKLOG",
    "TODO",
    "IN_PROGRESS",
    "WAITING_SUPPLIER",
    "WAITING_CUSTOMER",
    "BLOCKED",
    "DONE",
]
TaskPriority = Literal["P0", "P1", "P2", "P3"]
TaskSignal = Literal["GREEN", "YELLOW", "RED", "BLACK"]
TaskSource = Literal["SUPPLIER", "CUSTOMER", "INTERNAL", "ESCALATION"]


class CommunicationTaskBase(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    supplier_id: Optional[int] = None
    supplier_name: Optional[str] = None
    supplier_po_no: Optional[str] = None
    procurement_record_id: Optional[int] = None
    linked_mail_id: Optional[int] = None
    customer_mail_id: Optional[int] = None
    material_name: Optional[str] = None
    task_source: TaskSource = "SUPPLIER"
    created_from_mail_id: Optional[int] = None
    assigned_to: Optional[str] = None
    assigned_to_user_id: Optional[int] = None
    assigned_by: Optional[str] = None
    watchers: list[int] = Field(default_factory=list)
    priority: TaskPriority = "P2"
    status: TaskStatus = "TODO"
    signal: TaskSignal = "YELLOW"
    escalation_level: int = 0
    progress_percent: int = Field(default=0, ge=0, le=100)
    due_date: Optional[datetime] = None
    reminder_at: Optional[datetime] = None


class CommunicationTaskCreate(CommunicationTaskBase):
    pass


class CommunicationTaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    assigned_to: Optional[str] = None
    assigned_to_user_id: Optional[int] = None
    watchers: Optional[list[int]] = None
    priority: Optional[TaskPriority] = None
    status: Optional[TaskStatus] = None
    signal: Optional[TaskSignal] = None
    task_source: Optional[TaskSource] = None
    material_name: Optional[str] = None
    escalation_level: Optional[int] = None
    due_date: Optional[datetime] = None
    reminder_at: Optional[datetime] = None
    progress_percent: Optional[int] = Field(default=None, ge=0, le=100)


class CommunicationTaskOut(CommunicationTaskBase):
    model_config = ConfigDict(from_attributes=True)

    @field_validator("watchers", mode="before")
    @classmethod
    def _coerce_watchers(cls, v):
        if not v:
            return []
        out: list[int] = []
        for item in v:
            try:
                out.append(int(item))
            except (TypeError, ValueError):
                continue  # drop legacy free-text watcher names (pre-migration data)
        return out

    id: int
    comments_count: int = 0
    attachment_count: int = 0
    closed_at: Optional[datetime] = None
    assigned_at: Optional[datetime] = None
    ai_summary: Optional[str] = None
    ai_summary_at: Optional[datetime] = None
    ai_summary_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime

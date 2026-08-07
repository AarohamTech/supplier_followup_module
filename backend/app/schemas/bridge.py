"""Wire types for /api/bridge — the door ZanFlow Materials pushes tasks through.

Deliberately narrower than `CommunicationTaskCreate`: an external system may
describe a piece of work, but it may not choose its `task_source`, its signal,
its watchers or its escalation level. Those belong to whoever works the task
here.
"""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class BridgeAssignee(BaseModel):
    """Who the sending system thinks should own this.

    All three are optional and tried in order — see
    `services/bridge_service._resolve_assignee`. `followup_user_id` is a cache
    of an administrator's mapping, `email` is the fallback that survives the
    cache going stale, `display_name` is what goes on the card when neither
    finds an account.
    """

    followup_user_id: Optional[int] = None
    email: Optional[str] = None
    display_name: Optional[str] = None


class BridgeTaskIn(BaseModel):
    external_system: Literal["zanflow"]
    external_ref: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=255)
    external_url: Optional[str] = Field(default=None, max_length=512)
    description: Optional[str] = None
    material_name: Optional[str] = Field(default=None, max_length=500)
    priority: Literal["LOW", "MEDIUM", "HIGH"] = "MEDIUM"
    #: Seeds a new task only. An existing task keeps the status it has here.
    status: Literal[
        "BACKLOG", "TODO", "IN_PROGRESS", "WAITING_SUPPLIER",
        "WAITING_CUSTOMER", "BLOCKED", "DONE",
    ] = "TODO"
    due_date: Optional[datetime] = None
    assignee: Optional[BridgeAssignee] = None
    assigned_by: Optional[str] = Field(default=None, max_length=128)


class BridgeTaskOut(BaseModel):
    task_id: int
    created: bool
    status: str
    assigned_to_user_id: Optional[int] = None
    assigned_to: Optional[str] = None
    #: True when an assignee was named but no account here matched it. The task
    #: exists and sits on the staff board; the sending system surfaces this as
    #: "needs mapping" rather than as a failure.
    unmapped_assignee: bool = False

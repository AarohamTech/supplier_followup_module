"""Persistence helpers for PO-scoped HI-assistant conversations."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.agent_subscription import AgentSubscription
from ..models.communication_message import CommunicationMessage
from ..models.hi_agent_chat_message import HiAgentChatMessage


def po_thread_id(procurement_record_id: int) -> str:
    """The PO record ID is the durable assistant thread ID."""
    return str(procurement_record_id)


def _rows(db: Session, procurement_record_id: int) -> list[HiAgentChatMessage]:
    return list(
        db.scalars(
            select(HiAgentChatMessage)
            .where(HiAgentChatMessage.thread_id == po_thread_id(procurement_record_id))
            .order_by(HiAgentChatMessage.created_at.asc(), HiAgentChatMessage.id.asc())
        ).all()
    )


def _action_is_pending(db: Session, action: dict[str, Any]) -> bool:
    if action.get("type") == "draft" and action.get("message_id") is not None:
        draft = db.get(CommunicationMessage, int(action["message_id"]))
        return bool(draft and draft.direction == "OUTGOING" and draft.status == "DRAFT")
    if action.get("type") == "subscription" and action.get("subscription_id") is not None:
        sub = db.get(AgentSubscription, int(action["subscription_id"]))
        return bool(sub and sub.status == "PENDING")
    return False


def _out(db: Session, row: HiAgentChatMessage) -> dict[str, Any]:
    actions = [dict(a) for a in (row.actions or []) if _action_is_pending(db, a)]
    return {
        "id": row.id,
        "role": row.role,
        "text": row.content,
        "actions": actions,
        "created_at": row.created_at.isoformat(),
    }


def history(db: Session, procurement_record_id: int) -> dict[str, Any]:
    return {
        "thread_id": po_thread_id(procurement_record_id),
        "messages": [_out(db, row) for row in _rows(db, procurement_record_id)],
    }


def llm_context(
    db: Session, procurement_record_id: int, *, limit: int = 20
) -> list[dict[str, str]]:
    rows = _rows(db, procurement_record_id)[-limit:]
    return [{"role": row.role, "content": row.content} for row in rows]


def append_exchange(
    db: Session,
    *,
    procurement_record_id: int,
    user_id: int | None,
    user_text: str,
    assistant_text: str,
    actions: list[dict[str, Any]] | None = None,
) -> None:
    thread_id = po_thread_id(procurement_record_id)
    db.add_all(
        [
            HiAgentChatMessage(
                thread_id=thread_id,
                procurement_record_id=procurement_record_id,
                user_id=user_id,
                role="user",
                content=user_text,
                actions=[],
            ),
            HiAgentChatMessage(
                thread_id=thread_id,
                procurement_record_id=procurement_record_id,
                user_id=user_id,
                role="assistant",
                content=assistant_text,
                actions=list(actions or []),
            ),
        ]
    )
    db.commit()


def dismiss_action(
    db: Session,
    *,
    chat_message_id: int,
    action_type: str,
    action_id: int,
) -> HiAgentChatMessage | None:
    row = db.get(HiAgentChatMessage, chat_message_id)
    if row is None:
        return None
    id_key = "message_id" if action_type == "draft" else "subscription_id"
    row.actions = [
        a
        for a in (row.actions or [])
        if not (a.get("type") == action_type and a.get(id_key) == action_id)
    ]
    db.commit()
    db.refresh(row)
    return row


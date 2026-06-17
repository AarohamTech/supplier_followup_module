"""AI router — everything LLM-facing lives under /api/ai so it never mixes with
the procurement / mail / customer-mail endpoints.

  GET  /api/ai/health                        → config status (no network call)
  GET  /api/ai/tools                          → tools the agent can call
  POST /api/ai/chat                           → agentic Assistant turn (tool calls)
  POST /api/ai/triage/customer-mail/{id}      → classify a customer mail
  POST /api/ai/summary/customer-mail/{id}     → summarise a customer mail thread
  GET  /api/ai/memory/stats                   → vector store status
  POST /api/ai/memory/backfill                → embed existing mails/replies
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.deps import require_manager, require_writer
from ..database import get_db
from ..services import (
    ai_insights_service,
    ai_service,
    ai_tools_service,
    knowledge_indexer,
    vector_store,
)
from ..services.ai_service import AIDisabledError

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai", tags=["ai"])


class ChatMessage(BaseModel):
    role: str = "user"
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(default_factory=list)
    # Let the caller force a plain (non-agentic) turn if desired.
    use_tools: bool | None = None


class ToolUse(BaseModel):
    name: str
    args: dict = Field(default_factory=dict)


class ChatResponse(BaseModel):
    reply: str
    model: str
    tools_used: list[ToolUse] = Field(default_factory=list)


@router.get("/health")
def ai_health() -> dict:
    return ai_service.health()


@router.get("/tools")
def ai_tools() -> dict:
    specs = ai_tools_service.tool_specs()
    return {
        "agent_enabled": bool(settings.AI_AGENT_ENABLED and ai_service.is_enabled()),
        "tools": [s["function"]["name"] for s in specs],
    }


@router.post("/chat", response_model=ChatResponse)
def ai_chat(payload: ChatRequest, db: Session = Depends(get_db)) -> ChatResponse:
    if not payload.messages:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "messages cannot be empty")

    messages = [m.model_dump() for m in payload.messages]
    use_tools = (
        settings.AI_AGENT_ENABLED if payload.use_tools is None else payload.use_tools
    )
    try:
        if use_tools and ai_service.is_enabled():
            result = ai_service.chat_with_tools(
                messages,
                tools=ai_tools_service.tool_specs(),
                executor=ai_tools_service.make_executor(db),
            )
            reply = result["reply"]
            tools_used = result.get("tools_used", [])
        else:
            reply = ai_service.chat(messages)
            tools_used = []
    except AIDisabledError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))
    except Exception as exc:  # noqa: BLE001 — surface upstream LLM errors cleanly
        log.exception("AI chat failed")
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"AI request failed: {exc}")

    return ChatResponse(
        reply=reply,
        model=settings.LLM_MODEL,
        tools_used=[ToolUse(**t) for t in tools_used],
    )


@router.post("/triage/customer-mail/{mail_id}")
def triage_customer_mail(
    mail_id: int,
    db: Session = Depends(get_db),
    _user=Depends(require_writer),
) -> dict:
    from ..models.customer_mail import CustomerMail

    mail = db.get(CustomerMail, mail_id)
    if mail is None:
        raise HTTPException(404, "Customer mail not found")
    result = ai_insights_service.triage_mail(db, mail, use_ai=True)
    return {"ok": True, "mail_id": mail_id, **result, "triaged_at": mail.ai_triaged_at}


@router.post("/summary/customer-mail/{mail_id}")
def summarize_customer_mail(
    mail_id: int,
    db: Session = Depends(get_db),
    _user=Depends(require_writer),
) -> dict:
    summary = ai_insights_service.summarize_customer_mail(db, mail_id)
    if summary is None:
        raise HTTPException(404, "Customer mail not found")
    return {"ok": True, "mail_id": mail_id, "summary": summary}


@router.get("/memory/stats")
def memory_stats(db: Session = Depends(get_db)) -> dict:
    return {
        "embeddings": ai_service.health().get("rag"),
        "store": vector_store.stats(db),
        "indexer_enabled": knowledge_indexer.enabled(),
    }


@router.post("/memory/backfill")
def memory_backfill(
    db: Session = Depends(get_db),
    limit: int = 500,
    _user=Depends(require_manager),
) -> dict:
    if not knowledge_indexer.enabled():
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "RAG is disabled or the vector store is unavailable (Postgres + RAG_ENABLED required).",
        )
    return knowledge_indexer.backfill(db, limit=max(1, min(limit, 2000)))

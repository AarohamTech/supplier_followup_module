"""AI router — everything LLM-facing lives under /api/ai so it never mixes with
the procurement / mail / customer-mail endpoints.

  GET  /api/ai/health     → config status (no network call)
  POST /api/ai/chat       → Assistant chatbot turn
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from ..services import ai_service
from ..services.ai_service import AIDisabledError

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai", tags=["ai"])


class ChatMessage(BaseModel):
    role: str = "user"
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(default_factory=list)


class ChatResponse(BaseModel):
    reply: str
    model: str


@router.get("/health")
def ai_health() -> dict:
    return ai_service.health()


@router.post("/chat", response_model=ChatResponse)
def ai_chat(payload: ChatRequest) -> ChatResponse:
    if not payload.messages:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "messages cannot be empty")
    try:
        reply = ai_service.chat([m.model_dump() for m in payload.messages])
    except AIDisabledError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))
    except Exception as exc:  # noqa: BLE001 — surface upstream LLM errors cleanly
        log.exception("AI chat failed")
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"AI request failed: {exc}")
    from ..core.config import settings
    return ChatResponse(reply=reply, model=settings.LLM_MODEL)

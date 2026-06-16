"""Dedicated AI service — the single place that talks to the LLM.

Wraps an OpenAI-compatible endpoint (NVIDIA NIM by default). Everything LLM-
related lives here so the rest of the app depends on plain functions, not on the
LLM SDK. Safe by default: if `LLM_ENABLED` is false or misconfigured, callers get
a clear `AIDisabledError` (or a `None`/fallback) instead of a crash.

Used by:
  - routers/ai.py        → the Assistant chatbot
  - customer_mail_service → AI-polished reply drafts
"""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any, Iterable

from ..core.config import settings

log = logging.getLogger(__name__)

SYSTEM_ASSISTANT = (
    "You are the AI assistant inside a Supplier Follow-up procurement control "
    "tower. You help the procurement team with supplier follow-ups, purchase "
    "orders, delivery commitments, customer replies and general procurement "
    "questions. Be concise, professional and practical. If you are unsure or the "
    "data isn't provided, say so plainly rather than inventing details."
)

SYSTEM_CUSTOMER_REPLY = (
    "You draft short, professional, friendly replies to a customer's email on "
    "behalf of a procurement team. Use ONLY the order facts provided. Do not "
    "invent dates, quantities or statuses. Keep it to a few sentences, no "
    "placeholders, ready to send. Sign off as 'ProcureDirect Team'."
)


class AIDisabledError(RuntimeError):
    """Raised when an LLM call is attempted while AI is disabled/unconfigured."""


def is_enabled() -> bool:
    return bool(settings.LLM_ENABLED and settings.LLM_API_KEY)


@lru_cache(maxsize=1)
def _client():
    """Lazily build (and cache) the OpenAI-compatible client."""
    from openai import OpenAI  # imported lazily so the app boots without the SDK

    return OpenAI(
        base_url=settings.LLM_BASE_URL,
        api_key=settings.LLM_API_KEY,
        timeout=settings.LLM_TIMEOUT_SECONDS,
        max_retries=0,  # fail fast — callers fall back to a deterministic template
    )


def _complete(messages: list[dict[str, str]], *, temperature: float | None = None,
              max_tokens: int | None = None) -> str:
    if not is_enabled():
        raise AIDisabledError("AI is disabled (set LLM_ENABLED=true and LLM_API_KEY).")
    # `reasoning_effort` is a gpt-oss feature (low/medium/high) — low keeps it fast.
    extra: dict[str, Any] = {}
    if settings.LLM_REASONING_EFFORT:
        extra["reasoning_effort"] = settings.LLM_REASONING_EFFORT
    completion = _client().chat.completions.create(
        model=settings.LLM_MODEL,
        messages=messages,
        temperature=settings.LLM_TEMPERATURE if temperature is None else temperature,
        top_p=1,
        max_tokens=settings.LLM_MAX_TOKENS if max_tokens is None else max_tokens,
        stream=False,
        extra_body=extra or None,
    )
    # Some models (e.g. gpt-oss) return chain-of-thought in `reasoning_content`;
    # we only want the user-facing answer.
    return (completion.choices[0].message.content or "").strip()


def _normalize_messages(messages: Iterable[dict[str, Any]]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for m in messages:
        role = str(m.get("role") or "user").lower()
        if role not in {"system", "user", "assistant"}:
            role = "user"
        content = str(m.get("content") or "").strip()
        if content:
            out.append({"role": role, "content": content})
    return out


# ── Public API ───────────────────────────────────────────────────────────────
def chat(messages: Iterable[dict[str, Any]], *, system: str | None = None) -> str:
    """Run a chat turn for the Assistant. `messages` is a [{role, content}] list."""
    convo = _normalize_messages(messages)
    payload = [{"role": "system", "content": system or SYSTEM_ASSISTANT}, *convo]
    return _complete(payload)


def suggest_customer_reply(
    *,
    customer_name: str | None,
    subject: str | None,
    customer_message: str | None,
    supplier_po_no: str | None = None,
    material: str | None = None,
    status: str | None = None,
    dispatch_date: str | None = None,
) -> str:
    """Draft a customer reply body from the order facts (returns plain text)."""
    facts = [
        f"Customer name: {customer_name or 'there'}",
        f"Their subject: {subject or '(none)'}",
        f"Their message: {customer_message or '(none)'}",
        f"Order / PO: {supplier_po_no or 'unknown'}",
        f"Material: {material or 'unknown'}",
        f"Current status: {status or 'in progress'}",
        f"Committed dispatch date: {dispatch_date or 'not yet confirmed'}",
    ]
    user = (
        "Draft a reply to this customer using these facts:\n"
        + "\n".join(facts)
        + "\n\nReply with only the email body."
    )
    return _complete(
        [{"role": "system", "content": SYSTEM_CUSTOMER_REPLY}, {"role": "user", "content": user}],
        temperature=0.5,
    )


def health() -> dict[str, Any]:
    """Lightweight status (no network call) for the settings/health UI."""
    return {
        "enabled": is_enabled(),
        "model": settings.LLM_MODEL,
        "base_url": settings.LLM_BASE_URL,
        "has_key": bool(settings.LLM_API_KEY),
    }

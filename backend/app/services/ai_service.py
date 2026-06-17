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

import json
import logging
import re
from functools import lru_cache
from typing import Any, Callable, Iterable

from ..core.config import settings

log = logging.getLogger(__name__)

SYSTEM_ASSISTANT = (
    "You are the AI assistant inside a Supplier Follow-up procurement control "
    "tower. You help the procurement team with supplier follow-ups, purchase "
    "orders, delivery commitments, customer replies and general procurement "
    "questions. Be concise, professional and practical. If you are unsure or the "
    "data isn't provided, say so plainly rather than inventing details."
)

SYSTEM_AGENT = (
    SYSTEM_ASSISTANT
    + " You have tools that read the live procurement database (purchase orders, "
    "risk signals, supplier records, mail threads) and a semantic memory of past "
    "mails. Prefer calling a tool to look up real data over guessing. Call tools "
    "only when they help answer the question, then give a clear, well-structured "
    "answer grounded in the results. Use markdown (short bullets / tables) when it "
    "improves readability."
)

SYSTEM_TRIAGE = (
    "You are a procurement mail triage classifier. Read the customer email and "
    "return STRICT JSON only (no prose, no code fences) with exactly these keys: "
    '{"category": one of '
    "[GENERAL, CUSTOMER, SUPPLIER, COMPLAINT, DISPATCH, QUALITY, FINANCE], "
    '"urgency": one of [HIGH, MEDIUM, LOW], '
    '"action": one of [REPLY, ESCALATE, RESOLVE, MONITOR], '
    '"summary": a one-sentence summary (max 160 chars)}. '
    "Use HIGH urgency for complaints, quality issues, disputes, or anything "
    "time-critical; LOW for acknowledgements and FYIs."
)

SYSTEM_SUMMARY = (
    "You summarise procurement email threads for a busy manager. Produce a single "
    "tight paragraph (2-4 sentences) covering what the customer/supplier wants, "
    "the current status, and the open action. No preamble, no bullet points."
)

SYSTEM_PO_FOLLOWUP = (
    "You draft concise, firm-but-polite follow-up emails from a procurement team "
    "to a SUPPLIER chasing a delivery/dispatch update on a purchase order. Use "
    "ONLY the facts provided. Do not invent dates, quantities or statuses. Match "
    "the urgency to the risk signal (RED/BLACK = urgent, clear ask + deadline). "
    "Return ONLY the email body, no subject line, signed 'Procurement Team'."
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


# ── Agentic chat (tool calling) ──────────────────────────────────────────────
def chat_with_tools(
    messages: Iterable[dict[str, Any]],
    *,
    tools: list[dict[str, Any]],
    executor: Callable[[str, dict[str, Any]], Any],
    system: str | None = None,
    max_rounds: int | None = None,
) -> dict[str, Any]:
    """Run an agentic chat turn. The model may call `tools`; `executor(name, args)`
    runs each call and its JSON result is fed back until the model answers.

    Returns {"reply": str, "tools_used": [{"name","args"}...]}.
    """
    if not is_enabled():
        raise AIDisabledError("AI is disabled (set LLM_ENABLED=true and LLM_API_KEY).")
    rounds = max_rounds or int(settings.AI_AGENT_MAX_ROUNDS)
    convo: list[dict[str, Any]] = [
        {"role": "system", "content": system or SYSTEM_AGENT},
        *_normalize_messages(messages),
    ]
    used: list[dict[str, Any]] = []

    agent_timeout = settings.LLM_AGENT_TIMEOUT_SECONDS
    for _ in range(max(1, rounds)):
        completion = _client().chat.completions.create(
            model=settings.LLM_MODEL,
            messages=convo,
            tools=tools,
            tool_choice="auto",
            temperature=settings.LLM_TEMPERATURE,
            max_tokens=settings.LLM_MAX_TOKENS,
            stream=False,
            timeout=agent_timeout,  # longer than the fail-fast helper timeout
        )
        msg = completion.choices[0].message
        tool_calls = getattr(msg, "tool_calls", None) or []
        if not tool_calls:
            return {"reply": (msg.content or "").strip(), "tools_used": used}

        convo.append(
            {
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments or "{}",
                        },
                    }
                    for tc in tool_calls
                ],
            }
        )
        for tc in tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
                if not isinstance(args, dict):
                    args = {}
            except Exception:  # noqa: BLE001
                args = {}
            try:
                result = executor(name, args)
            except Exception as exc:  # noqa: BLE001
                log.exception("tool %s failed", name)
                result = {"error": str(exc)}
            used.append({"name": name, "args": args})
            convo.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result, default=str)[:6000],
                }
            )

    # Out of rounds — force a final answer without tools.
    convo.append(
        {
            "role": "system",
            "content": "Answer the user now using the tool results above. Do not call more tools.",
        }
    )
    final = _client().chat.completions.create(
        model=settings.LLM_MODEL,
        messages=convo,
        temperature=settings.LLM_TEMPERATURE,
        max_tokens=settings.LLM_MAX_TOKENS,
        stream=False,
        timeout=agent_timeout,
    )
    return {"reply": (final.choices[0].message.content or "").strip(), "tools_used": used}


# ── Structured helpers (triage / summary / PO follow-up) ─────────────────────
def _parse_json(raw: str) -> dict[str, Any]:
    """Best-effort JSON extraction from an LLM response."""
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:  # noqa: BLE001
        pass
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:  # noqa: BLE001
            return {}
    return {}


def complete_json(system: str, user: str, *, temperature: float = 0.2) -> dict[str, Any]:
    raw = _complete(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=temperature,
    )
    return _parse_json(raw)


_TRIAGE_CATEGORIES = {"GENERAL", "CUSTOMER", "SUPPLIER", "COMPLAINT", "DISPATCH", "QUALITY", "FINANCE"}
_TRIAGE_URGENCY = {"HIGH", "MEDIUM", "LOW"}
_TRIAGE_ACTION = {"REPLY", "ESCALATE", "RESOLVE", "MONITOR"}


def triage_customer_mail(
    *, subject: str | None, body: str | None, sender: str | None = None
) -> dict[str, Any]:
    """Classify a customer mail. Returns {category, urgency, action, summary}."""
    user = (
        f"From: {sender or 'unknown'}\n"
        f"Subject: {subject or '(none)'}\n\n"
        f"Body:\n{(body or '').strip()[:4000]}"
    )
    data = complete_json(SYSTEM_TRIAGE, user)
    category = str(data.get("category") or "GENERAL").upper().strip()
    urgency = str(data.get("urgency") or "MEDIUM").upper().strip()
    action = str(data.get("action") or "REPLY").upper().strip()
    summary = str(data.get("summary") or "").strip()[:200]
    return {
        "category": category if category in _TRIAGE_CATEGORIES else "GENERAL",
        "urgency": urgency if urgency in _TRIAGE_URGENCY else "MEDIUM",
        "action": action if action in _TRIAGE_ACTION else "REPLY",
        "summary": summary,
    }


def summarize_thread(transcript: str) -> str:
    """Summarise an email thread transcript into a short paragraph."""
    user = f"Summarise this thread:\n\n{transcript.strip()[:6000]}"
    return _complete(
        [{"role": "system", "content": SYSTEM_SUMMARY}, {"role": "user", "content": user}],
        temperature=0.3,
    )


def suggest_po_followup(
    *,
    supplier_name: str | None,
    supplier_po_no: str | None,
    overall_signal: str | None,
    days_late: int | None,
    followup_count: int | None,
    materials_summary: str | None,
    earliest_due_date: str | None = None,
    last_supplier_reply: str | None = None,
    precedent: str | None = None,
) -> str:
    """Draft an AI supplier follow-up body grounded in the PO facts."""
    facts = [
        f"Supplier: {supplier_name or 'Supplier'}",
        f"PO number: {supplier_po_no or 'unknown'}",
        f"Overall risk signal: {overall_signal or 'GREEN'}",
        f"Earliest required dispatch date: {earliest_due_date or 'not specified'}",
        f"Days past due (negative = not yet due): {days_late if days_late is not None else 'unknown'}",
        f"Follow-ups already sent: {followup_count if followup_count is not None else 0}",
        f"Materials:\n{materials_summary or '(see PO)'}",
    ]
    if last_supplier_reply:
        facts.append(f"Last supplier reply: {last_supplier_reply[:500]}")
    if precedent:
        facts.append(f"How this supplier responded to past follow-ups:\n{precedent[:800]}")
    user = (
        "Draft a follow-up email body to the supplier using these facts:\n"
        + "\n".join(facts)
        + "\n\nReturn only the email body."
    )
    return _complete(
        [{"role": "system", "content": SYSTEM_PO_FOLLOWUP}, {"role": "user", "content": user}],
        temperature=0.4,
    )


def health() -> dict[str, Any]:
    """Lightweight status (no network call) for the settings/health UI."""
    from . import embeddings_service  # local import avoids a cycle at module load

    return {
        "enabled": is_enabled(),
        "model": settings.LLM_MODEL,
        "base_url": settings.LLM_BASE_URL,
        "has_key": bool(settings.LLM_API_KEY),
        "agent_enabled": bool(settings.AI_AGENT_ENABLED and is_enabled()),
        "triage_enabled": bool(settings.AI_TRIAGE_ENABLED),
        "po_followup_ai": bool(settings.AI_PO_FOLLOWUP_ENABLED),
        "rag": embeddings_service.health(),
    }

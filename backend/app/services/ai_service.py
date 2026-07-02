"""Dedicated AI service — the single place that talks to the LLM.

Two providers:
  - Primary: an OpenAI-compatible endpoint (NVIDIA NIM by default, LLM_* keys).
  - Secondary: real OpenAI gpt-5-nano (OPENAI_* keys) — the PRIMARY model for
    the HI thread-chat / draft formation (`prefer_openai=True`), and the
    automatic BACKUP for everything else (digest cron, triage, summaries) when
    the primary endpoint fails. Cost controls: background/cron calls run on the
    ~50%-cheaper flex service tier, and each task carries a `prompt_cache_key`
    so OpenAI's automatic prompt caching (90% off cached input tokens) hits.

Everything LLM-related lives here so the rest of the app depends on plain
functions, not on the LLM SDK. Safe by default: if no provider is configured,
callers get a clear `AIDisabledError` (or a `None`/fallback) instead of a crash.

Used by:
  - routers/ai.py        → the Assistant chatbot
  - customer_mail_service → AI-polished reply drafts
  - hi_agent_service      → the /hi thread chat (gpt-5-nano first)
"""
from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from typing import Any, Callable, Iterable

from ..core.config import settings
from ..database import SessionLocal
from ..models.app_setting import AppSetting

log = logging.getLogger(__name__)

SYSTEM_ASSISTANT = (
    "You are the AI assistant inside a Supplier Follow-up procurement control "
    "tower. You help the procurement team with supplier follow-ups, purchase "
    "orders, delivery commitments, customer replies and general procurement "
    "questions. Be concise, professional and practical. If you are unsure or the "
    "data isn't provided, say so plainly rather than inventing details."
)

# Appended (not user-editable) to the assistant prompt for the agentic chat so
# tool-calling behaviour stays correct even if the editable persona changes.
AGENT_TOOLS_SUFFIX = (
    " You have tools that read the live procurement database (purchase orders, "
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
    "You draft concise, firm and professional follow-up emails from a procurement "
    "team to a SUPPLIER chasing a delivery/dispatch update on a purchase order. Use "
    "ONLY the facts provided. Do not invent dates, quantities or statuses. Match the "
    "urgency to the risk signal (RED/BLACK = urgent, with a clear ask and a deadline) "
    "while staying courteous and relationship-preserving. Become firmer ONLY if the "
    "procurement officer's instruction explicitly asks for it. Direct the supplier to "
    "submit or update their committed dispatch date for each material in the secure "
    "supplier portal — the portal link is added automatically below your message. Do "
    "NOT ask them to reply to this email, send a return email, or fill in a table; the "
    "supplier portal is the only channel they should use to respond. Return ONLY the "
    "email body, no subject line, signed 'Procurement Team'."
)

SYSTEM_CUSTOMER_REPLY = (
    "You draft short, professional, friendly replies to a customer's email on "
    "behalf of a procurement team. Use ONLY the order facts provided. Do not "
    "invent dates, quantities or statuses. Keep it to a few sentences, no "
    "placeholders, ready to send. Sign off as 'ProcureDirect Team'."
)


# ── Editable system prompts (DB-backed overrides, code defaults) ─────────────
# Stored as one app_settings row {key: "ai_prompts", value: {prompt_key: text}}.
# Edited live from the UI so the team can tune AI tone/behaviour without a deploy.
PROMPT_DEFAULTS: dict[str, str] = {
    "assistant": SYSTEM_ASSISTANT,
    "po_followup": SYSTEM_PO_FOLLOWUP,
    "customer_reply": SYSTEM_CUSTOMER_REPLY,
    "triage": SYSTEM_TRIAGE,
    "summary": SYSTEM_SUMMARY,
}
PROMPT_LABELS: dict[str, str] = {
    "assistant": "AI Assistant (chatbot persona)",
    "po_followup": "Supplier follow-up emails (incl. Black follow-ups)",
    "customer_reply": "Customer reply drafts (AI Generate)",
    "triage": "Incoming mail triage classifier",
    "summary": "Thread summariser",
}
_PROMPTS_KEY = "ai_prompts"
_prompt_cache: dict[str, str] | None = None


def _load_prompt_overrides() -> dict[str, str]:
    resolved = dict(PROMPT_DEFAULTS)
    try:
        db = SessionLocal()
        try:
            row = db.get(AppSetting, _PROMPTS_KEY)
            overrides = row.value if row and isinstance(row.value, dict) else {}
        finally:
            db.close()
        for key in PROMPT_DEFAULTS:
            val = overrides.get(key)
            if isinstance(val, str) and val.strip():
                resolved[key] = val.strip()
    except Exception:  # noqa: BLE001
        log.exception("Loading prompt overrides failed; using code defaults")
    return resolved


def _prompt(key: str) -> str:
    global _prompt_cache
    if _prompt_cache is None:
        _prompt_cache = _load_prompt_overrides()
    return _prompt_cache.get(key) or PROMPT_DEFAULTS.get(key, "")


def reload_prompts() -> None:
    """Invalidate the in-memory prompt cache (call after an override is saved)."""
    global _prompt_cache
    _prompt_cache = None


def list_prompts(db) -> dict[str, Any]:
    """Return each editable prompt with its current value, default and custom flag."""
    row = db.get(AppSetting, _PROMPTS_KEY)
    overrides = row.value if row and isinstance(row.value, dict) else {}
    out: dict[str, Any] = {}
    for key, default in PROMPT_DEFAULTS.items():
        ov = overrides.get(key)
        if isinstance(ov, str) and ov.strip():
            value, is_custom = ov.strip(), True
        else:
            value, is_custom = default, False
        out[key] = {
            "label": PROMPT_LABELS.get(key, key),
            "value": value,
            "default": default,
            "is_custom": is_custom,
        }
    return out


def set_prompts(db, values: dict[str, str | None]) -> dict[str, Any]:
    """Upsert prompt overrides. A blank/None value resets that prompt to default."""
    row = db.get(AppSetting, _PROMPTS_KEY)
    overrides = dict(row.value) if row and isinstance(row.value, dict) else {}
    for key, val in (values or {}).items():
        if key not in PROMPT_DEFAULTS:
            continue
        if val is None or (isinstance(val, str) and not val.strip()):
            overrides.pop(key, None)  # reset to default
        else:
            overrides[key] = str(val).strip()
    if row is None:
        db.add(AppSetting(key=_PROMPTS_KEY, value=overrides))
    else:
        row.value = overrides
    db.commit()
    reload_prompts()
    return list_prompts(db)


class AIDisabledError(RuntimeError):
    """Raised when an LLM call is attempted while AI is disabled/unconfigured."""


def is_enabled() -> bool:
    """The primary (NVIDIA NIM / OpenAI-compatible) endpoint is configured."""
    return bool(settings.LLM_ENABLED and settings.LLM_API_KEY)


def openai_enabled() -> bool:
    """The secondary OpenAI (gpt-5-nano) provider is configured."""
    return bool(settings.OPENAI_ENABLED and settings.OPENAI_API_KEY)


def any_enabled() -> bool:
    """At least one LLM provider is usable."""
    return is_enabled() or openai_enabled()


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


@lru_cache(maxsize=1)
def _openai_client():
    """Lazily build (and cache) the real-OpenAI client (gpt-5-nano)."""
    from openai import OpenAI

    return OpenAI(
        base_url=settings.OPENAI_BASE_URL,
        api_key=settings.OPENAI_API_KEY,
        timeout=settings.OPENAI_TIMEOUT_SECONDS,
        max_retries=0,
    )


def _provider_order(prefer_openai: bool) -> list[str]:
    """Enabled providers in attempt order. HI chat prefers OpenAI (gpt-5-nano);
    everything else runs the primary endpoint with OpenAI as the backup."""
    order: list[str] = []
    if prefer_openai and openai_enabled():
        order.append("openai")
    if is_enabled():
        order.append("primary")
    if not prefer_openai and openai_enabled():
        order.append("openai")
    return order


def _openai_extra(*, background: bool, cache_key: str | None,
                  max_tokens: int | None = None) -> dict[str, Any]:
    """gpt-5-family request params, sent via extra_body so any openai-sdk
    version passes them through untouched."""
    extra: dict[str, Any] = {
        # gpt-5 rejects `max_tokens`; reasoning tokens also bill against the
        # completion budget, so never go below the configured headroom.
        "max_completion_tokens": max(int(max_tokens or 0), settings.OPENAI_MAX_COMPLETION_TOKENS),
    }
    if settings.OPENAI_REASONING_EFFORT:
        extra["reasoning_effort"] = settings.OPENAI_REASONING_EFFORT
    if cache_key:
        # Routes same-prefix requests to the same cache shard so OpenAI's
        # automatic prompt caching (90% off cached input) hits reliably.
        extra["prompt_cache_key"] = f"sfm-{cache_key}"
    if background and settings.OPENAI_FLEX_FOR_BACKGROUND:
        extra["service_tier"] = "flex"  # ~50% cheaper; fine for cron jobs
    return extra


def _openai_complete(messages: list[dict[str, str]], *, background: bool = False,
                     cache_key: str | None = None, max_tokens: int | None = None) -> str:
    """One completion on gpt-5-nano. No temperature/top_p — gpt-5 only accepts
    the defaults. Flex-tier calls that fail (capacity shed) retry once standard."""
    extra = _openai_extra(background=background, cache_key=cache_key, max_tokens=max_tokens)
    flex = extra.get("service_tier") == "flex"
    try:
        completion = _openai_client().chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=messages,
            stream=False,
            timeout=settings.OPENAI_FLEX_TIMEOUT_SECONDS if flex else settings.OPENAI_TIMEOUT_SECONDS,
            extra_body=extra,
        )
    except Exception:  # noqa: BLE001
        if not flex:
            raise
        log.warning("OpenAI flex-tier call failed; retrying at standard tier", exc_info=True)
        retry_extra = {k: v for k, v in extra.items() if k != "service_tier"}
        completion = _openai_client().chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=messages,
            stream=False,
            timeout=settings.OPENAI_TIMEOUT_SECONDS,
            extra_body=retry_extra,
        )
    return (completion.choices[0].message.content or "").strip()


def _primary_complete(messages: list[dict[str, str]], *, temperature: float | None = None,
                      max_tokens: int | None = None) -> str:
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


def _complete(messages: list[dict[str, str]], *, temperature: float | None = None,
              max_tokens: int | None = None, background: bool = False,
              cache_key: str | None = None, prefer_openai: bool = False) -> str:
    """Run one completion across the configured providers, in order, falling
    back to the next provider on any error. `background` marks cron/worker
    traffic (flex tier on OpenAI); `prefer_openai` puts gpt-5-nano first."""
    providers = _provider_order(prefer_openai)
    if not providers:
        raise AIDisabledError("AI is disabled (set LLM_ENABLED or OPENAI_ENABLED plus an API key).")
    last_exc: Exception | None = None
    for i, provider in enumerate(providers):
        try:
            if provider == "openai":
                return _openai_complete(messages, background=background,
                                        cache_key=cache_key, max_tokens=max_tokens)
            return _primary_complete(messages, temperature=temperature, max_tokens=max_tokens)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if i + 1 < len(providers):
                log.warning("LLM provider '%s' failed; falling back to '%s'",
                            provider, providers[i + 1], exc_info=True)
    assert last_exc is not None
    raise last_exc


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
    payload = [{"role": "system", "content": system or _prompt("assistant")}, *convo]
    return _complete(payload, cache_key="assistant")


def suggest_customer_reply(
    *,
    customer_name: str | None,
    subject: str | None,
    customer_message: str | None,
    supplier_po_no: str | None = None,
    material: str | None = None,
    status: str | None = None,
    dispatch_date: str | None = None,
    instruction: str | None = None,
    prefer_openai: bool = False,
) -> str:
    """Draft a customer reply body from the order facts (returns plain text).

    `instruction` is free-text guidance the agent typed in the composer (e.g.
    "tell them it ships Friday and apologise for the delay") — the model must
    follow it while staying grounded in the order facts.
    """
    facts = [
        f"Customer name: {customer_name or 'there'}",
        f"Their subject: {subject or '(none)'}",
        f"Their message: {customer_message or '(none)'}",
        f"Order / PO: {supplier_po_no or 'unknown'}",
        f"Material: {material or 'unknown'}",
        f"Current status: {status or 'in progress'}",
        f"Committed dispatch date: {dispatch_date or 'not yet confirmed'}",
    ]
    user = "Draft a reply to this customer using these facts:\n" + "\n".join(facts)
    if instruction and instruction.strip():
        user += (
            "\n\nThe support agent wrote these notes/instructions for the reply — "
            "follow them closely and expand into a complete, professional message:\n"
            + instruction.strip()
        )
    user += "\n\nReply with only the email body."
    return _complete(
        [{"role": "system", "content": _prompt("customer_reply")}, {"role": "user", "content": user}],
        temperature=0.5,
        cache_key="customer-reply",
        prefer_openai=prefer_openai,
    )


# ── Agentic chat (tool calling) ──────────────────────────────────────────────
def _agent_completion(convo: list[dict[str, Any]], provider: str,
                      tools: list[dict[str, Any]] | None, cache_key: str | None):
    """One agent-loop completion on the given provider."""
    agent_timeout = settings.LLM_AGENT_TIMEOUT_SECONDS
    if provider == "openai":
        extra = _openai_extra(background=False, cache_key=cache_key)
        if tools is not None:
            return _openai_client().chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=convo,
                tools=tools,
                tool_choice="auto",
                stream=False,
                timeout=agent_timeout,
                extra_body=extra,
            )
        return _openai_client().chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=convo,
            stream=False,
            timeout=agent_timeout,
            extra_body=extra,
        )
    if tools is not None:
        return _client().chat.completions.create(
            model=settings.LLM_MODEL,
            messages=convo,
            tools=tools,
            tool_choice="auto",
            temperature=settings.LLM_TEMPERATURE,
            max_tokens=settings.LLM_MAX_TOKENS,
            stream=False,
            timeout=agent_timeout,  # longer than the fail-fast helper timeout
        )
    return _client().chat.completions.create(
        model=settings.LLM_MODEL,
        messages=convo,
        temperature=settings.LLM_TEMPERATURE,
        max_tokens=settings.LLM_MAX_TOKENS,
        stream=False,
        timeout=agent_timeout,
    )


def chat_with_tools(
    messages: Iterable[dict[str, Any]],
    *,
    tools: list[dict[str, Any]],
    executor: Callable[[str, dict[str, Any]], Any],
    system: str | None = None,
    max_rounds: int | None = None,
    prefer_openai: bool = False,
    cache_key: str = "agent",
) -> dict[str, Any]:
    """Run an agentic chat turn. The model may call `tools`; `executor(name, args)`
    runs each call and its JSON result is fed back until the model answers.

    `prefer_openai=True` runs the turn on gpt-5-nano first (HI chat / drafting),
    with the primary endpoint as fallback; otherwise the order is reversed. If a
    provider dies mid-conversation we switch to the next one and keep the convo
    (tool results already executed are never re-run).

    Returns {"reply": str, "tools_used": [{"name","args"}...]}.
    """
    providers = _provider_order(prefer_openai)
    if not providers:
        raise AIDisabledError("AI is disabled (set LLM_ENABLED or OPENAI_ENABLED plus an API key).")
    rounds = max_rounds or int(settings.AI_AGENT_MAX_ROUNDS)
    convo: list[dict[str, Any]] = [
        {"role": "system", "content": system or (_prompt("assistant") + AGENT_TOOLS_SUFFIX)},
        *_normalize_messages(messages),
    ]
    used: list[dict[str, Any]] = []

    def call(tools_arg: list[dict[str, Any]] | None):
        while True:
            try:
                return _agent_completion(convo, providers[0], tools_arg, cache_key)
            except Exception:  # noqa: BLE001
                failed = providers.pop(0)
                if not providers:
                    raise
                log.warning("agent provider '%s' failed; switching to '%s'",
                            failed, providers[0], exc_info=True)

    for _ in range(max(1, rounds)):
        completion = call(tools)
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
    final = call(None)
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


def complete_json(system: str, user: str, *, temperature: float = 0.2,
                  background: bool = False, cache_key: str | None = None,
                  prefer_openai: bool = False) -> dict[str, Any]:
    raw = _complete(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=temperature,
        background=background,
        cache_key=cache_key,
        prefer_openai=prefer_openai,
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
    # Triage always runs from the mail-fetch worker — background traffic.
    data = complete_json(_prompt("triage"), user, background=True, cache_key="triage")
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


def summarize_thread(transcript: str, *, background: bool = False,
                     prefer_openai: bool = False) -> str:
    """Summarise an email thread transcript into a short paragraph."""
    user = f"Summarise this thread:\n\n{transcript.strip()[:6000]}"
    return _complete(
        [{"role": "system", "content": _prompt("summary")}, {"role": "user", "content": user}],
        temperature=0.3,
        background=background,
        cache_key="summary",
        prefer_openai=prefer_openai,
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
    instruction: str | None = None,
    background: bool = False,
) -> str:
    """Draft an AI supplier follow-up body grounded in the PO facts.

    `instruction` is a free-text command the user typed (e.g. "also ask for a
    firm dispatch date by Friday and mention the penalty clause") — follow it
    while staying grounded in the facts.
    """
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
    user = "Draft a follow-up email to the supplier using these facts:\n" + "\n".join(facts)
    if instruction and instruction.strip():
        user += (
            "\n\nThe procurement officer gave this specific instruction for THIS "
            "follow-up — follow it closely:\n" + instruction.strip()
        )
    # Structured output: we only want the PROSE body. The material table and
    # reply table are built from real PO data and rendered to HTML by the backend
    # — so the model must NOT include any table, material list or markdown.
    user += (
        '\n\nReturn STRICT JSON only: {"draft": "<the email message as plain prose: '
        "greeting, the ask, the urgency/deadline, and sign-off>\"}. In the ask, direct "
        "the supplier to submit or update their committed dispatch date for each material "
        "in the secure supplier portal (the portal link is appended automatically below "
        "your message). Do NOT ask them to reply by email or to fill in a table. Do NOT "
        "include any table, material-wise list, PO summary block, markdown or code "
        "fences — the material table and portal link are appended automatically by the "
        "system."
    )
    base_prompt = _prompt("po_followup")
    system = base_prompt + ' Output ONLY a strict JSON object {"draft": "..."} and nothing else.'
    data = complete_json(system, user, temperature=0.4, background=background,
                         cache_key="po-followup")
    draft = str(data.get("draft") or "").strip()
    if not draft:
        # Fallback: plain completion if JSON parsing failed.
        draft = _complete(
            [
                {"role": "system", "content": base_prompt},
                {"role": "user", "content": user + "\n\n(If JSON is hard, just return the prose body.)"},
            ],
            temperature=0.4,
            background=background,
            cache_key="po-followup",
        )
    return _strip_md_tables(draft)


def _strip_md_tables(text: str) -> str:
    """Remove any leaked markdown table rows/separators from an LLM draft, so the
    backend's own HTML table is the only one in the email."""
    out: list[str] = []
    for ln in (text or "").splitlines():
        s = ln.strip()
        if s.startswith("|") and s.endswith("|") and s.count("|") >= 2:
            continue  # table row
        if s and set(s) <= {"-", "|", " ", ":"}:
            continue  # separator row like |---|---|
        out.append(ln)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()


def health() -> dict[str, Any]:
    """Lightweight status (no network call) for the settings/health UI."""
    from . import embeddings_service  # local import avoids a cycle at module load

    return {
        "enabled": is_enabled(),
        "model": settings.LLM_MODEL,
        "base_url": settings.LLM_BASE_URL,
        "has_key": bool(settings.LLM_API_KEY),
        "agent_enabled": bool(settings.AI_AGENT_ENABLED and any_enabled()),
        "triage_enabled": bool(settings.AI_TRIAGE_ENABLED),
        "po_followup_ai": bool(settings.AI_PO_FOLLOWUP_ENABLED),
        "openai": {
            "enabled": openai_enabled(),
            "model": settings.OPENAI_MODEL,
            "has_key": bool(settings.OPENAI_API_KEY),
            "role": "hi-chat primary + cron/backend backup",
            "flex_for_background": bool(settings.OPENAI_FLEX_FOR_BACKGROUND),
        },
        "rag": embeddings_service.health(),
    }

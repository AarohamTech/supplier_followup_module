"""HI-agent orchestrator. Turns a /hi message into a reply + pending actions.

LLM-driven when available (tool-calling via ai_service.chat_with_tools), with a
deterministic fallback so the feature works — and tests run — with AI disabled.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from . import ai_service
from . import hi_agent_tools as tools

log = logging.getLogger(__name__)

HI_SYSTEM_PROMPT = (
    "You are HI, an assistant embedded in a procurement Communication Hub thread "
    "for one purchase order. You can ONLY: summarise the thread, list open action "
    "items, explain the PO's risk signal, look up @mentioned people, prepare a "
    "one-time email DRAFT, draft a reply, set up a standing followup that forwards "
    "new messages to an internal teammate, set up a recurring summary for an "
    "internal teammate, and list existing subscriptions. "
    "You NEVER send mail yourself: drafts and subscriptions you create must be "
    "confirmed by the user via the UI before anything is sent. Subscriptions "
    "(followups and scheduled summaries) can only target internal teammates, not "
    "suppliers; one-time emails may target either. "
    "If the user asks for something outside this list (editing/deleting data, "
    "anything unrelated), say clearly: \"I can't do that, but I can summarise this "
    "thread, draft or send an email, set up a followup, or schedule a summary — "
    "want one of those?\" Keep replies short and concrete. After preparing a draft "
    "or subscription, tell the user it is ready and awaiting their confirmation."
)


def run(
    db: Session,
    *,
    user: Any,
    message: str,
    supplier_id: int | None,
    procurement_record_id: int | None,
    supplier_po_no: str | None,
) -> dict[str, Any]:
    ctx = tools.ToolContext(
        db=db, user=user, supplier_id=supplier_id,
        procurement_record_id=procurement_record_id, supplier_po_no=supplier_po_no,
    )
    text = (message or "").strip()

    if not ai_service.is_enabled():
        reply = _fallback(ctx, text)
        return {"reply": reply, "pending_actions": ctx.pending_actions, "tools_used": []}

    try:
        result = ai_service.chat_with_tools(
            [{"role": "user", "content": text}],
            tools=tools.TOOLS,
            executor=tools.make_executor(ctx),
            system=HI_SYSTEM_PROMPT,
        )
        return {
            "reply": result.get("reply") or "",
            "pending_actions": ctx.pending_actions,
            "tools_used": result.get("tools_used", []),
        }
    except Exception:  # noqa: BLE001
        log.exception("HI agent LLM path failed; using fallback")
        reply = _fallback(ctx, text)
        return {"reply": reply, "pending_actions": ctx.pending_actions, "tools_used": []}


_HELP = (
    "I can summarise this thread, list open action items, explain the PO's signal, "
    "send a one-time email to an @teammate or supplier, set up a followup, or "
    "schedule a recurring summary. What would you like?"
)


def _fallback(ctx: tools.ToolContext, text: str) -> str:
    """Deterministic intent handling when the LLM is unavailable.

    Only covers read-only summarisation reliably; anything needing a recipient or
    the model is deferred to a help message (we never silently send)."""
    low = text.lower()
    if any(k in low for k in ("summar", "recap", "tl;dr", "what's happening", "whats happening")):
        return tools.tool_summarize(ctx, {}).get("summary") or _HELP
    if any(k in low for k in ("action item", "pending", "open question", "to do", "todo")):
        out = tools.tool_action_items(ctx, {})
        if out.get("items"):
            return "Open items:\n- " + "\n- ".join(out["items"])
        return out.get("note") or _HELP
    if "signal" in low or "why is this" in low or "red" in low or "black" in low:
        return tools.tool_explain_signal(ctx, {}).get("explanation") or _HELP
    if "subscription" in low or "following" in low or "who's" in low or "whos" in low:
        rows = tools.tool_list_subscriptions(ctx, {})["subscriptions"]
        if not rows:
            return "No followups or scheduled summaries are set on this thread yet."
        return "Active here:\n" + "\n".join(
            f"- {r['kind']} → {r['recipient']} ({r['status']})" for r in rows
        )
    return "AI is currently disabled, so I can summarise or list items here. " + _HELP

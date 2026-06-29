"""HI-agent tools: read / create-draft / create-pending-subscription only.

No function here sends email or edits/deletes existing rows. Draft and
subscription tools append a descriptor to `ToolContext.pending_actions` so the
orchestrator can surface confirm cards to the user.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from sqlalchemy import func as _sa_func, select
from sqlalchemy.orm import Session

from ..models.communication_message import CommunicationMessage
from ..models.customer_mail import CustomerMail
from ..models.mail_history import MailHistory
from ..models.procurement import ProcurementRecord
from ..models.supplier_email import SupplierEmail
from . import agent_subscription_service as subs
from . import ai_service
from . import communication_message_service as msg_service
from . import user_service

log = logging.getLogger(__name__)


@dataclass
class ToolContext:
    db: Session
    user: Any
    supplier_id: int | None
    procurement_record_id: int | None
    supplier_po_no: str | None
    pending_actions: list[dict[str, Any]] = field(default_factory=list)


# ── Thread context ───────────────────────────────────────────────────────────
def gather_thread(
    db: Session, procurement_record_id: int | None, supplier_po_no: str | None
) -> list[dict[str, Any]]:
    """Merge MailHistory (legacy) + CommunicationMessage (new) for one PO thread."""
    rows: list[dict[str, Any]] = []

    mh = select(MailHistory)
    if procurement_record_id is not None and supplier_po_no:
        mh = mh.where(
            (MailHistory.procurement_record_id == procurement_record_id)
            | (MailHistory.supplier_po_no == supplier_po_no)
        )
    elif procurement_record_id is not None:
        mh = mh.where(MailHistory.procurement_record_id == procurement_record_id)
    elif supplier_po_no:
        mh = mh.where(MailHistory.supplier_po_no == supplier_po_no)
    else:
        mh = None
    if mh is not None:
        for m in db.scalars(mh).all():
            rows.append({
                "direction": "OUTGOING",
                "subject": m.subject,
                "body": m.body or "",
                "created_at": m.created_at,
                "who": "Procurement",
            })

    cm = select(CommunicationMessage)
    if procurement_record_id is not None and supplier_po_no:
        cm = cm.where(
            (CommunicationMessage.procurement_record_id == procurement_record_id)
            | (CommunicationMessage.supplier_po_no == supplier_po_no)
        )
    elif procurement_record_id is not None:
        cm = cm.where(CommunicationMessage.procurement_record_id == procurement_record_id)
    elif supplier_po_no:
        cm = cm.where(CommunicationMessage.supplier_po_no == supplier_po_no)
    else:
        cm = None
    if cm is not None:
        for m in db.scalars(cm).all():
            rows.append({
                "direction": m.direction,
                "subject": m.subject,
                "body": m.body or "",
                "created_at": m.created_at,
                "who": "Supplier" if m.direction == "INCOMING" else "Procurement",
            })

    rows.sort(key=lambda r: r["created_at"] or "")
    return rows


def build_transcript(rows: list[dict[str, Any]]) -> str:
    lines = []
    for r in rows:
        subj = (r.get("subject") or "").strip()
        body = (r.get("body") or "").strip()
        lines.append(f"[{r['who']}] {subj}\n{body}".strip())
    return "\n\n".join(lines)


def _po_record(ctx: "ToolContext") -> ProcurementRecord | None:
    if ctx.procurement_record_id is not None:
        rec = ctx.db.get(ProcurementRecord, ctx.procurement_record_id)
        if rec:
            return rec
    if ctx.supplier_po_no:
        return ctx.db.scalar(
            select(ProcurementRecord).where(
                ProcurementRecord.supplier_po_no == ctx.supplier_po_no
            )
        )
    return None


# ── Read-only tools ──────────────────────────────────────────────────────────
def tool_read_thread(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    rows = gather_thread(ctx.db, ctx.procurement_record_id, ctx.supplier_po_no)
    return {
        "message_count": len(rows),
        "supplier_po_no": ctx.supplier_po_no,
        "transcript": build_transcript(rows)[:6000],
    }


def tool_summarize(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    rows = gather_thread(ctx.db, ctx.procurement_record_id, ctx.supplier_po_no)
    transcript = build_transcript(rows)
    if not transcript:
        return {"summary": "There are no messages in this thread yet."}
    if ai_service.is_enabled():
        try:
            return {"summary": ai_service.summarize_thread(transcript)}
        except Exception:  # noqa: BLE001
            log.exception("summarize_thread failed; using fallback")
    # Deterministic fallback: last inbound + counts.
    incoming = [r for r in rows if r["direction"] == "INCOMING"]
    last = incoming[-1]["body"] if incoming else rows[-1]["body"]
    return {
        "summary": (
            f"{len(rows)} message(s) on PO {ctx.supplier_po_no}. "
            f"Most recent update: {last.strip()[:240]}"
        )
    }


def tool_action_items(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    rows = gather_thread(ctx.db, ctx.procurement_record_id, ctx.supplier_po_no)
    transcript = build_transcript(rows)
    if not transcript:
        return {"items": [], "note": "No messages to analyse."}
    if ai_service.is_enabled():
        try:
            data = ai_service.complete_json(
                "Extract open action items and unanswered questions from this "
                'procurement thread. Return STRICT JSON {"items": ["...", "..."]}.',
                transcript[:6000],
            )
            items = data.get("items")
            if isinstance(items, list):
                return {"items": [str(i)[:200] for i in items][:10]}
        except Exception:  # noqa: BLE001
            log.exception("action item extraction failed; using fallback")
    # Fallback: flag unanswered if the last message is from the supplier.
    note = "Latest message is from the supplier — a reply may be pending." if (
        rows and rows[-1]["direction"] == "INCOMING"
    ) else "No obvious open items detected."
    return {"items": [], "note": note}


def tool_explain_signal(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    rec = _po_record(ctx)
    if rec is None:
        return {"explanation": "No purchase-order record is linked to this thread."}
    signal = (rec.signal or "GREEN").upper()
    parts = [f"PO {rec.supplier_po_no} for {rec.supplier_name} is {signal}."]
    if getattr(rec, "shipment_date", None):
        parts.append(f"Shipment date: {rec.shipment_date}.")
    if getattr(rec, "last_supplier_reply", None):
        parts.append(f"Last supplier reply: {str(rec.last_supplier_reply)[:200]}")
    return {"explanation": " ".join(parts)}


# ── Recipient resolution + draft tools (no send) ─────────────────────────────
def _clean_mention(mention: str | None) -> str:
    return (mention or "").strip().lstrip("@").strip()


def resolve_recipient(db: Session, mention: str | None, *, allow_supplier: bool) -> dict[str, Any]:
    """Resolve an @handle to an internal user (always) or a supplier (one-time only)."""
    handle = _clean_mention(mention)
    if not handle:
        return {"found": False, "reason": "No recipient given.", "kind": None,
                "email": None, "label": None, "user_id": None, "supplier_id": None}

    # 1) Internal user by username, then by name/email search.
    user = user_service.get_by_username(db, handle)
    if user is None:
        matches = user_service.list_users(db, search=handle)
        internal = [u for u in matches if u.supplier_id is None]
        user = internal[0] if len(internal) == 1 else None
    if user is not None and user.email:
        return {"found": True, "kind": "user", "email": user.email,
                "label": user.full_name or user.username or user.email,
                "user_id": user.id, "supplier_id": None, "reason": None}

    # 2) Supplier (one-time sends only).
    if allow_supplier:
        row = db.scalar(
            select(SupplierEmail).where(
                _sa_func.lower(SupplierEmail.supplier_name) == handle.lower(),
                SupplierEmail.is_active.is_(True),
            )
        )
        if row and row.to_emails:
            return {"found": True, "kind": "supplier", "email": row.to_emails[0],
                    "label": row.supplier_name, "user_id": None,
                    "supplier_id": row.supplier_id, "reason": None}

    # 3) Customer (one-time sends only) — match a recent customer email by exact
    #    address or name; resolve only when it points to a single email.
    if allow_supplier:
        handle_l = handle.lower()
        crows = db.execute(
            select(CustomerMail.from_email, CustomerMail.customer_name, CustomerMail.from_name)
            .where(CustomerMail.from_email.isnot(None))
            .order_by(CustomerMail.received_at.desc().nullslast())
        ).all()
        candidates: dict[str, tuple[str, str]] = {}
        for from_email, customer_name, from_name in crows:
            email = (from_email or "").strip()
            if not email:
                continue
            el = email.lower()
            name_blob = f"{customer_name or ''} {from_name or ''}".lower()
            if el == handle_l or handle_l in el or handle_l in name_blob:
                label = (customer_name or from_name or email).strip()
                candidates.setdefault(el, (email, label))
        if len(candidates) == 1:
            email, label = next(iter(candidates.values()))
            return {"found": True, "kind": "customer", "email": email,
                    "label": label, "user_id": None, "supplier_id": None, "reason": None}
        if len(candidates) > 1:
            return {"found": False, "kind": None, "email": None, "label": None,
                    "user_id": None, "supplier_id": None,
                    "reason": f"Multiple customers match '{handle}' — be more specific."}

    reason = (
        f"No internal user matches '{handle}'."
        if not allow_supplier
        else f"No user, supplier, or customer matches '{handle}'."
    )
    return {"found": False, "kind": None, "email": None, "label": None,
            "user_id": None, "supplier_id": None, "reason": reason}


def tool_resolve_recipient(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    return resolve_recipient(ctx.db, args.get("mention"), allow_supplier=True)


def tool_draft_email(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Create a DRAFT one-time email to @mention. One-time sends may target suppliers."""
    rec = resolve_recipient(ctx.db, args.get("mention"), allow_supplier=True)
    if not rec["found"]:
        return {"drafted": False, "error": rec["reason"]}
    subject = (args.get("subject") or f"Update on PO {ctx.supplier_po_no}").strip()
    body = (args.get("body") or "").strip()
    if not body:
        return {"drafted": False, "error": "Email body is empty."}
    msg = msg_service.create_message(
        ctx.db,
        direction="OUTGOING",
        status="DRAFT",  # never READY — confirm endpoint promotes it
        supplier_id=ctx.supplier_id if rec["kind"] == "supplier" else None,
        supplier_name=rec["label"] if rec["kind"] == "supplier" else None,
        procurement_record_id=ctx.procurement_record_id,
        supplier_po_no=ctx.supplier_po_no,
        subject=subject,
        body=body,
        receiver_email=rec["email"],
        to_emails=[rec["email"]],
        mail_type="HI_AGENT_SEND",
        commit=True,
    )
    descriptor = {
        "type": "draft", "message_id": msg.id, "recipient": rec["label"],
        "recipient_email": rec["email"], "recipient_kind": rec["kind"], "subject": subject,
    }
    ctx.pending_actions.append(descriptor)
    return {"drafted": True, "message_id": msg.id, "recipient": rec["label"],
            "subject": subject, "needs_confirmation": True}


def tool_draft_reply(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Compose a supplier-reply DRAFT into this thread (confirm-gated, no send)."""
    rows = gather_thread(ctx.db, ctx.procurement_record_id, ctx.supplier_po_no)
    last_incoming = next(
        (r["body"] for r in reversed(rows) if r["direction"] == "INCOMING"), None
    )
    instruction = (args.get("instruction") or "").strip()
    body = ""
    if ai_service.is_enabled():
        try:
            body = ai_service.suggest_customer_reply(
                customer_name=None, subject=f"PO {ctx.supplier_po_no}",
                customer_message=last_incoming, supplier_po_no=ctx.supplier_po_no,
                instruction=instruction or None,
            )
        except Exception:  # noqa: BLE001
            log.exception("suggest_customer_reply failed; using fallback body")
    if not body:
        body = instruction or "Thank you for the update — we will revert shortly."
    msg = msg_service.create_message(
        ctx.db, direction="OUTGOING", status="DRAFT",
        supplier_id=ctx.supplier_id, procurement_record_id=ctx.procurement_record_id,
        supplier_po_no=ctx.supplier_po_no,
        subject=f"Re: PO {ctx.supplier_po_no}", body=body,
        mail_type="HI_AGENT_REPLY", commit=True,
    )
    descriptor = {"type": "draft", "message_id": msg.id, "recipient": "Supplier",
                  "recipient_kind": "supplier", "subject": msg.subject}
    ctx.pending_actions.append(descriptor)
    return {"drafted": True, "message_id": msg.id, "preview": body[:240],
            "needs_confirmation": True}


# ── Subscription tools (create-pending only) ─────────────────────────────────
def tool_create_subscription(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Create a PENDING subscription. Internal recipients only (no suppliers)."""
    kind = str(args.get("kind") or "").upper()
    if kind not in ("FOLLOWUP", "SCHEDULED_SUMMARY"):
        return {"created": False, "error": "kind must be FOLLOWUP or SCHEDULED_SUMMARY."}
    rec = resolve_recipient(ctx.db, args.get("mention"), allow_supplier=False)
    if not rec["found"]:
        return {"created": False, "error": rec["reason"]
                + " Subscriptions can only go to internal teammates."}
    schedule = None
    if kind == "SCHEDULED_SUMMARY":
        schedule = str(args.get("schedule") or "daily").lower()
        if schedule not in ("daily", "weekly"):
            schedule = "daily"
    sub = subs.create_pending(
        ctx.db, kind=kind, supplier_id=ctx.supplier_id,
        procurement_record_id=ctx.procurement_record_id,
        supplier_po_no=ctx.supplier_po_no, recipient_user_id=rec["user_id"],
        recipient_email=rec["email"], recipient_label=rec["label"],
        created_by_user_id=getattr(ctx.user, "id", None), schedule=schedule,
    )
    ctx.pending_actions.append({
        "type": "subscription", "subscription_id": sub.id, "kind": kind,
        "recipient": rec["label"], "schedule": schedule,
    })
    return {"created": True, "subscription_id": sub.id, "kind": kind,
            "recipient": rec["label"], "schedule": schedule, "needs_confirmation": True}


def tool_list_subscriptions(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    rows = subs.list_for_thread(
        ctx.db, procurement_record_id=ctx.procurement_record_id,
        supplier_po_no=ctx.supplier_po_no,
    )
    return {"subscriptions": [
        {"id": s.id, "kind": s.kind, "status": s.status,
         "recipient": s.recipient_label, "schedule": s.schedule}
        for s in rows
    ]}


# ── Tool registry: schemas + executor ────────────────────────────────────────
_DISPATCH: dict[str, Callable[[ToolContext, dict[str, Any]], Any]] = {
    "read_thread": tool_read_thread,
    "summarize_thread": tool_summarize,
    "extract_action_items": tool_action_items,
    "explain_signal": tool_explain_signal,
    "resolve_recipient": tool_resolve_recipient,
    "draft_email": tool_draft_email,
    "draft_reply": tool_draft_reply,
    "create_subscription": tool_create_subscription,
    "list_subscriptions": tool_list_subscriptions,
}


def make_executor(ctx: ToolContext) -> Callable[[str, dict[str, Any]], Any]:
    def _executor(name: str, args: dict[str, Any]) -> Any:
        fn = _DISPATCH.get(name)
        if fn is None:
            return {"error": f"Unknown tool: {name}"}
        return fn(ctx, args or {})
    return _executor


def _fn(name: str, description: str, properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "function", "function": {
        "name": name, "description": description,
        "parameters": {"type": "object", "properties": properties, "required": required},
    }}


TOOLS: list[dict[str, Any]] = [
    _fn("read_thread", "Read the current PO/supplier thread messages.", {}, []),
    _fn("summarize_thread", "Summarise the current thread for the user.", {}, []),
    _fn("extract_action_items", "List open questions and next actions in the thread.", {}, []),
    _fn("explain_signal", "Explain why this PO has its current risk signal.", {}, []),
    _fn("resolve_recipient", "Look up who an @mention refers to (no send).",
        {"mention": {"type": "string", "description": "e.g. @anjali"}}, ["mention"]),
    _fn("draft_email", "Prepare a one-time email DRAFT to an @mention (needs human confirm to send).",
        {"mention": {"type": "string"}, "subject": {"type": "string"},
         "body": {"type": "string"}}, ["mention", "body"]),
    _fn("draft_reply", "Draft a reply to the supplier in this thread (needs human confirm to send).",
        {"instruction": {"type": "string", "description": "What the reply should say"}}, []),
    _fn("create_subscription",
        "Set up a standing FOLLOWUP (forward each new message) or SCHEDULED_SUMMARY for an internal teammate (needs human confirm).",
        {"kind": {"type": "string", "enum": ["FOLLOWUP", "SCHEDULED_SUMMARY"]},
         "mention": {"type": "string"},
         "schedule": {"type": "string", "enum": ["daily", "weekly"],
                      "description": "Only for SCHEDULED_SUMMARY"}},
        ["kind", "mention"]),
    _fn("list_subscriptions", "List active followups/summaries on this thread.", {}, []),
]

"""Agentic tool registry for the Assistant.

Defines the OpenAI-style tool schemas the LLM may call and the executors that
run them against the live database (plus a semantic `search_knowledge` tool
backed by the pgvector store). `ai_service.chat_with_tools` drives the loop;
this module is the bridge from a tool name + args to real data.

Every executor returns a plain JSON-serialisable dict and is defensive — a bad
arg or empty result yields a structured message, never an exception that aborts
the chat turn.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Callable

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..core.config import settings
from ..models.communication_message import CommunicationMessage
from ..models.customer_mail import CustomerMail
from ..models.procurement import ProcurementRecord
from ..models.supplier import SupplierMaster
from . import embeddings_service, po_followup_service, vector_store

log = logging.getLogger(__name__)


# ── helpers ──────────────────────────────────────────────────────────────────
def _days_late(due_iso: str | None) -> int | None:
    if not due_iso:
        return None
    try:
        due = datetime.fromisoformat(due_iso).date()
    except ValueError:
        return None
    return (date.today() - due).days


def _trim(text: str | None, n: int = 280) -> str | None:
    if not text:
        return None
    text = " ".join(text.split())
    return text if len(text) <= n else text[:n] + "…"


def _group_brief(g: dict[str, Any]) -> dict[str, Any]:
    return {
        "supplier_name": g.get("supplier_name"),
        "supplier_po_no": g.get("supplier_po_no"),
        "overall_signal": g.get("overall_signal"),
        "material_count": g.get("material_count"),
        "earliest_due_date": g.get("earliest_due_date"),
        "days_late": _days_late(g.get("earliest_due_date")),
        "mapping_active": g.get("mapping_active"),
        "latest_followup_date": g.get("latest_followup_date"),
    }


# ── executors ────────────────────────────────────────────────────────────────
def _get_overview(db: Session, args: dict[str, Any]) -> dict[str, Any]:
    rows = db.execute(
        select(func.upper(ProcurementRecord.signal), func.count(ProcurementRecord.id))
        .group_by(func.upper(ProcurementRecord.signal))
    ).all()
    by_signal = {(sig or "UNSET"): int(c) for sig, c in rows}
    open_customer_mails = int(
        db.scalar(
            select(func.count(CustomerMail.id)).where(CustomerMail.status == "OPEN")
        )
        or 0
    )
    high_risk = int(
        db.scalar(
            select(func.count(ProcurementRecord.id)).where(
                func.upper(ProcurementRecord.risk_band) == "HIGH"
            )
        )
        or 0
    )
    total = int(db.scalar(select(func.count(ProcurementRecord.id))) or 0)
    return {
        "total_records": total,
        "records_by_signal": by_signal,
        "open_customer_mails": open_customer_mails,
        "high_risk_records": high_risk,
    }


def _list_red_pos(db: Session, args: dict[str, Any]) -> dict[str, Any]:
    limit = max(1, min(int(args.get("limit", 10) or 10), 50))
    supplier = (args.get("supplier_name") or "").strip() or None
    payload = po_followup_service.list_po_groups(db, supplier_name=supplier, size=200)
    red = [
        _group_brief(g)
        for g in payload.get("items", [])
        if (g.get("overall_signal") or "").upper() in {"RED", "BLACK"}
    ]
    return {"count": len(red), "purchase_orders": red[:limit]}


def _get_po_status(db: Session, args: dict[str, Any]) -> dict[str, Any]:
    po = (args.get("supplier_po_no") or "").strip()
    if not po:
        return {"error": "supplier_po_no is required"}
    anchor = db.scalar(
        select(ProcurementRecord)
        .where(ProcurementRecord.supplier_po_no == po)
        .order_by(ProcurementRecord.created_at.desc())
    )
    if anchor is None:
        return {"found": False, "supplier_po_no": po, "message": "No PO found with that number"}
    group = po_followup_service.get_po_group(db, anchor.supplier_name or "", po) or {}
    materials = [
        {
            "material_name": m.get("material_name"),
            "signal": m.get("signal"),
            "current_status": m.get("current_status"),
            "due_date": m.get("due_date"),
            "po_qty": m.get("po_qty"),
            "committed": (m.get("commitment") or {}).get("commitment_date") if m.get("commitment") else None,
            "supplier_status": (m.get("commitment") or {}).get("supplier_status") if m.get("commitment") else None,
        }
        for m in (group.get("materials") or [])
    ]
    return {
        "found": True,
        "supplier_name": group.get("supplier_name"),
        "supplier_po_no": po,
        "overall_signal": group.get("overall_signal"),
        "earliest_due_date": group.get("earliest_due_date"),
        "days_late": _days_late(group.get("earliest_due_date")),
        "material_count": group.get("material_count"),
        "mapping_active": group.get("mapping_active"),
        "risk_band": anchor.risk_band,
        "risk_score": anchor.risk_score,
        "last_supplier_reply": _trim(anchor.last_supplier_reply, 400),
        "materials": materials[:25],
    }


def _search_supplier(db: Session, args: dict[str, Any]) -> dict[str, Any]:
    q = (args.get("query") or "").strip()
    if not q:
        return {"error": "query is required"}
    like = f"%{q}%"
    suppliers = db.scalars(
        select(SupplierMaster)
        .where(SupplierMaster.supplier_name.ilike(like))
        .order_by(SupplierMaster.supplier_name.asc())
        .limit(10)
    ).all()
    # Also match supplier names that only appear on procurement rows.
    names = {s.supplier_name for s in suppliers}
    extra = db.execute(
        select(ProcurementRecord.supplier_name)
        .where(ProcurementRecord.supplier_name.ilike(like))
        .distinct()
        .limit(10)
    ).all()
    for (name,) in extra:
        if name:
            names.add(name)

    out: list[dict[str, Any]] = []
    for name in sorted(n for n in names if n):
        rows = db.execute(
            select(func.upper(ProcurementRecord.signal), func.count(ProcurementRecord.id))
            .where(func.upper(ProcurementRecord.supplier_name) == name.upper())
            .group_by(func.upper(ProcurementRecord.signal))
        ).all()
        by_signal = {(sig or "UNSET"): int(c) for sig, c in rows}
        out.append(
            {
                "supplier_name": name,
                "record_count": sum(by_signal.values()),
                "by_signal": by_signal,
            }
        )
    return {"count": len(out), "suppliers": out[:10]}


def _get_mail_thread(db: Session, args: dict[str, Any]) -> dict[str, Any]:
    po = (args.get("supplier_po_no") or "").strip()
    limit = max(1, min(int(args.get("limit", 12) or 12), 30))
    if not po:
        return {"error": "supplier_po_no is required"}
    msgs = db.scalars(
        select(CommunicationMessage)
        .where(CommunicationMessage.supplier_po_no == po)
        .order_by(CommunicationMessage.created_at.asc())
        .limit(limit)
    ).all()
    thread = [
        {
            "direction": m.direction,
            "status": m.status,
            "mail_type": m.mail_type,
            "subject": m.subject,
            "parsed_status": m.parsed_status,
            "snippet": _trim(m.body, 240),
            "at": (m.received_at or m.created_at).isoformat() if (m.received_at or m.created_at) else None,
        }
        for m in msgs
    ]
    return {"supplier_po_no": po, "message_count": len(thread), "thread": thread}


def _search_knowledge(db: Session, args: dict[str, Any]) -> dict[str, Any]:
    if not (embeddings_service.is_enabled() and vector_store.available()):
        return {"available": False, "message": "Semantic memory is not enabled."}
    q = (args.get("query") or "").strip()
    if not q:
        return {"error": "query is required"}
    k = max(1, min(int(args.get("limit", settings.RAG_TOP_K) or settings.RAG_TOP_K), 10))
    source_types = args.get("source_types") or None
    if isinstance(source_types, str):
        source_types = [source_types]
    try:
        emb = embeddings_service.embed_query(q)
    except Exception as exc:  # noqa: BLE001
        log.exception("search_knowledge embed failed")
        return {"available": True, "error": str(exc), "results": []}
    hits = vector_store.search(db, embedding=emb, k=k, source_types=source_types)
    return {
        "available": True,
        "count": len(hits),
        "results": [
            {
                "source_type": h["source_type"],
                "source_id": h["source_id"],
                "similarity": h["similarity"],
                "content": _trim(h["content"], 500),
                "metadata": h.get("metadata"),
            }
            for h in hits
        ],
    }


_EXECUTORS: dict[str, Callable[[Session, dict[str, Any]], dict[str, Any]]] = {
    "get_overview": _get_overview,
    "list_red_pos": _list_red_pos,
    "get_po_status": _get_po_status,
    "search_supplier": _search_supplier,
    "get_mail_thread": _get_mail_thread,
    "search_knowledge": _search_knowledge,
}


# ── tool schemas ─────────────────────────────────────────────────────────────
def _spec(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }


_BASE_SPECS = [
    _spec(
        "get_overview",
        "Portfolio snapshot: counts of procurement records by risk signal "
        "(GREEN/YELLOW/RED/BLACK), number of open customer mails, and high-risk "
        "record count. Use for 'how are we doing' / 'summarise RED signals'.",
        {},
        [],
    ),
    _spec(
        "list_red_pos",
        "List the highest-risk purchase orders (RED or BLACK signal), most urgent "
        "first, with supplier, PO number, material count, due date and days late.",
        {
            "limit": {"type": "integer", "description": "Max POs to return (default 10)."},
            "supplier_name": {"type": "string", "description": "Optional exact/partial supplier filter."},
        },
        [],
    ),
    _spec(
        "get_po_status",
        "Full status of one purchase order by its supplier PO number: overall "
        "signal, due date, per-material status & supplier commitments, last reply.",
        {"supplier_po_no": {"type": "string", "description": "The supplier PO number."}},
        ["supplier_po_no"],
    ),
    _spec(
        "search_supplier",
        "Find suppliers by a name fragment and return how many procurement records "
        "they have broken down by risk signal.",
        {"query": {"type": "string", "description": "Supplier name or fragment."}},
        ["query"],
    ),
    _spec(
        "get_mail_thread",
        "Return the email thread (incoming supplier replies + outgoing follow-ups) "
        "for a given supplier PO number, oldest first.",
        {
            "supplier_po_no": {"type": "string", "description": "The supplier PO number."},
            "limit": {"type": "integer", "description": "Max messages (default 12)."},
        },
        ["supplier_po_no"],
    ),
]

_KNOWLEDGE_SPEC = _spec(
    "search_knowledge",
    "Semantic search over the memory of past customer mails and supplier replies. "
    "Use to find precedent: how similar issues, complaints or delays were handled "
    "before. Returns the most relevant past message snippets.",
    {
        "query": {"type": "string", "description": "What to look for (natural language)."},
        "limit": {"type": "integer", "description": "Max results (default 5)."},
        "source_types": {
            "type": "array",
            "items": {"type": "string", "enum": ["customer_mail", "supplier_reply"]},
            "description": "Optional filter on the kind of past message.",
        },
    },
    ["query"],
)


def tool_specs() -> list[dict[str, Any]]:
    """Tools exposed to the model — includes search_knowledge only when RAG is on."""
    specs = list(_BASE_SPECS)
    if embeddings_service.is_enabled() and vector_store.available():
        specs.append(_KNOWLEDGE_SPEC)
    return specs


def make_executor(db: Session) -> Callable[[str, dict[str, Any]], dict[str, Any]]:
    """Bind a db session to a (name, args) -> result dispatcher for the agent loop."""

    def _run(name: str, args: dict[str, Any]) -> dict[str, Any]:
        fn = _EXECUTORS.get(name)
        if fn is None:
            return {"error": f"unknown tool: {name}"}
        return fn(db, args or {})

    return _run

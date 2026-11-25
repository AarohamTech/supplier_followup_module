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
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Callable

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..core.config import settings
from ..models.communication_message import CommunicationMessage
from ..models.customer_mail import CustomerMail
from ..models.procurement import ProcurementRecord
from .po_visibility import supplier_visible_clause
from .po_open_lines import open_line_clause
from ..models.supplier import SupplierMaster
from . import embeddings_service, po_followup_service, vector_store

log = logging.getLogger(__name__)


# ── Caller scope ──────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class ToolScope:
    """Who the assistant is acting for. A supplier scope hard-filters every tool
    to that supplier's data so one supplier can never see another's. Staff scope
    (the default) is unrestricted, unless ``staff`` carries a non-admin
    ``staff_scope.StaffScope`` — then every tool sees only that user's POs.
    """
    supplier_id: int | None = None
    supplier_name: str | None = None
    staff: Any = None  # services.staff_scope.StaffScope | None

    @property
    def is_supplier(self) -> bool:
        return self.supplier_id is not None


STAFF_SCOPE = ToolScope()

# Outbound statuses a supplier is allowed to see (mirror routers/portal.py).
_VISIBLE_OUTGOING = {"SENT", "SENT_MANUALLY", "READY", "COPIED", "MAILTO_OPENED"}

# Tools a supplier account may call (everything else is staff-only).
_SUPPLIER_TOOLS = {"get_overview", "list_red_pos", "get_po_status", "get_mail_thread"}


def _owns_po(db: Session, scope: ToolScope, supplier_po_no: str) -> bool:
    """True if the PO has at least one line belonging to the scoped supplier
    (or, for a scoped staff user, is one of their own POs)."""
    if scope.staff is not None and supplier_po_no not in scope.staff.po_counters:
        return False
    if not scope.is_supplier or not scope.supplier_name:
        return True
    return db.scalar(
        select(func.count(ProcurementRecord.id)).where(
            supplier_visible_clause(),
            ProcurementRecord.supplier_po_no == supplier_po_no,
            func.upper(ProcurementRecord.supplier_name) == scope.supplier_name.upper(),
        )
    ) > 0


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
def _get_overview(db: Session, args: dict[str, Any], scope: ToolScope) -> dict[str, Any]:
    # Open lines only (po_open_lines) — the same counts the dashboard shows.
    sig_stmt = select(
        func.upper(ProcurementRecord.signal), func.count(ProcurementRecord.id)
    ).where(open_line_clause())
    total_stmt = select(func.count(ProcurementRecord.id)).where(open_line_clause())
    high_stmt = select(func.count(ProcurementRecord.id)).where(
        func.upper(ProcurementRecord.risk_band) == "HIGH", open_line_clause()
    )
    if scope.is_supplier and scope.supplier_name:
        cond = func.upper(ProcurementRecord.supplier_name) == scope.supplier_name.upper()
        sig_stmt = sig_stmt.where(cond)
        total_stmt = total_stmt.where(cond)
        high_stmt = high_stmt.where(cond)
    if scope.staff is not None:
        cond = scope.staff.record_clause(ProcurementRecord)
        sig_stmt = sig_stmt.where(cond)
        total_stmt = total_stmt.where(cond)
        high_stmt = high_stmt.where(cond)
    by_signal = {(sig or "UNSET"): int(c) for sig, c in db.execute(sig_stmt.group_by(func.upper(ProcurementRecord.signal))).all()}
    out: dict[str, Any] = {
        "total_records": int(db.scalar(total_stmt) or 0),
        "records_by_signal": by_signal,
        "high_risk_records": int(db.scalar(high_stmt) or 0),
    }
    # Customer inbox is internal-only — never surfaced to suppliers, and not
    # PO-scoped, so left out for scoped staff too.
    if not scope.is_supplier and scope.staff is None:
        out["open_customer_mails"] = int(
            db.scalar(select(func.count(CustomerMail.id)).where(CustomerMail.status == "OPEN")) or 0
        )
    return out


def _list_red_pos(db: Session, args: dict[str, Any], scope: ToolScope) -> dict[str, Any]:
    limit = max(1, min(int(args.get("limit", 10) or 10), 50))
    # A supplier scope forces their own name; staff may filter by any supplier.
    supplier = scope.supplier_name if scope.is_supplier else ((args.get("supplier_name") or "").strip() or None)
    if scope.staff is not None:
        groups = [
            g for g in po_followup_service.build_all_po_groups(db, supplier_name=supplier)
            if scope.staff.allows_pair(g.get("supplier_name"), g.get("supplier_po_no"))
        ]
    else:
        groups = po_followup_service.list_po_groups(db, supplier_name=supplier, size=200).get("items", [])
    red = [
        _group_brief(g)
        for g in groups
        if (g.get("overall_signal") or "").upper() in {"RED", "BLACK"}
    ]
    return {"count": len(red), "purchase_orders": red[:limit]}


def _get_po_status(db: Session, args: dict[str, Any], scope: ToolScope) -> dict[str, Any]:
    po = (args.get("supplier_po_no") or "").strip()
    if not po:
        return {"error": "supplier_po_no is required"}
    if not _owns_po(db, scope, po):
        return {"found": False, "supplier_po_no": po, "message": "No PO found with that number"}
    anchor_stmt = select(ProcurementRecord).where(ProcurementRecord.supplier_po_no == po)
    if scope.staff is not None:
        # The counter is recycled across suppliers — anchor on the user's own pair.
        anchor_stmt = anchor_stmt.where(
            scope.staff.pair_clause(ProcurementRecord.supplier_name, ProcurementRecord.supplier_po_no)
        )
    anchor = db.scalar(anchor_stmt.order_by(ProcurementRecord.created_at.desc()))
    if anchor is None:
        return {"found": False, "supplier_po_no": po, "message": "No PO found with that number"}
    group = po_followup_service.get_po_group(db, anchor.supplier_name or "", po) or {}
    if not group:
        # Every line is closed (received / cancelled / off the pending desk).
        return {
            "found": True,
            "supplier_name": anchor.supplier_name,
            "supplier_po_no": po,
            "closed": True,
            "message": "This PO is closed — nothing is pending on it.",
        }
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


def _search_supplier(db: Session, args: dict[str, Any], scope: ToolScope) -> dict[str, Any]:
    # Cross-supplier search is staff-only; suppliers can never reach this tool.
    if scope.is_supplier:
        return {"error": "not available"}
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
    if scope.staff is not None:
        names = {n for n in names if scope.staff.allows_supplier(n)}
    extra = db.execute(
        select(ProcurementRecord.supplier_name)
        .where(ProcurementRecord.supplier_name.ilike(like))
        .distinct()
        .limit(10)
    ).all()
    for (name,) in extra:
        if name and (scope.staff is None or scope.staff.allows_supplier(name)):
            names.add(name)

    out: list[dict[str, Any]] = []
    for name in sorted(n for n in names if n):
        count_stmt = (
            select(func.upper(ProcurementRecord.signal), func.count(ProcurementRecord.id))
            .where(func.upper(ProcurementRecord.supplier_name) == name.upper())
        )
        if scope.staff is not None:
            count_stmt = count_stmt.where(scope.staff.record_clause(ProcurementRecord))
        rows = db.execute(count_stmt.group_by(func.upper(ProcurementRecord.signal))).all()
        by_signal = {(sig or "UNSET"): int(c) for sig, c in rows}
        out.append(
            {
                "supplier_name": name,
                "record_count": sum(by_signal.values()),
                "by_signal": by_signal,
            }
        )
    return {"count": len(out), "suppliers": out[:10]}


def _get_mail_thread(db: Session, args: dict[str, Any], scope: ToolScope) -> dict[str, Any]:
    po = (args.get("supplier_po_no") or "").strip()
    limit = max(1, min(int(args.get("limit", 12) or 12), 30))
    if not po:
        return {"error": "supplier_po_no is required"}
    if not _owns_po(db, scope, po):
        return {"supplier_po_no": po, "message_count": 0, "thread": []}
    stmt = (
        select(CommunicationMessage)
        .where(CommunicationMessage.supplier_po_no == po)
        .order_by(CommunicationMessage.created_at.asc())
    )
    if scope.is_supplier:
        # Only this supplier's own visible messages (no internal drafts).
        stmt = stmt.where(CommunicationMessage.supplier_id == scope.supplier_id)
    if scope.staff is not None:
        stmt = stmt.where(scope.staff.pair_clause(
            CommunicationMessage.supplier_name, CommunicationMessage.supplier_po_no
        ))
    msgs = [
        m for m in db.scalars(stmt.limit(limit)).all()
        if not scope.is_supplier
        or m.direction == "INCOMING"
        or (m.status in _VISIBLE_OUTGOING)
    ]
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


def _search_knowledge(db: Session, args: dict[str, Any], scope: ToolScope) -> dict[str, Any]:
    # Shared memory spans all suppliers' threads → admin/unscoped staff only.
    if scope.is_supplier or scope.staff is not None:
        return {"available": False, "message": "not available"}
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


_EXECUTORS: dict[str, Callable[[Session, dict[str, Any], "ToolScope"], dict[str, Any]]] = {
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


def tool_specs(scope: ToolScope = STAFF_SCOPE) -> list[dict[str, Any]]:
    """Tools exposed to the model for this caller. Suppliers get a scoped subset
    (no cross-supplier search, no shared memory); staff get everything (+ RAG)."""
    if scope.is_supplier:
        return [s for s in _BASE_SPECS if s["function"]["name"] in _SUPPLIER_TOOLS]
    specs = list(_BASE_SPECS)
    if scope.staff is None and embeddings_service.is_enabled() and vector_store.available():
        specs.append(_KNOWLEDGE_SPEC)
    return specs


def make_executor(
    db: Session, scope: ToolScope = STAFF_SCOPE
) -> Callable[[str, dict[str, Any]], dict[str, Any]]:
    """Bind a db session + caller scope to a (name, args) -> result dispatcher.

    For supplier scope, any tool outside the allowed set is refused even if the
    model tries to call it — defence in depth on top of the scoped tool_specs.
    """

    def _run(name: str, args: dict[str, Any]) -> dict[str, Any]:
        if scope.is_supplier and name not in _SUPPLIER_TOOLS:
            return {"error": "not available"}
        fn = _EXECUTORS.get(name)
        if fn is None:
            return {"error": f"unknown tool: {name}"}
        return fn(db, args or {}, scope)

    return _run

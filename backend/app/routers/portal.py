"""Supplier portal API — scoped to the logged-in supplier account.

Mounted in main.py with `Depends(get_current_supplier)`, so every handler can
trust `user.supplier_id`. Suppliers only ever see their own POs/ASNs.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.deps import get_current_supplier
from ..database import get_db
from ..models.asn import Asn
from ..models.communication_message import CommunicationMessage
from ..models.communication_task import CommunicationTask
from ..models.procurement import ProcurementRecord
from ..models.supplier import SupplierMaster
from ..models.supplier_material_commitment import SupplierMaterialCommitment
from ..models.user import User
from ..schemas.asn import AsnCreate, AsnEventIn, AsnListOut, AsnOut, AsnSummaryOut, AsnUpdate
from ..schemas.portal import (
    PortalCommitmentSubmit,
    PortalMessage,
    PortalMessageCreate,
    PortalPo,
    PortalPoListResponse,
    PortalPoMaterial,
    PortalSummary,
    PortalTask,
)
from ..services import ai_service
from ..services import ai_tools_service
from ..services import asn_service
from ..services import communication_message_service as msg_service
from ..services import notification_service as notif
from ..services import po_followup_service
from ..services.ai_service import AIDisabledError

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/portal", tags=["portal"])

# Outgoing (buyer→supplier) statuses the supplier is allowed to see — i.e. mails
# sent or in-flight to them (incl. READY = queued/portal-posted). Only internal
# DRAFTs awaiting approval stay hidden.
_VISIBLE_OUTGOING = {"SENT", "SENT_MANUALLY", "READY", "COPIED", "MAILTO_OPENED"}
_TAG_RE = re.compile(r"<[^>]+>")


# ── Scope helpers ─────────────────────────────────────────────────────────────
def _supplier_name(db: Session, user: User) -> str | None:
    supplier = db.get(SupplierMaster, user.supplier_id)
    return supplier.supplier_name if supplier else None


def _po_records(db: Session, supplier_name: str | None) -> list[ProcurementRecord]:
    if not supplier_name:
        return []
    return list(
        db.scalars(
            select(ProcurementRecord).where(
                func.upper(ProcurementRecord.supplier_name) == supplier_name.upper()
            )
        ).all()
    )


def _load_owned_asn(db: Session, asn_id: int, user: User) -> Asn:
    asn = asn_service.get_asn(db, asn_id, supplier_id=user.supplier_id)
    if asn is None:
        raise HTTPException(404, "ASN not found")
    return asn


# ── Profile + dashboard ───────────────────────────────────────────────────────
@router.get("/me")
def me(user: User = Depends(get_current_supplier), db: Session = Depends(get_db)) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "supplier_id": user.supplier_id,
        "supplier_name": _supplier_name(db, user),
        "must_change_password": user.must_change_password,
    }


@router.get("/summary", response_model=PortalSummary)
def summary(user: User = Depends(get_current_supplier), db: Session = Depends(get_db)) -> PortalSummary:
    name = _supplier_name(db, user)
    records = _po_records(db, name)
    po_nos = {r.supplier_po_no for r in records if r.supplier_po_no}
    completed = asn_service.completed_po_numbers(db, supplier_id=user.supplier_id) & po_nos
    blocked = {r.supplier_po_no for r in records if (r.signal or "").upper() == "BLACK" and r.supplier_po_no}
    return PortalSummary(
        supplier_name=name,
        total_pos=len(po_nos),
        completed_pos=len(completed),
        pending_pos=len(po_nos) - len(completed),
        blocked_count=len(blocked),
        asn=AsnSummaryOut(**asn_service.asn_summary(db, supplier_id=user.supplier_id)),
    )


# ── POs ───────────────────────────────────────────────────────────────────────
_SIGNAL_RANK = {"GREEN": 1, "YELLOW": 2, "RED": 3, "BLACK": 4}


def _worst_signal(signals: list[str | None]) -> str | None:
    worst = None
    worst_rank = 0
    for sig in signals:
        s = (sig or "").upper()
        r = _SIGNAL_RANK.get(s, 0)
        if r > worst_rank:
            worst_rank, worst = r, s
    return worst


@router.get("/pos", response_model=PortalPoListResponse)
def list_pos(user: User = Depends(get_current_supplier), db: Session = Depends(get_db)) -> PortalPoListResponse:
    name = _supplier_name(db, user)
    records = _po_records(db, name)
    completed = asn_service.completed_po_numbers(db, supplier_id=user.supplier_id)

    # ASN count per PO.
    asn_counts: dict[str, int] = {}
    for po_no in db.scalars(select(Asn.supplier_po_no).where(Asn.supplier_id == user.supplier_id)).all():
        if po_no:
            asn_counts[po_no] = asn_counts.get(po_no, 0) + 1

    # Visible message count per PO (incoming + sent outgoing).
    msg_counts: dict[str, int] = {}
    msg_rows = db.execute(
        select(CommunicationMessage.supplier_po_no, CommunicationMessage.direction, CommunicationMessage.status)
        .where(CommunicationMessage.supplier_id == user.supplier_id)
    ).all()
    for po_no, direction, status in msg_rows:
        if not po_no:
            continue
        if direction == "INCOMING" or status in _VISIBLE_OUTGOING:
            msg_counts[po_no] = msg_counts.get(po_no, 0) + 1

    groups: dict[str, dict] = {}
    for r in records:
        po = r.supplier_po_no
        if not po:
            continue
        g = groups.setdefault(po, {
            "crm_no": r.crm_no,
            "signals": [],
            "po_status": r.po_status,
            "earliest": None,
            "count": 0,
            "escalated": False,
        })
        g["count"] += 1
        g["signals"].append(r.signal)
        if (r.escalation_level or "NONE").upper() != "NONE":
            g["escalated"] = True
        if r.shipment_date and (g["earliest"] is None or r.shipment_date < g["earliest"]):
            g["earliest"] = r.shipment_date

    items = [
        PortalPo(
            supplier_po_no=po,
            crm_no=g["crm_no"],
            material_count=g["count"],
            overall_signal=_worst_signal(g["signals"]),
            po_status=g["po_status"],
            earliest_shipment_date=g["earliest"],
            completed=po in completed,
            asn_count=asn_counts.get(po, 0),
            message_count=msg_counts.get(po, 0),
            escalated=g["escalated"],
        )
        for po, g in sorted(groups.items())
    ]
    # Escalated POs first; then worst signal; then by PO number (stable).
    items.sort(
        key=lambda p: (
            0 if p.escalated else 1,
            -_SIGNAL_RANK.get((p.overall_signal or "").upper(), 0),
            p.supplier_po_no,
        )
    )
    return PortalPoListResponse(count=len(items), items=items)


@router.get("/pos/{supplier_po_no}/materials", response_model=list[PortalPoMaterial])
def po_materials(
    supplier_po_no: str,
    user: User = Depends(get_current_supplier),
    db: Session = Depends(get_db),
) -> list[PortalPoMaterial]:
    name = _supplier_name(db, user)
    if not name:
        return []
    rows = db.scalars(
        select(ProcurementRecord).where(
            func.upper(ProcurementRecord.supplier_name) == name.upper(),
            ProcurementRecord.supplier_po_no == supplier_po_no,
        )
    ).all()
    commits = _commitments_by_material(db, supplier_po_no)
    return [_material_out(r, commits.get((r.material_name or "").strip().upper())) for r in rows]


def _as_dt(d) -> datetime | None:
    if d is None:
        return None
    return d if isinstance(d, datetime) else datetime.combine(d, datetime.min.time())


def _commitments_by_material(db: Session, supplier_po_no: str) -> dict[str, SupplierMaterialCommitment]:
    rows = db.scalars(
        select(SupplierMaterialCommitment)
        .where(SupplierMaterialCommitment.supplier_po_no == supplier_po_no)
        .order_by(SupplierMaterialCommitment.updated_at.desc())
    ).all()
    out: dict[str, SupplierMaterialCommitment] = {}
    for c in rows:
        key = (c.material_name or "").strip().upper()
        if key and key not in out:
            out[key] = c
    return out


def _material_out(r: ProcurementRecord, c: SupplierMaterialCommitment | None) -> PortalPoMaterial:
    return PortalPoMaterial(
        procurement_record_id=r.id,
        crm_no=r.crm_no,
        material_name=r.material_name,
        uom=r.uom,
        qty=float(r.qty) if r.qty is not None else None,
        po_date=_as_dt(r.supplier_date or r.po_date),
        shipment_date=r.shipment_date,
        signal=r.signal,
        po_status=r.po_status,
        commitment_date=_as_dt(c.commitment_date) if c else None,
        commitment_qty=float(c.commitment_qty) if c and c.commitment_qty is not None else None,
        commitment_status=c.supplier_status if c else None,
        commitment_remark=c.supplier_remark if c else None,
    )


@router.post("/pos/{supplier_po_no}/commitments", response_model=list[PortalPoMaterial])
def submit_commitments(
    supplier_po_no: str,
    payload: PortalCommitmentSubmit,
    user: User = Depends(get_current_supplier),
    db: Session = Depends(get_db),
) -> list[PortalPoMaterial]:
    name = _supplier_name(db, user)
    if not _po_is_owned(db, name, supplier_po_no):
        raise HTTPException(404, "PO not found for your account")

    saved = 0
    for item in payload.items:
        rec = db.get(ProcurementRecord, item.procurement_record_id)
        # Only accept rows that actually belong to this supplier's PO.
        if (
            rec is None
            or rec.supplier_po_no != supplier_po_no
            or (rec.supplier_name or "").upper() != (name or "").upper()
        ):
            continue
        cdate: date | None = None
        if item.commitment_date:
            try:
                cdate = date.fromisoformat(item.commitment_date)
            except ValueError:
                cdate = None
        if cdate is None:
            continue  # a commitment requires a committed dispatch date
        po_followup_service.upsert_commitment(
            db,
            supplier_po_no=supplier_po_no,
            material_name=rec.material_name,
            procurement_record_id=rec.id,
            supplier_id=user.supplier_id,
            supplier_name=name,
            material_code=rec.crm_no,
            commitment_qty=item.commitment_qty,
            commitment_date_value=cdate,
            supplier_status=item.supplier_status or "CONFIRMED",
            supplier_remark=item.supplier_remark,
            reply_mail_id=None,
            commit=False,
        )
        if cdate is not None:
            rec.commitment_date = cdate
        saved += 1

    db.commit()
    if saved:
        notif.safe(
            notif.notify_po_owners, db,
            type="COMMITMENT_RECEIVED",
            title=f"Commitment received from {name or 'a supplier'}",
            body=f"PO {supplier_po_no}: {saved} material(s) committed",
            link="/mail-history",
            supplier_id=user.supplier_id,
            supplier_po_no=supplier_po_no,
        )
    commits = _commitments_by_material(db, supplier_po_no)
    rows = db.scalars(
        select(ProcurementRecord).where(
            func.upper(ProcurementRecord.supplier_name) == (name or "").upper(),
            ProcurementRecord.supplier_po_no == supplier_po_no,
        )
    ).all()
    return [_material_out(r, commits.get((r.material_name or "").strip().upper())) for r in rows]


# ── PO tasks (read-only view of the internal team's tasks for this PO) ────────
@router.get("/pos/{supplier_po_no}/tasks", response_model=list[PortalTask])
def po_tasks(
    supplier_po_no: str,
    user: User = Depends(get_current_supplier),
    db: Session = Depends(get_db),
) -> list[PortalTask]:
    name = _supplier_name(db, user)
    if not _po_is_owned(db, name, supplier_po_no):
        raise HTTPException(404, "PO not found for your account")
    rows = db.scalars(
        select(CommunicationTask).where(
            CommunicationTask.supplier_po_no == supplier_po_no,
            or_(
                CommunicationTask.supplier_id == user.supplier_id,
                func.upper(CommunicationTask.supplier_name) == (name or "").upper(),
            ),
        )
    ).all()
    # Open tasks first, then by due date (undated last).
    rows = sorted(
        rows,
        key=lambda t: (1 if (t.status or "").upper() == "DONE" else 0, t.due_date or datetime.max),
    )
    return [
        PortalTask(
            id=t.id,
            title=t.title,
            description=t.description,
            material_name=t.material_name,
            status=t.status,
            priority=t.priority,
            signal=t.signal,
            progress_percent=t.progress_percent,
            due_date=t.due_date,
            created_at=t.created_at,
            closed_at=t.closed_at,
        )
        for t in rows
    ]


# ── All tasks for this supplier (read-only Task Manager) ──────────────────────
@router.get("/tasks", response_model=list[PortalTask])
def supplier_tasks(
    user: User = Depends(get_current_supplier),
    db: Session = Depends(get_db),
) -> list[PortalTask]:
    """Every internal task linked to this supplier — view only."""
    name = _supplier_name(db, user)
    rows = db.scalars(
        select(CommunicationTask).where(
            or_(
                CommunicationTask.supplier_id == user.supplier_id,
                func.upper(CommunicationTask.supplier_name) == (name or "").upper(),
            )
        )
    ).all()
    # Open tasks first, then by due date (undated last).
    rows = sorted(
        rows,
        key=lambda t: (1 if (t.status or "").upper() == "DONE" else 0, t.due_date or datetime.max),
    )
    return [
        PortalTask(
            id=t.id,
            title=t.title,
            description=t.description,
            material_name=t.material_name,
            status=t.status,
            priority=t.priority,
            signal=t.signal,
            progress_percent=t.progress_percent,
            due_date=t.due_date,
            created_at=t.created_at,
            closed_at=t.closed_at,
        )
        for t in rows
    ]


# ── PO messaging (shared thread with the staff Communication Hub) ─────────────
def _message_text(cm: CommunicationMessage) -> str:
    if cm.body and cm.body.strip():
        return cm.body.strip()
    if cm.body_html:
        return re.sub(r"\s+", " ", _TAG_RE.sub(" ", cm.body_html)).strip()
    return ""


def _to_portal_message(cm: CommunicationMessage, supplier_name: str | None) -> PortalMessage:
    mine = cm.direction == "INCOMING"  # supplier-authored
    author = (supplier_name or "You") if mine else "Procurement · Harmony × Hariom"
    return PortalMessage(
        id=cm.id,
        direction=cm.direction,
        mine=mine,
        author=author,
        subject=cm.subject,
        body=_message_text(cm),
        mail_type=cm.mail_type,
        status=cm.status,
        at=cm.sent_at or cm.received_at or cm.created_at,
    )


def _po_is_owned(db: Session, supplier_name: str | None, supplier_po_no: str) -> ProcurementRecord | None:
    if not supplier_name:
        return None
    return db.scalar(
        select(ProcurementRecord).where(
            func.upper(ProcurementRecord.supplier_name) == supplier_name.upper(),
            ProcurementRecord.supplier_po_no == supplier_po_no,
        )
    )


@router.get("/pos/{supplier_po_no}/messages", response_model=list[PortalMessage])
def list_po_messages(
    supplier_po_no: str,
    user: User = Depends(get_current_supplier),
    db: Session = Depends(get_db),
) -> list[PortalMessage]:
    name = _supplier_name(db, user)
    rows = db.scalars(
        select(CommunicationMessage)
        .where(
            CommunicationMessage.supplier_id == user.supplier_id,
            CommunicationMessage.supplier_po_no == supplier_po_no,
        )
        .order_by(CommunicationMessage.created_at.asc())
    ).all()
    visible = [
        cm for cm in rows
        if cm.direction == "INCOMING" or cm.status in _VISIBLE_OUTGOING
    ]
    return [_to_portal_message(cm, name) for cm in visible]


@router.post("/pos/{supplier_po_no}/messages", response_model=PortalMessage, status_code=201)
def post_po_message(
    supplier_po_no: str,
    payload: PortalMessageCreate,
    user: User = Depends(get_current_supplier),
    db: Session = Depends(get_db),
) -> PortalMessage:
    name = _supplier_name(db, user)
    rec = _po_is_owned(db, name, supplier_po_no)
    if rec is None:
        raise HTTPException(404, "PO not found for your account")

    subject = (payload.subject or "").strip() or f"Supplier message · PO {supplier_po_no}"
    # Stored as an INCOMING message → shows in the staff Communication Hub thread
    # and increments their unread badge (read_at left NULL).
    cm = msg_service.create_message(
        db,
        direction="INCOMING",
        status="RECEIVED",
        supplier_id=user.supplier_id,
        supplier_name=name,
        procurement_record_id=rec.id,
        supplier_po_no=supplier_po_no,
        subject=subject,
        body=payload.body.strip(),
        sender_email=user.email,
        mail_type="PORTAL_MESSAGE",
        received_at=datetime.utcnow(),
    )
    notif.safe(
        notif.notify_po_owners, db,
        type="SUPPLIER_MESSAGE",
        title=f"New message from {name or 'a supplier'}",
        body=f"PO {supplier_po_no}: {payload.body.strip()[:140]}",
        link="/mail-history",
        supplier_id=user.supplier_id,
        supplier_po_no=supplier_po_no,
        procurement_record_id=rec.id,
    )
    return _to_portal_message(cm, name)


# ── ASNs ──────────────────────────────────────────────────────────────────────
@router.get("/asns/summary", response_model=AsnSummaryOut)
def asns_summary(user: User = Depends(get_current_supplier), db: Session = Depends(get_db)) -> AsnSummaryOut:
    return AsnSummaryOut(**asn_service.asn_summary(db, supplier_id=user.supplier_id))


@router.get("/asns", response_model=AsnListOut)
def list_asns(
    user: User = Depends(get_current_supplier),
    db: Session = Depends(get_db),
    tab: str | None = Query(default=None),
    search: str | None = Query(default=None),
) -> AsnListOut:
    rows = asn_service.list_asns(db, supplier_id=user.supplier_id, tab=tab, search=search)
    return AsnListOut(count=len(rows), items=[AsnOut.model_validate(r) for r in rows])


@router.post("/asns", response_model=AsnOut, status_code=201)
def create_asn(
    payload: AsnCreate,
    user: User = Depends(get_current_supplier),
    db: Session = Depends(get_db),
) -> AsnOut:
    name = _supplier_name(db, user)
    # Guard: the PO must belong to this supplier.
    owns_po = db.scalar(
        select(func.count(ProcurementRecord.id)).where(
            func.upper(ProcurementRecord.supplier_name) == (name or "").upper(),
            ProcurementRecord.supplier_po_no == payload.supplier_po_no,
        )
    )
    if not owns_po:
        raise HTTPException(400, "PO reference not found for your account")

    if payload.transport_mode and payload.transport_mode.upper() not in asn_service.TRANSPORT_MODES:
        raise HTTPException(422, f"transport_mode must be one of {asn_service.TRANSPORT_MODES}")

    asn = asn_service.create_asn(
        db,
        supplier_id=user.supplier_id,
        supplier_name=name,
        supplier_po_no=payload.supplier_po_no,
        crm_no=payload.crm_no,
        carrier_name=payload.carrier_name,
        courier_code=payload.courier_code,
        tracking_no=payload.tracking_no,
        transport_mode=(payload.transport_mode or "").upper() or None,
        origin=payload.origin,
        destination=payload.destination,
        dispatch_date=payload.dispatch_date,
        eta=payload.eta,
        remarks=payload.remarks,
        items=[i.model_dump() for i in payload.items],
        submit=payload.submit,
        created_by_user_id=user.id,
        created_by_email=user.email,
    )
    if asn.status != "DRAFT":
        notif.safe(
            notif.notify_po_owners, db,
            type="ASN_SUBMITTED",
            title=f"New ASN {asn.asn_no} from {name or 'a supplier'}",
            body=f"PO {asn.supplier_po_no} · {len(asn.items)} item(s)",
            link="/asns",
            supplier_id=user.supplier_id,
            supplier_po_no=asn.supplier_po_no,
            asn_id=asn.id,
        )
    return AsnOut.model_validate(asn)


@router.get("/asns/{asn_id}", response_model=AsnOut)
def get_asn(asn_id: int, user: User = Depends(get_current_supplier), db: Session = Depends(get_db)) -> AsnOut:
    return AsnOut.model_validate(_load_owned_asn(db, asn_id, user))


@router.patch("/asns/{asn_id}", response_model=AsnOut)
def update_asn(
    asn_id: int,
    payload: AsnUpdate,
    user: User = Depends(get_current_supplier),
    db: Session = Depends(get_db),
) -> AsnOut:
    asn = _load_owned_asn(db, asn_id, user)
    asn = asn_service.update_asn(db, asn, payload.model_dump(exclude_unset=True))
    return AsnOut.model_validate(asn)


@router.post("/asns/{asn_id}/events", response_model=AsnOut)
def add_event(
    asn_id: int,
    payload: AsnEventIn,
    user: User = Depends(get_current_supplier),
    db: Session = Depends(get_db),
) -> AsnOut:
    asn = _load_owned_asn(db, asn_id, user)
    if not asn_service.is_valid_status(payload.stage):
        raise HTTPException(422, f"Unknown stage '{payload.stage}'")
    asn = asn_service.add_event(
        db, asn,
        stage=payload.stage,
        location=payload.location,
        note=payload.note,
        label=payload.label,
        alert=payload.alert,
        alert_reason=payload.alert_reason,
        created_by=user.email,
        occurred_at=payload.occurred_at,
    )
    if asn.status == "DELIVERED":
        name = _supplier_name(db, user)
        notif.safe(
            notif.notify_po_owners, db,
            type="ASN_DELIVERED",
            title=f"ASN {asn.asn_no} delivered",
            body=f"PO {asn.supplier_po_no} marked delivered by {name or 'the supplier'}",
            link="/asns",
            supplier_id=user.supplier_id,
            supplier_po_no=asn.supplier_po_no,
            asn_id=asn.id,
        )
    return AsnOut.model_validate(asn)


# ── Supplier assistant (Harmony Intelligent, scoped to this supplier) ─────────
class _AssistantMessage(BaseModel):
    role: str = "user"
    content: str


class _AssistantRequest(BaseModel):
    messages: list[_AssistantMessage] = Field(default_factory=list)


@router.get("/assistant/health")
def assistant_health(user: User = Depends(get_current_supplier)) -> dict:
    return {"enabled": bool(ai_service.is_enabled())}


@router.post("/assistant/chat")
def assistant_chat(
    payload: _AssistantRequest,
    user: User = Depends(get_current_supplier),
    db: Session = Depends(get_db),
) -> dict:
    if not payload.messages:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "messages cannot be empty")

    name = _supplier_name(db, user)
    scope = ai_tools_service.ToolScope(supplier_id=user.supplier_id, supplier_name=name)
    system = (
        f"You are Harmony Intelligent, the assistant for the supplier '{name}'. "
        "You can ONLY see this supplier's own purchase orders, shipments (ASNs) and "
        "message threads — never another supplier's or any internal-only data. "
        "Always call a tool to fetch real data before answering, and be concise and "
        "professional. If asked about anything outside this supplier's orders, say you "
        "can only help with their POs and shipments." + ai_service.AGENT_TOOLS_SUFFIX
    )
    try:
        if not ai_service.is_enabled():
            raise AIDisabledError("Harmony Intelligent is currently unavailable.")
        result = ai_service.chat_with_tools(
            [m.model_dump() for m in payload.messages],
            tools=ai_tools_service.tool_specs(scope),
            executor=ai_tools_service.make_executor(db, scope),
            system=system,
        )
    except AIDisabledError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))
    except Exception as exc:  # noqa: BLE001
        log.exception("Portal assistant chat failed")
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Assistant request failed: {exc}")

    return {
        "reply": result["reply"],
        "model": settings.LLM_MODEL,
        "tools_used": result.get("tools_used", []),
    }

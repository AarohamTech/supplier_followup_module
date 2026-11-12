"""PO acknowledgement — signed mail links + supplier portal button.

A supplier confirms they received a purchase order. Two entry points share
:func:`acknowledge`:

* ``via='link'``   — the "Acknowledge PO" button in a PO follow-up mail. The link
  carries a signed token (HMAC-SHA256 with a key derived from ``JWT_SECRET``)
  that encodes the company schema, supplier and PO, so the public page needs no
  login and the token cannot be guessed or edited.
* ``via='portal'`` — the button on the supplier portal PO page.

The first acknowledgement is stored; repeat clicks return it unchanged
(idempotent). On the first acknowledgement the people responsible for the PO
are notified and a system message is posted into the PO's Communication Hub
thread.

Acknowledging is not a dispatch commitment: nothing here touches follow-up
scheduling or suppression.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.tenant import DEFAULT_SCHEMA, get_current_schema
from ..models.communication_task import CommunicationTask
from ..models.po_acknowledgement import PoAcknowledgement
from ..models.procurement import ProcurementRecord
from ..models.user import User
from . import communication_message_service as msg_service
from . import notification_service as notif

log = logging.getLogger(__name__)

TOKEN_VERSION = 1
_SIG_BYTES = 16  # 128-bit truncated HMAC — unguessable, keeps the URL short
_SCHEMA_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
ACK_MAIL_TYPE = "PO_ACK"
VIA_LABEL = {"link": "email link", "portal": "supplier portal"}


class InvalidAckToken(ValueError):
    """The token is malformed, tampered with, or signed with another key."""


# ── token ────────────────────────────────────────────────────────────────────
def _key() -> bytes:
    secret = (getattr(settings, "JWT_SECRET", "") or "").encode()
    # Derive a purpose-bound key so an ack token can never double as a JWT.
    return hmac.new(secret, b"h-connect/po-ack/v1", hashlib.sha256).digest()


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64d(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def _sign(payload_b64: str) -> str:
    digest = hmac.new(_key(), payload_b64.encode("ascii"), hashlib.sha256).digest()
    return _b64e(digest[:_SIG_BYTES])


def make_token(
    *,
    supplier_name: str,
    supplier_po_no: str | None,
    po_ref: str | None = None,
    record_id: int | None = None,
    schema: str | None = None,
) -> str:
    payload = {
        "v": TOKEN_VERSION,
        "s": schema or get_current_schema() or DEFAULT_SCHEMA,
        "n": supplier_name,
        "p": supplier_po_no or "",
        "r": po_ref or "",
        "i": record_id,
    }
    body = _b64e(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    return f"{body}.{_sign(body)}"


def verify_token(token: str) -> dict[str, Any]:
    """Return the decoded payload or raise :class:`InvalidAckToken`."""
    try:
        body, sig = (token or "").strip().split(".", 1)
    except ValueError as exc:
        raise InvalidAckToken("malformed token") from exc
    if not body or not sig or not hmac.compare_digest(_sign(body), sig):
        raise InvalidAckToken("bad signature")
    try:
        data = json.loads(_b64d(body).decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise InvalidAckToken("bad payload") from exc
    if not isinstance(data, dict) or data.get("v") != TOKEN_VERSION:
        raise InvalidAckToken("unsupported token version")
    schema = str(data.get("s") or DEFAULT_SCHEMA)
    if not _SCHEMA_RE.match(schema) or not str(data.get("n") or "").strip():
        raise InvalidAckToken("bad payload")
    if not (data.get("p") or data.get("r")):
        raise InvalidAckToken("bad payload")
    return data


def ack_url(token: str) -> str | None:
    base = (getattr(settings, "APP_BASE_URL", "") or "").strip().rstrip("/")
    if not base:
        return None
    return f"{base}/po-ack/{quote(token, safe='.-_')}"


# ── identity helpers ─────────────────────────────────────────────────────────
def supplier_key(name: str | None) -> str:
    return (name or "").strip().upper()


def po_key(supplier_po_no: str | None, po_ref: str | None) -> str:
    return ((po_ref or "").strip() or (supplier_po_no or "").strip())


def find_ack(
    db: Session, supplier_name: str | None, supplier_po_no: str | None, po_ref: str | None
) -> PoAcknowledgement | None:
    key = po_key(supplier_po_no, po_ref)
    if not key or not supplier_key(supplier_name):
        return None
    return db.scalar(
        select(PoAcknowledgement).where(
            PoAcknowledgement.supplier_key == supplier_key(supplier_name),
            PoAcknowledgement.po_key == key,
        )
    )


def acks_for_supplier(db: Session, supplier_name: str | None) -> dict[str, PoAcknowledgement]:
    """Every acknowledgement of a supplier, keyed by po_key (bulk lookup)."""
    if not supplier_key(supplier_name):
        return {}
    rows = db.scalars(
        select(PoAcknowledgement).where(
            PoAcknowledgement.supplier_key == supplier_key(supplier_name)
        )
    ).all()
    return {r.po_key: r for r in rows}


def _group_records(db: Session, rec: ProcurementRecord) -> list[ProcurementRecord]:
    from . import po_followup_service

    try:
        return po_followup_service.vendor_ref_group_for_record(db, rec) or [rec]
    except Exception:  # noqa: BLE001
        log.exception("vendor_ref_group_for_record failed for record %s", rec.id)
        return [rec]


def _ref_of(records: list[ProcurementRecord]) -> str | None:
    return next((r.po_short_ref for r in records if r.po_short_ref), None)


def resolve_po(
    db: Session,
    *,
    supplier_name: str,
    supplier_po_no: str | None,
    po_ref: str | None = None,
    record_id: int | None = None,
) -> tuple[ProcurementRecord | None, list[ProcurementRecord], str | None]:
    """Find the anchor record + its vendor-PO thread. Returns (anchor, records, ref)."""
    skey = supplier_key(supplier_name)
    anchor: ProcurementRecord | None = None
    if record_id:
        cand = db.get(ProcurementRecord, record_id)
        if cand is not None and supplier_key(cand.supplier_name) == skey:
            anchor = cand
    if anchor is None and po_ref:
        anchor = db.scalar(
            select(ProcurementRecord)
            .where(
                func.upper(ProcurementRecord.supplier_name) == skey,
                ProcurementRecord.po_short_ref == po_ref,
            )
            .order_by(ProcurementRecord.id.asc())
            .limit(1)
        )
    if anchor is None and supplier_po_no:
        anchor = db.scalar(
            select(ProcurementRecord)
            .where(
                func.upper(ProcurementRecord.supplier_name) == skey,
                ProcurementRecord.supplier_po_no == supplier_po_no,
            )
            .order_by(ProcurementRecord.id.asc())
            .limit(1)
        )
    if anchor is None:
        return None, [], po_ref or None
    records = _group_records(db, anchor)
    return anchor, records, po_ref or _ref_of(records)


# ── time formatting ──────────────────────────────────────────────────────────
def _local(dt: datetime) -> datetime:
    try:
        from zoneinfo import ZoneInfo

        tz = ZoneInfo("Asia/Kolkata")
    except Exception:  # noqa: BLE001 — no tzdata on the host
        tz = timezone(timedelta(hours=5, minutes=30))
    return dt.replace(tzinfo=timezone.utc).astimezone(tz)


def format_time(dt: datetime | None) -> str:
    if dt is None:
        return ""
    return _local(dt).strftime("%d %b %Y, %I:%M %p IST")


def ack_out(row: PoAcknowledgement | None) -> dict[str, Any]:
    if row is None:
        return {"acknowledged": False, "acknowledged_at": None, "via": None}
    return {
        "acknowledged": True,
        "acknowledged_at": row.acknowledged_at.isoformat() + "Z" if row.acknowledged_at else None,
        "acknowledged_at_label": format_time(row.acknowledged_at),
        "via": row.via,
    }


# ── follow-up mail link ──────────────────────────────────────────────────────
def ack_url_for_group(db: Session, group: dict[str, Any]) -> str | None:
    """Signed ack link for a PO follow-up group, or None when the PO is already
    acknowledged, has no supplier, or no APP_BASE_URL is configured. Never raises."""
    try:
        name = group.get("supplier_name")
        po_no = group.get("supplier_po_no")
        ref = group.get("po_ref")
        if not supplier_key(name) or not po_key(po_no, ref):
            return None
        if find_ack(db, name, po_no, ref) is not None:
            return None
        token = make_token(
            supplier_name=name,
            supplier_po_no=po_no,
            po_ref=ref,
            record_id=group.get("anchor_record_id"),
        )
        return ack_url(token)
    except Exception:  # noqa: BLE001 — a missing link must never block a follow-up
        log.exception("Could not build PO ack link")
        return None


# ── recipients ───────────────────────────────────────────────────────────────
def _recipient_users(
    db: Session, records: list[ProcurementRecord], supplier_id: int | None
) -> list[User]:
    """PO owners (owner_emp_code), the supplier's assigned staff, and the
    assignees/watchers of open tasks on the PO's records."""
    ids: set[int] = set()
    emp_codes = {r.owner_emp_code for r in records if r.owner_emp_code}
    if emp_codes:
        ids.update(
            db.scalars(
                select(User.id).where(User.is_active.is_(True), User.emp_code.in_(emp_codes))
            ).all()
        )
    if supplier_id is not None:
        from . import supplier_assignment_service

        try:
            ids.update(supplier_assignment_service.get_assignee_ids(db, supplier_id))
        except Exception:  # noqa: BLE001
            log.exception("Supplier assignee lookup failed (ignored)")
    record_ids = [r.id for r in records]
    if record_ids:
        for t in db.scalars(
            select(CommunicationTask).where(
                CommunicationTask.procurement_record_id.in_(record_ids),
                CommunicationTask.status != "DONE",
            )
        ).all():
            if t.assigned_to_user_id:
                ids.add(t.assigned_to_user_id)
            for w in t.watchers or []:
                try:
                    ids.add(int(w))
                except (TypeError, ValueError):
                    continue
    if not ids:
        return []
    return list(
        db.scalars(
            select(User).where(
                User.id.in_(ids), User.is_active.is_(True), User.supplier_id.is_(None)
            )
        ).all()
    )


def _notify(
    db: Session,
    *,
    row: PoAcknowledgement,
    records: list[ProcurementRecord],
    supplier_id: int | None,
    display_ref: str,
) -> int:
    when = format_time(row.acknowledged_at)
    fields = dict(
        type="PO_ACK",
        title=f"PO {display_ref} acknowledged",
        body=f"PO {display_ref} acknowledged by {row.supplier_name} at {when} "
        f"(via {VIA_LABEL.get(row.via, row.via)}).",
        supplier_id=supplier_id,
        supplier_po_no=row.supplier_po_no,
        procurement_record_id=row.procurement_record_id,
    )
    users = _recipient_users(db, records, supplier_id)
    if not users:
        # Orphan PO — nobody owns it, so tell the staff rather than drop it.
        return notif.notify_staff(db, link="/mail-history", **fields)
    created = 0
    for link in ("/mail-history", "/eportal/communication"):
        group = [u.id for u in users if bool(u.emp_code) == (link != "/mail-history")]
        if group:
            created += notif.notify_users(db, group, link=link, **fields)
    return created


def _post_hub_message(
    db: Session, *, row: PoAcknowledgement, supplier_id: int | None, display_ref: str
) -> None:
    when = format_time(row.acknowledged_at)
    msg_service.create_message(
        db,
        direction="INCOMING",
        status="RECEIVED",
        supplier_id=supplier_id,
        supplier_name=row.supplier_name,
        procurement_record_id=row.procurement_record_id,
        supplier_po_no=row.supplier_po_no,
        subject=f"PO {display_ref} acknowledged",
        body=(
            f"PO {display_ref} acknowledged by {row.supplier_name} at {when} "
            f"(via {VIA_LABEL.get(row.via, row.via)})."
        ),
        mail_type=ACK_MAIL_TYPE,
        received_at=row.acknowledged_at,
        raw_payload={"system": True, "po_ack_id": row.id, "via": row.via},
        commit=True,
    )


# ── the write ────────────────────────────────────────────────────────────────
def acknowledge(
    db: Session,
    *,
    supplier_name: str,
    supplier_po_no: str | None,
    po_ref: str | None = None,
    record_id: int | None = None,
    via: str,
    ip: str | None = None,
    user_agent: str | None = None,
    user_id: int | None = None,
    now: datetime | None = None,
) -> tuple[PoAcknowledgement | None, bool, dict[str, Any]]:
    """Record the acknowledgement once. Returns (row, created, po_info).

    `row` is None only when the PO cannot be found. Side effects (notification,
    hub message) run only for a newly created acknowledgement and are best-effort.
    """
    anchor, records, ref = resolve_po(
        db,
        supplier_name=supplier_name,
        supplier_po_no=supplier_po_no,
        po_ref=po_ref,
        record_id=record_id,
    )
    name = (anchor.supplier_name if anchor else supplier_name) or supplier_name
    counter = (anchor.supplier_po_no if anchor else None) or supplier_po_no
    info = {"supplier_name": name, "supplier_po_no": counter, "po_ref": ref,
            "display_ref": ref or counter}
    if anchor is None:
        return None, False, info

    existing = find_ack(db, name, counter, ref)
    if existing is not None:
        return existing, False, info

    row = PoAcknowledgement(
        supplier_name=name.strip(),
        supplier_key=supplier_key(name),
        supplier_po_no=counter,
        po_short_ref=ref,
        po_key=po_key(counter, ref),
        procurement_record_id=anchor.id,
        acknowledged_at=now or datetime.utcnow(),
        via=via,
        ip=(ip or "")[:64] or None,
        user_agent=(user_agent or "")[:512] or None,
        acknowledged_by_user_id=user_id,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        # A concurrent click won the race — read theirs back.
        db.rollback()
        existing = find_ack(db, name, counter, ref)
        return existing, False, info
    db.refresh(row)

    supplier_id = None
    try:
        supplier_id = msg_service.resolve_supplier_id_by_name(db, name)
    except Exception:  # noqa: BLE001
        log.exception("Supplier id lookup failed (ignored)")
    display_ref = info["display_ref"] or "-"
    try:
        _post_hub_message(db, row=row, supplier_id=supplier_id, display_ref=display_ref)
    except Exception:  # noqa: BLE001
        db.rollback()
        log.exception("Posting PO ack hub message failed (ignored)")
    try:
        _notify(db, row=row, records=records, supplier_id=supplier_id, display_ref=display_ref)
    except Exception:  # noqa: BLE001
        db.rollback()
        log.exception("PO ack notification failed (ignored)")
    return row, True, info


def acknowledge_by_token(
    db: Session, token: str, *, ip: str | None = None, user_agent: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Token flow. The caller must already be in the token's company schema
    (see :func:`verify_token` → ``payload['s']``)."""
    data = verify_token(token)
    row, created, info = acknowledge(
        db,
        supplier_name=str(data["n"]),
        supplier_po_no=str(data.get("p") or "") or None,
        po_ref=str(data.get("r") or "") or None,
        record_id=data.get("i") if isinstance(data.get("i"), int) else None,
        via="link",
        ip=ip,
        user_agent=user_agent,
        now=now,
    )
    return {
        "found": row is not None,
        "created": created,
        "supplier_name": info["supplier_name"],
        "po_ref": info["display_ref"],
        **ack_out(row),
    }


def status_by_token(db: Session, token: str) -> dict[str, Any]:
    data = verify_token(token)
    anchor, _records, ref = resolve_po(
        db,
        supplier_name=str(data["n"]),
        supplier_po_no=str(data.get("p") or "") or None,
        po_ref=str(data.get("r") or "") or None,
        record_id=data.get("i") if isinstance(data.get("i"), int) else None,
    )
    name = anchor.supplier_name if anchor else str(data["n"])
    counter = anchor.supplier_po_no if anchor else (data.get("p") or None)
    row = find_ack(db, name, counter, ref) if anchor else None
    return {
        "found": anchor is not None,
        "supplier_name": name,
        "po_ref": ref or counter,
        **ack_out(row),
    }

"""PO follow-up mail generation and automatic queueing."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from html import escape
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.config import settings
from ..models.mail_history import MailHistory
from ..models.procurement import ProcurementRecord
from . import communication_message_service as msg_service
from . import po_followup_service
from .followup_engine import apply_followup_logic
from .mail_template_service import (
    PO_MAIL_TYPE_BY_SIGNAL,
    PO_REPLY_INSTRUCTIONS,
    build_po_group_context,
    pick_po_template,
    render,
    render_po_materials_table_html,
    render_po_reply_table_html,
)

TYPE_LABELS_PO = {
    "PO_FOLLOWUP_GREEN": "PO Follow-up",
    "PO_FOLLOWUP_YELLOW": "PO Reminder",
    "PO_FOLLOWUP_RED": "Urgent PO Follow-up",
    "PO_FOLLOWUP_BLACK": "Critical PO Escalation",
    "PO_FOLLOWUP_GROUP": "PO Follow-up",
}

ACTIVE_AUTO_STATUSES = {"READY", "SENT", "FAILED"}


@dataclass(frozen=True)
class PoMailQueueResult:
    created: bool
    reused_existing: bool = False
    skipped_reason: str | None = None
    history_id: int | None = None
    message_id: int | None = None
    procurement_record_id: int | None = None
    supplier_name: str | None = None
    supplier_po_no: str | None = None
    mail_type: str | None = None
    overall_signal: str | None = None
    material_count: int = 0
    to_emails: list[str] | None = None
    cc_emails: list[str] | None = None
    bcc_emails: list[str] | None = None
    escalation_emails: list[str] | None = None
    subject: str | None = None
    body: str | None = None
    body_html: str | None = None
    materials: list[dict[str, Any]] | None = None
    notes: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "created": self.created,
            "reused_existing": self.reused_existing,
            "skipped_reason": self.skipped_reason,
            "history_id": self.history_id,
            "message_id": self.message_id,
            "procurement_record_id": self.procurement_record_id,
            "supplier_name": self.supplier_name,
            "supplier_po_no": self.supplier_po_no,
            "mail_type": self.mail_type,
            "overall_signal": self.overall_signal,
            "material_count": self.material_count,
            "to_emails": self.to_emails or [],
            "cc_emails": self.cc_emails or [],
            "bcc_emails": self.bcc_emails or [],
            "escalation_emails": self.escalation_emails or [],
            "subject": self.subject,
            "body": self.body,
            "body_html": self.body_html,
            "materials": self.materials or [],
            "notes": self.notes,
        }


def _po_subject(mail_type: str, supplier_name: str | None, po_no: str, count: int) -> str:
    label = TYPE_LABELS_PO.get(mail_type, "PO Follow-up")
    return f"{label} | PO No. {po_no} | {count} material(s) | {supplier_name or ''}".strip()


def _po_fallback_body(group: dict[str, Any], table_text: str) -> str:
    return (
        f"Dear {group.get('supplier_name') or 'Supplier'},\n\n"
        f"Status update is required for PO No. {group.get('supplier_po_no')}.\n"
        f"Overall signal: {group.get('overall_signal')}.\n"
        f"Earliest required dispatch: {group.get('earliest_due_date') or '-'}.\n\n"
        "Material-wise summary:\n"
        f"{table_text}\n\n"
        f"{PO_REPLY_INSTRUCTIONS}\n\n"
        "Regards,\nProcurement"
    )


def _po_body_html(group: dict[str, Any], table_html: str, reply_table_html: str | None = None) -> str:
    supplier = escape(str(group.get("supplier_name") or "Supplier"))
    po_no = escape(str(group.get("supplier_po_no") or "-"))
    count = escape(str(group.get("material_count") or 0))
    signal = escape(str(group.get("overall_signal") or "GREEN"))
    due = escape(str(group.get("earliest_due_date") or "-"))
    signal_bg = {
        "GREEN": "#dcfce7",
        "YELLOW": "#fef9c3",
        "RED": "#fee2e2",
        "BLACK": "#111827",
    }.get(signal.upper(), "#e2e8f0")
    signal_fg = "#f9fafb" if signal.upper() == "BLACK" else "#0f172a"

    reply_block = ""
    if reply_table_html:
        reply_block = (
            "<p style=\"margin:16px 0 4px;font-weight:600;color:#0f172a;\">"
            "Please reply using this table (one row per material):</p>"
            f"{reply_table_html}"
            "<p style=\"font-size:12px;color:#475569;margin:6px 0 0;\">"
            "Allowed status values: CONFIRMED, DELAYED, PARTIAL, DISPATCHED, ON_HOLD, CANCELLED.</p>"
        )

    return (
        "<div style=\"background:#f1f5f9;padding:18px;font-family:Arial,Helvetica,sans-serif;\">"
        "<div style=\"max-width:760px;margin:0 auto;background:#ffffff;border:1px solid #e2e8f0;"
        "border-radius:10px;overflow:hidden;\">"
        # Header bar
        "<div style=\"background:#0f172a;padding:14px 20px;\">"
        "<span style=\"color:#ffffff;font-size:16px;font-weight:700;\">Procurement Follow-up</span>"
        "</div>"
        "<div style=\"padding:20px;color:#1e293b;font-size:13px;line-height:1.5;\">"
        f"<p style=\"margin:0 0 12px;\">Dear {supplier},</p>"
        "<p style=\"margin:0 0 14px;\">We request a material-wise status update for the "
        "following purchase order. Kindly review the summary and reply using the table provided.</p>"
        # PO summary card
        "<table role=\"presentation\" style=\"border-collapse:collapse;width:100%;margin:0 0 16px;\">"
        "<tr>"
        "<td style=\"background:#f8fafc;border:1px solid #e2e8f0;padding:10px 12px;font-size:12px;\">"
        f"<div style=\"color:#64748b;\">PO Number</div><div style=\"font-weight:700;font-size:14px;\">{po_no}</div>"
        "</td>"
        "<td style=\"background:#f8fafc;border:1px solid #e2e8f0;padding:10px 12px;font-size:12px;\">"
        f"<div style=\"color:#64748b;\">Materials</div><div style=\"font-weight:700;font-size:14px;\">{count}</div>"
        "</td>"
        "<td style=\"background:#f8fafc;border:1px solid #e2e8f0;padding:10px 12px;font-size:12px;\">"
        f"<div style=\"color:#64748b;\">Earliest Due</div><div style=\"font-weight:700;font-size:14px;\">{due}</div>"
        "</td>"
        "<td style=\"background:#f8fafc;border:1px solid #e2e8f0;padding:10px 12px;font-size:12px;\">"
        f"<div style=\"color:#64748b;\">Risk Signal</div>"
        f"<div><span style=\"display:inline-block;padding:2px 10px;border-radius:9999px;"
        f"background:{signal_bg};color:{signal_fg};font-weight:700;font-size:12px;\">{signal}</span></div>"
        "</td>"
        "</tr></table>"
        # Material summary table
        "<p style=\"margin:0 0 4px;font-weight:600;color:#0f172a;\">Material-wise summary</p>"
        f"{table_html}"
        # Reply table
        f"{reply_block}"
        # Footer
        "<p style=\"margin:18px 0 0;\">Regards,<br/><strong>Procurement Team</strong></p>"
        "</div>"
        "<div style=\"background:#f8fafc;border-top:1px solid #e2e8f0;padding:10px 20px;"
        "font-size:11px;color:#94a3b8;\">This is an automated follow-up from the Supplier "
        "Follow-up Agent. Please reply keeping the table format intact.</div>"
        "</div></div>"
    )


def _active_window_start() -> datetime:
    return datetime.combine(date.today(), datetime.min.time())


def find_active_po_mail(
    db: Session,
    *,
    supplier_name: str | None,
    supplier_po_no: str,
    mail_type: str,
) -> MailHistory | None:
    stmt = (
        select(MailHistory)
        .where(
            MailHistory.supplier_po_no == supplier_po_no.strip(),
            MailHistory.mail_type == mail_type,
            MailHistory.sent_status.in_(ACTIVE_AUTO_STATUSES),
            MailHistory.created_at >= _active_window_start(),
        )
        .order_by(MailHistory.created_at.desc())
    )
    if supplier_name:
        stmt = stmt.where(
            func.upper(MailHistory.supplier_name) == supplier_name.strip().upper()
        )
    return db.scalar(stmt)


def _queue_history_for_auto_send(db: Session, history: MailHistory):
    return msg_service.queue_outgoing_message(
        db,
        supplier_id=history.supplier_id,
        supplier_name=history.supplier_name,
        procurement_record_id=history.procurement_record_id,
        supplier_po_no=history.supplier_po_no,
        subject=history.subject,
        body=history.body,
        body_html=history.body_html,
        to_emails=history.to_emails or [],
        cc_emails=history.cc_emails or [],
        bcc_emails=history.bcc_emails or [],
        mail_type=history.mail_type,
        mail_history_id=history.id,
        commit=False,
    )


def result_from_history(
    *,
    history: MailHistory,
    group: dict[str, Any],
    reused_existing: bool,
    notes: str | None = None,
) -> PoMailQueueResult:
    table_html = render_po_materials_table_html(group.get("materials") or [])
    reply_table_html = render_po_reply_table_html(group.get("materials") or [])
    return PoMailQueueResult(
        created=False,
        reused_existing=reused_existing,
        history_id=history.id,
        procurement_record_id=history.procurement_record_id,
        supplier_name=history.supplier_name,
        supplier_po_no=history.supplier_po_no,
        mail_type=history.mail_type,
        overall_signal=group.get("overall_signal"),
        material_count=group.get("material_count") or 0,
        to_emails=history.to_emails or [],
        cc_emails=history.cc_emails or [],
        bcc_emails=history.bcc_emails or [],
        escalation_emails=history.escalation_emails or [],
        subject=history.subject,
        body=history.body,
        body_html=history.body_html or _po_body_html(group, table_html, reply_table_html),
        materials=group.get("materials") or [],
        notes=notes,
    )


def create_po_followup_mail(
    db: Session,
    *,
    supplier_name: str,
    supplier_po_no: str,
    mail_type: str | None = None,
    force_new: bool = False,
    require_mapping: bool = False,
    commit: bool = True,
) -> PoMailQueueResult:
    group = po_followup_service.get_po_group(db, supplier_name, supplier_po_no)
    if not group:
        return PoMailQueueResult(
            created=False,
            skipped_reason="PO group not found",
            supplier_name=supplier_name,
            supplier_po_no=supplier_po_no,
        )

    resolved_mail_type = mail_type or PO_MAIL_TYPE_BY_SIGNAL.get(
        group["overall_signal"], "PO_FOLLOWUP_GROUP"
    )

    if require_mapping and not group.get("mapping_active"):
        return PoMailQueueResult(
            created=False,
            skipped_reason="No active supplier email mapping",
            supplier_name=group.get("supplier_name"),
            supplier_po_no=group.get("supplier_po_no"),
            mail_type=resolved_mail_type,
            overall_signal=group.get("overall_signal"),
            material_count=group.get("material_count") or 0,
        )

    if not force_new:
        existing = po_followup_service.find_today_draft(
            db,
            supplier_name=group.get("supplier_name"),
            supplier_po_no=group["supplier_po_no"],
            mail_type=resolved_mail_type,
        )
        if existing:
            return result_from_history(
                history=existing,
                group=group,
                reused_existing=True,
                notes="Existing mail from today reused.",
            )

    ctx = build_po_group_context(group)
    template = pick_po_template(db, group["overall_signal"])

    table_html = ctx["materials_table_html"]
    table_text = ctx["materials_table_text"]
    reply_table_html = ctx["reply_table_html"]
    body_plain = (
        render(template.body_template, ctx)
        if template and template.body_template
        else _po_fallback_body(group, table_text)
    )
    subject = (
        render(template.subject_template, ctx)
        if template and template.subject_template
        else _po_subject(
            resolved_mail_type,
            group.get("supplier_name"),
            group["supplier_po_no"],
            group["material_count"],
        )
    )
    body_html = _po_body_html(group, table_html, reply_table_html)

    anchor_id = group["anchor_record_id"]
    anchor_rec = db.get(ProcurementRecord, anchor_id)
    if anchor_rec is None:
        return PoMailQueueResult(
            created=False,
            skipped_reason="Anchor procurement record missing",
            supplier_name=group.get("supplier_name"),
            supplier_po_no=group.get("supplier_po_no"),
            mail_type=resolved_mail_type,
            overall_signal=group.get("overall_signal"),
        )

    history = MailHistory(
        procurement_record_id=anchor_id,
        supplier_id=group.get("supplier_id"),
        supplier_name=group.get("supplier_name"),
        supplier_po_no=group["supplier_po_no"],
        material_name=f"ALL MATERIALS ({group['material_count']})",
        to_emails=group.get("to_emails") or [],
        cc_emails=group.get("cc_emails") or [],
        bcc_emails=group.get("bcc_emails") or [],
        escalation_emails=group.get("escalation_emails") or [],
        subject=subject,
        body=body_plain,
        body_html=body_html,
        mail_type=resolved_mail_type,
        sent_status="READY",
    )
    db.add(history)
    db.flush()
    msg = _queue_history_for_auto_send(db, history)

    for rid in group["procurement_record_ids"]:
        rec = db.get(ProcurementRecord, rid)
        if rec:
            rec.mail_status = "READY"

    if commit:
        db.commit()
        db.refresh(history)

    notes = None
    if not group.get("mapping_active"):
        notes = (
            f"No active email mapping found for '{group.get('supplier_name')}'. "
            "Please add one in Email Master."
        )

    return PoMailQueueResult(
        created=True,
        history_id=history.id,
        message_id=getattr(msg, "id", None),
        procurement_record_id=anchor_id,
        supplier_name=group.get("supplier_name"),
        supplier_po_no=group["supplier_po_no"],
        mail_type=resolved_mail_type,
        overall_signal=group["overall_signal"],
        material_count=group["material_count"],
        to_emails=group.get("to_emails") or [],
        cc_emails=group.get("cc_emails") or [],
        bcc_emails=group.get("bcc_emails") or [],
        escalation_emails=group.get("escalation_emails") or [],
        subject=subject,
        body=body_plain,
        body_html=body_html,
        materials=group["materials"],
        notes=notes,
    )


def _record_due_for_auto_mail(rec: ProcurementRecord, now: datetime) -> bool:
    if (rec.mail_status or "").upper() == "READY":
        return False
    if (rec.mail_status or "").upper() == "SENT":
        # No next date scheduled -> treat as due so critical POs don't freeze.
        if rec.next_followup_date is None:
            return True
        return rec.next_followup_date <= now
    if rec.next_followup_date is not None and rec.next_followup_date > now:
        return False
    return True


def queue_due_po_followups(
    db: Session,
    *,
    limit: int = 50,
    dry_run: bool = False,
) -> dict[str, Any]:
    if not getattr(settings, "AUTO_PO_FOLLOWUP_ENABLED", False):
        return {"enabled": False, "queued": 0, "skipped": 0, "results": []}

    now = datetime.utcnow()
    records = db.scalars(
        select(ProcurementRecord)
        .where(ProcurementRecord.supplier_po_no.isnot(None))
        .order_by(ProcurementRecord.supplier_name.asc(), ProcurementRecord.supplier_po_no.asc())
    ).all()

    buckets: dict[tuple[str, str], list[ProcurementRecord]] = {}
    for rec in records:
        if not rec.supplier_po_no:
            continue
        key = ((rec.supplier_name or "").strip().upper(), rec.supplier_po_no.strip())
        buckets.setdefault(key, []).append(rec)

    results: list[dict[str, Any]] = []
    queued = 0
    skipped = 0

    for (_, _), group_records in buckets.items():
        if queued >= limit:
            break

        due_records = [rec for rec in group_records if _record_due_for_auto_mail(rec, now)]
        first = group_records[0]
        if not due_records:
            skipped += 1
            results.append({
                "created": False,
                "supplier_name": first.supplier_name,
                "supplier_po_no": first.supplier_po_no,
                "skipped_reason": "No due records",
            })
            continue

        for rec in group_records:
            apply_followup_logic(rec, db=db)

        group = po_followup_service.build_po_group_payload(
            db,
            group_records,
            first.supplier_name,
            first.supplier_po_no,
        )
        mail_type = PO_MAIL_TYPE_BY_SIGNAL.get(group["overall_signal"], "PO_FOLLOWUP_GROUP")
        if not group.get("supplier_name"):
            skipped += 1
            results.append({
                "created": False,
                "supplier_name": group.get("supplier_name"),
                "supplier_po_no": group.get("supplier_po_no"),
                "mail_type": mail_type,
                "overall_signal": group.get("overall_signal"),
                "skipped_reason": "Supplier name missing",
            })
            continue
        if not group.get("mapping_active"):
            skipped += 1
            results.append({
                "created": False,
                "supplier_name": group.get("supplier_name"),
                "supplier_po_no": group.get("supplier_po_no"),
                "mail_type": mail_type,
                "overall_signal": group.get("overall_signal"),
                "skipped_reason": "No active supplier email mapping",
            })
            continue
        existing = find_active_po_mail(
            db,
            supplier_name=group.get("supplier_name"),
            supplier_po_no=group["supplier_po_no"],
            mail_type=mail_type,
        )
        if existing:
            skipped += 1
            results.append({
                "created": False,
                "supplier_name": group.get("supplier_name"),
                "supplier_po_no": group.get("supplier_po_no"),
                "mail_type": mail_type,
                "overall_signal": group.get("overall_signal"),
                "history_id": existing.id,
                "skipped_reason": f"Existing {existing.sent_status} mail in active window",
            })
            continue

        if dry_run:
            queued += 1
            results.append({
                "created": False,
                "dry_run": True,
                "supplier_name": group.get("supplier_name"),
                "supplier_po_no": group.get("supplier_po_no"),
                "mail_type": mail_type,
                "overall_signal": group.get("overall_signal"),
                "material_count": group.get("material_count") or 0,
            })
            continue

        result = create_po_followup_mail(
            db,
            supplier_name=group["supplier_name"],
            supplier_po_no=group["supplier_po_no"],
            mail_type=mail_type,
            require_mapping=True,
            commit=False,
        )
        if result.created:
            queued += 1
        else:
            skipped += 1
        results.append(result.as_dict())

    if dry_run:
        db.rollback()
    else:
        db.commit()

    return {
        "enabled": True,
        "queued": queued,
        "skipped": skipped,
        "dry_run": dry_run,
        "ran_at": now.isoformat(),
        "results": results,
    }

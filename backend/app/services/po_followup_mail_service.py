"""PO follow-up mail generation and automatic queueing."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from html import escape
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.config import settings
from ..models.mail_history import MailHistory
from ..models.procurement import ProcurementRecord
from . import ai_service, brand_email, communication_message_service as msg_service
from . import embeddings_service, followup_audit_service, po_followup_service, vector_store
from .followup_engine import apply_followup_logic

log = logging.getLogger(__name__)
from .mail_template_service import (
    PO_MAIL_TYPE_BY_SIGNAL,
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


def _portal_po_url(po_no: str | None) -> str | None:
    """Deep link to the supplier portal PO page (commitment form)."""
    base = (settings.APP_BASE_URL or "").strip().rstrip("/")
    if not base or not po_no:
        return None
    from urllib.parse import quote

    return f"{base}/portal/pos/{quote(str(po_no))}"


def _commitment_instruction_text(po_no: str | None) -> str:
    url = _portal_po_url(po_no)
    if url:
        return (
            "Please provide a committed dispatch date for each material in the "
            f"supplier portal:\n{url}"
        )
    return (
        "Please log in to the supplier portal and provide a committed dispatch "
        "date for each material."
    )


def _po_fallback_body(group: dict[str, Any], table_text: str) -> str:
    return (
        f"Dear {group.get('supplier_name') or 'Supplier'},\n\n"
        f"Status update is required for PO No. {group.get('supplier_po_no')}.\n"
        f"Overall signal: {group.get('overall_signal')}.\n"
        f"Earliest required dispatch: {group.get('earliest_due_date') or '-'}.\n\n"
        "Material-wise summary:\n"
        f"{table_text}\n\n"
        f"{_commitment_instruction_text(group.get('supplier_po_no'))}\n\n"
        "Regards,\nProcurement"
    )


def _po_body_html(
    group: dict[str, Any],
    table_html: str,
    reply_table_html: str | None = None,
    intro_html: str | None = None,
) -> str:
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

    # New flow: instead of asking the supplier to reply with a table, send them
    # to the portal commitment form via a clear call-to-action button.
    commit_url = _portal_po_url(group.get("supplier_po_no"))
    if commit_url:
        reply_block = (
            "<div style=\"margin:18px 0 4px;text-align:center;\">"
            f"<a href=\"{escape(commit_url)}\" style=\"display:inline-block;background:#E11D2E;"
            "color:#ffffff;text-decoration:none;padding:11px 22px;border-radius:8px;"
            "font-weight:700;font-size:14px;\">Provide / update commitment dates</a>"
            "<p style=\"font-size:12px;color:#475569;margin:8px 0 0;\">"
            "Open the secure supplier portal to enter a committed dispatch date for "
            "each material on this PO.</p></div>"
        )
    else:
        reply_block = (
            "<p style=\"margin:16px 0 4px;font-weight:600;color:#B01624;\">"
            "Please log in to the supplier portal to provide a committed dispatch "
            "date for each material.</p>"
        )

    inner = (
        brand_email.header_html("Procurement Follow-up")
        + "<div style=\"padding:20px;color:#1f2937;font-size:13px;line-height:1.5;\">"
        + (
            intro_html
            or (
                f"<p style=\"margin:0 0 12px;\">Dear {supplier},</p>"
                "<p style=\"margin:0 0 14px;\">We request a material-wise status update for the "
                "following purchase order. Kindly review the summary below and enter a committed "
                "dispatch date for each material using the button provided.</p>"
            )
        )
        +
        # PO summary card
        "<table role=\"presentation\" style=\"border-collapse:collapse;width:100%;margin:0 0 16px;\">"
        "<tr>"
        "<td style=\"background:#fff5f6;border:1px solid #f4d6da;padding:10px 12px;font-size:12px;\">"
        f"<div style=\"color:#9b6b70;\">PO Number</div><div style=\"font-weight:700;font-size:14px;color:#1f2937;\">{po_no}</div>"
        "</td>"
        "<td style=\"background:#fff5f6;border:1px solid #f4d6da;padding:10px 12px;font-size:12px;\">"
        f"<div style=\"color:#9b6b70;\">Materials</div><div style=\"font-weight:700;font-size:14px;color:#1f2937;\">{count}</div>"
        "</td>"
        "<td style=\"background:#fff5f6;border:1px solid #f4d6da;padding:10px 12px;font-size:12px;\">"
        f"<div style=\"color:#9b6b70;\">Earliest Due</div><div style=\"font-weight:700;font-size:14px;color:#1f2937;\">{due}</div>"
        "</td>"
        "<td style=\"background:#fff5f6;border:1px solid #f4d6da;padding:10px 12px;font-size:12px;\">"
        f"<div style=\"color:#9b6b70;\">Risk Signal</div>"
        f"<div><span style=\"display:inline-block;padding:2px 10px;border-radius:9999px;"
        f"background:{signal_bg};color:{signal_fg};font-weight:700;font-size:12px;\">{signal}</span></div>"
        "</td>"
        "</tr></table>"
        # Material summary table
        "<p style=\"margin:0 0 4px;font-weight:600;color:#B01624;\">Material-wise summary</p>"
        f"{table_html}"
        # Reply table
        f"{reply_block}"
        # Footer
        "<p style=\"margin:18px 0 0;\">Regards,<br/><strong>Procurement Team</strong></p>"
        "</div>"
        + brand_email.footer_html(
            "This is an automated follow-up from Harmony × Hariom. "
            "Please use the button above to provide your commitment dates in the portal."
        )
    )
    return brand_email.shell(inner, max_width=760)


def _ai_intro_html(text: str) -> str:
    """Turn an AI-written plain-text body into HTML paragraphs for the intro slot."""
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text.strip()) if b.strip()]
    return "".join(
        f'<p style="margin:0 0 12px;">{escape(b).replace(chr(10), "<br/>")}</p>'
        for b in blocks
    )


def _supplier_precedent(db: Session, supplier_name: str | None) -> str | None:
    """RAG: pull how this supplier previously responded to follow-ups (if RAG on)."""
    if not supplier_name or not (embeddings_service.is_enabled() and vector_store.available()):
        return None
    try:
        emb = embeddings_service.embed_query(
            f"follow-up reply from {supplier_name} about delivery delay or dispatch date"
        )
        hits = vector_store.search(db, embedding=emb, k=3, source_types=["supplier_reply"])
        snippets = [
            h["content"]
            for h in hits
            if (h.get("metadata") or {}).get("supplier_name", "").upper()
            == supplier_name.upper()
        ]
        return "\n---\n".join(snippets[:2]) if snippets else None
    except Exception:  # noqa: BLE001
        log.exception("supplier precedent lookup failed")
        return None


def _ai_followup_narrative(
    db: Session,
    group: dict[str, Any],
    anchor_rec: ProcurementRecord | None,
    materials_summary: str,
    instruction: str | None = None,
) -> tuple[str | None, str | None]:
    """The LLM's PROSE follow-up body only (no table — that's added as HTML).

    Returns (narrative, ai_error). narrative is None when AI is disabled or fails;
    ai_error is the error string only when AI was attempted and errored.
    """
    if not ai_service.any_enabled():
        return None, None
    try:
        due = group.get("earliest_due_date")
        days_late: int | None = None
        if due:
            try:
                days_late = (date.today() - datetime.fromisoformat(due).date()).days
            except ValueError:
                days_late = None
        body = ai_service.suggest_po_followup(
            supplier_name=group.get("supplier_name"),
            supplier_po_no=group.get("supplier_po_no"),
            overall_signal=group.get("overall_signal"),
            days_late=days_late,
            followup_count=getattr(anchor_rec, "followup_count", None),
            materials_summary=materials_summary,
            earliest_due_date=due,
            last_supplier_reply=getattr(anchor_rec, "last_supplier_reply", None),
            precedent=_supplier_precedent(db, group.get("supplier_name")),
            instruction=instruction,
            background=True,  # auto-followup worker → flex tier on the OpenAI backup
        )
        return (body.strip() if body and body.strip() else None), None
    except Exception as exc:  # noqa: BLE001
        log.exception("AI PO follow-up draft failed; using template")
        return None, str(exc)


def _maybe_ai_polish(
    db: Session,
    group: dict[str, Any],
    anchor_rec: ProcurementRecord | None,
    table_text: str,
    instruction: str | None = None,
) -> tuple[tuple[str, str] | None, str | None]:
    """Return ((plain_body, intro_html) | None, ai_error). None keeps the template.

    The LLM supplies only the prose; the material table (text + HTML) is appended
    by us, so the email always has a clean, structured table — never the model's
    own markdown.
    """
    narrative, ai_error = _ai_followup_narrative(db, group, anchor_rec, table_text, instruction)
    if not narrative:
        return None, ai_error
    plain = f"{narrative}\n\n{table_text}\n\n{_commitment_instruction_text(group.get('supplier_po_no'))}"
    return (plain, _ai_intro_html(narrative)), ai_error


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
    instruction: str | None = None,
    source: str = "manual",
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
        followup_audit_service.record_safe(
            db,
            supplier_po_no=group.get("supplier_po_no"),
            supplier_name=group.get("supplier_name"),
            signal=group.get("overall_signal"),
            mail_type=resolved_mail_type,
            source=source,
            outcome="SKIPPED",
            detail="No active supplier email mapping",
            commit=commit,
        )
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

    # AI-polish when (a) the user gave an explicit instruction/command, or
    # (b) it's a high-risk RED/BLACK follow-up and AI polishing is enabled.
    # Keeps the structured material + reply tables; replaces the intro/tone.
    ai_used = False
    ai_error: str | None = None
    if (instruction and instruction.strip()) or (
        getattr(settings, "AI_PO_FOLLOWUP_ENABLED", False)
        and (group.get("overall_signal") or "").upper() in {"RED", "BLACK"}
    ):
        polished, ai_error = _maybe_ai_polish(db, group, anchor_rec, table_text, instruction=instruction)
        if polished:
            body_plain, intro_html = polished
            body_html = _po_body_html(group, table_html, reply_table_html, intro_html=intro_html)
            ai_used = True

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

    followup_audit_service.record_safe(
        db,
        supplier_po_no=group["supplier_po_no"],
        supplier_name=group.get("supplier_name"),
        signal=group.get("overall_signal"),
        mail_type=resolved_mail_type,
        source=source,
        outcome="QUEUED",
        detail=None if group.get("mapping_active") else "No active email mapping",
        ai_used=ai_used,
        ai_error=ai_error,
        history_id=history.id,
        message_id=getattr(msg, "id", None),
        commit=False,
    )

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

        # Chase until commitment: keep auto-following-up while any material is
        # still missing a committed dispatch date; once EVERY material on the PO
        # has a commitment date, stop chasing this PO.
        materials = group.get("materials") or []
        if materials and all((m.get("commitment") or {}).get("commitment_date") for m in materials):
            skipped += 1
            results.append({
                "created": False,
                "supplier_name": group.get("supplier_name"),
                "supplier_po_no": group.get("supplier_po_no"),
                "mail_type": mail_type,
                "overall_signal": group.get("overall_signal"),
                "skipped_reason": "Commitment date captured — follow-up stopped",
            })
            continue

        if not group.get("supplier_name"):
            skipped += 1
            followup_audit_service.record_safe(
                db, supplier_po_no=group.get("supplier_po_no"), supplier_name=None,
                signal=group.get("overall_signal"), mail_type=mail_type, source="auto",
                outcome="SKIPPED", detail="Supplier name missing", commit=False,
            )
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
            followup_audit_service.record_safe(
                db, supplier_po_no=group.get("supplier_po_no"),
                supplier_name=group.get("supplier_name"), signal=group.get("overall_signal"),
                mail_type=mail_type, source="auto", outcome="SKIPPED",
                detail="No active supplier email mapping", commit=False,
            )
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

        try:
            result = create_po_followup_mail(
                db,
                supplier_name=group["supplier_name"],
                supplier_po_no=group["supplier_po_no"],
                mail_type=mail_type,
                require_mapping=True,
                commit=False,
                source="auto",
            )
        except Exception as exc:  # noqa: BLE001 — record the failure, keep the run going
            log.exception("PO follow-up generation failed for %s", group.get("supplier_po_no"))
            db.rollback()
            followup_audit_service.record_safe(
                db,
                supplier_po_no=group.get("supplier_po_no"),
                supplier_name=group.get("supplier_name"),
                signal=group.get("overall_signal"),
                mail_type=mail_type,
                source="auto",
                outcome="FAILED",
                detail=str(exc)[:1000],
                commit=True,
            )
            skipped += 1
            results.append({
                "created": False,
                "supplier_name": group.get("supplier_name"),
                "supplier_po_no": group.get("supplier_po_no"),
                "mail_type": mail_type,
                "overall_signal": group.get("overall_signal"),
                "skipped_reason": f"error: {exc}",
            })
            continue
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


def command_followup(
    db: Session,
    *,
    supplier_po_no: str,
    instruction: str,
    send: bool = False,
) -> dict[str, Any]:
    """Generate (and optionally send) an AI follow-up for a PO from a free-text
    user command (e.g. "also ask for a firm dispatch date by Friday").

    Preview by default (no DB writes); `send=True` queues the mail and sends it
    immediately to the mapped supplier address.
    """
    po = (supplier_po_no or "").strip()
    rec = db.scalar(
        select(ProcurementRecord)
        .where(ProcurementRecord.supplier_po_no == po)
        .order_by(ProcurementRecord.created_at.desc())
    )
    if rec is None:
        return {"found": False, "error": "PO not found"}
    supplier_name = rec.supplier_name or ""
    group = po_followup_service.get_po_group(db, supplier_name, po)
    if not group:
        return {"found": False, "error": "PO group not found"}

    mail_type = PO_MAIL_TYPE_BY_SIGNAL.get(group["overall_signal"], "PO_FOLLOWUP_GROUP")
    subject = _po_subject(
        mail_type, group.get("supplier_name"), group["supplier_po_no"], group["material_count"]
    )

    if send:
        result = create_po_followup_mail(
            db,
            supplier_name=group["supplier_name"],
            supplier_po_no=group["supplier_po_no"],
            force_new=True,
            require_mapping=True,
            commit=True,
            instruction=instruction,
            source="command",
        )
        sent = False
        if result.created and result.message_id is not None:
            from ..workers import mail_send_worker  # local import avoids import cycle

            send_res = mail_send_worker.send_message_now(db, result.message_id)
            sent = bool(send_res.get("sent"))
        return {
            "found": True,
            "sent": sent,
            "queued": bool(result.created and not sent),
            "subject": result.subject or subject,
            "body": result.body or "",
            "body_html": result.body_html or "",
            "source": "ai" if ai_service.any_enabled() else "template",
            "mapping_active": group.get("mapping_active"),
            "skipped_reason": result.skipped_reason,
            "message_id": result.message_id,
        }

    # Preview only — no DB writes. Return the clean prose AND the rendered HTML so
    # the UI shows exactly what the supplier will receive (branded layout + table).
    ctx = build_po_group_context(group)
    table_text = ctx["materials_table_text"]
    table_html = ctx["materials_table_html"]
    reply_table_html = ctx["reply_table_html"]
    anchor_rec = db.get(ProcurementRecord, group["anchor_record_id"])
    narrative, _ai_err = _ai_followup_narrative(db, group, anchor_rec, table_text, instruction=instruction)
    source = "ai" if narrative else "template"
    if not narrative:
        narrative = (
            f"Dear {group.get('supplier_name') or 'Supplier'},\n\n"
            f"We require an urgent dispatch status update for PO No. {group['supplier_po_no']}. "
            "Kindly review the material summary below and provide your committed dispatch "
            "dates in the supplier portal.\n\n"
            "Regards,\nProcurement Team"
        )
    body_html = _po_body_html(group, table_html, reply_table_html, intro_html=_ai_intro_html(narrative))
    return {
        "found": True,
        "sent": False,
        "subject": subject,
        "body": narrative,
        "body_html": body_html,
        "source": source,
        "mapping_active": group.get("mapping_active"),
    }

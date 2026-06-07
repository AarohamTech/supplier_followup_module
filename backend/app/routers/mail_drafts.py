import base64
import html
import os
import platform
import shutil
import subprocess

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.mail_history import MailHistory
from ..models.procurement import ProcurementRecord
from ..models.supplier import SupplierMaster
from ..schemas.mail_draft import (
    MailDraftOut,
    OutlookComposeOut,
    OutlookComposeRequest,
    MailDraftPoOut,
    MailDraftPoRequest,
    MailDraftRequest,
)
from ..services import communication_message_service as msg_service
from ..services import po_followup_mail_service
from ..services.followup_engine import apply_followup_logic, get_followup_rule
from ..services.mail_template_service import (
    build_context,
    find_supplier_email,
    pick_template,
    render,
)

router = APIRouter(prefix="/api/mail-drafts", tags=["mail-drafts"])

TYPE_LABELS = {
    "GREEN_PO_RELEASE": "PO Acknowledgement",
    "YELLOW_REMINDER": "Reminder",
    "RED_DAY1": "Urgent Follow-up",
    "RED_DAY2": "Strong Follow-up",
    "AI_REQUIRED": "AI Follow-up",
    "BLACK_ESCALATION": "Critical Escalation",
}


def _subject(mail_type: str, rec: ProcurementRecord) -> str:
    type_label = TYPE_LABELS.get(mail_type, "Follow-up")
    return (
        f"{type_label} | PO No. {rec.supplier_po_no} | "
        f"{rec.material_name} | {rec.supplier_name or ''}"
    )


def _ai_body(rec: ProcurementRecord, action: str) -> str:
    return (
        f"Dear {rec.supplier_name or 'Supplier'},\n\n"
        f"{action} is required for PO No. {rec.supplier_po_no} / {rec.material_name}.\n"
        f"Signal: {rec.signal or '-'}\n"
        f"CRM No.: {rec.crm_no}\n"
        f"Qty: {rec.qty or '-'} {rec.uom or ''}\n"
        f"Shipment Date: {rec.shipment_date or '-'}\n\n"
        "Please share the current dispatch commitment, delay reason if any, "
        "and the earliest recoverable delivery date.\n\n"
        "Regards,\nProcurement"
    )


def _queue_history_for_auto_send(db: Session, history: MailHistory) -> None:
    msg_service.queue_outgoing_message(
        db,
        supplier_id=history.supplier_id,
        supplier_name=history.supplier_name,
        procurement_record_id=history.procurement_record_id,
        supplier_po_no=history.supplier_po_no,
        subject=history.subject,
        body=history.body,
        to_emails=history.to_emails or [],
        cc_emails=history.cc_emails or [],
        bcc_emails=history.bcc_emails or [],
        mail_type=history.mail_type,
        mail_history_id=history.id,
        commit=False,
    )


@router.post("/generate", response_model=MailDraftOut)
def generate_draft(payload: MailDraftRequest, db: Session = Depends(get_db)):
    rec = db.get(ProcurementRecord, payload.procurement_record_id)
    if not rec:
        raise HTTPException(404, "Procurement record not found")

    apply_followup_logic(rec)
    rule = get_followup_rule(rec)
    supplier = None
    if rec.supplier_name:
        supplier = db.scalar(
            select(SupplierMaster).where(SupplierMaster.supplier_name == rec.supplier_name)
        )
    mapping = find_supplier_email(db, rec.supplier_name)
    template = pick_template(db, rec)
    ctx = build_context(rec)

    notes = None
    if not mapping:
        notes = f"No active email mapping found for '{rec.supplier_name}'. Please add one in Email Master."

    body = render(template.body_template, ctx) if template else _ai_body(rec, rule.action)
    to_emails = mapping.to_emails if mapping else []
    cc_emails = mapping.cc_emails if mapping else []
    bcc_emails = mapping.bcc_emails if mapping else []
    escalation_emails = (
        mapping.escalation_emails
        if mapping and rule.escalation_level != "NONE"
        else []
    )
    subject = _subject(rule.mail_type, rec)

    history = MailHistory(
        procurement_record_id=rec.id,
        supplier_id=supplier.id if supplier else None,
        supplier_name=rec.supplier_name,
        supplier_po_no=rec.supplier_po_no,
        material_name=rec.material_name,
        to_emails=to_emails,
        cc_emails=cc_emails,
        bcc_emails=bcc_emails,
        escalation_emails=escalation_emails,
        subject=subject,
        body=body,
        mail_type=rule.mail_type,
        sent_status="READY",
    )
    rec.mail_status = "READY"
    db.add(history)
    db.flush()
    _queue_history_for_auto_send(db, history)
    db.commit()
    db.refresh(history)
    db.refresh(rec)

    return MailDraftOut(
        history_id=history.id,
        procurement_record_id=rec.id,
        to_emails=to_emails,
        cc_emails=cc_emails,
        bcc_emails=bcc_emails,
        escalation_emails=escalation_emails,
        subject=subject,
        body=body,
        mail_type=rule.mail_type,
        ai_required=rule.ai_required,
        notes=notes,
    )


def _b64(value: str) -> str:
    return base64.b64encode((value or "").encode("utf-8")).decode("ascii")


def _join_outlook(values: list[str]) -> str:
    seen: set[str] = set()
    items: list[str] = []
    for raw in values:
        val = (raw or "").strip()
        if not val:
            continue
        lower = val.lower()
        if lower in seen:
            continue
        seen.add(lower)
        items.append(val)
    return "; ".join(items)


def _html_from_text(body: str) -> str:
    escaped = html.escape(body or "")
    escaped = escaped.replace("\r\n", "\n").replace("\r", "\n")
    return (
        '<div style="font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#1e293b;white-space:pre-wrap;">'
        + escaped.replace("\n", "<br/>")
        + "</div>"
    )


def _resolve_powershell() -> str:
    candidates = [
        shutil.which("powershell.exe"),
        shutil.which("powershell"),
    ]
    system_root = os.environ.get("SystemRoot") or r"C:\Windows"
    candidates.extend(
        [
            os.path.join(system_root, "System32", "WindowsPowerShell", "v1.0", "powershell.exe"),
            os.path.join(system_root, "SysWOW64", "WindowsPowerShell", "v1.0", "powershell.exe"),
        ]
    )
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate
    raise HTTPException(500, "PowerShell is not available on this machine.")


def _open_outlook_compose(payload: OutlookComposeRequest) -> None:
    if platform.system() != "Windows":
        raise HTTPException(501, "Direct Outlook compose is available only on Windows.")

    powershell_exe = _resolve_powershell()

    to_value = _join_outlook(payload.to_emails)
    cc_value = _join_outlook([*(payload.cc_emails or []), *(payload.escalation_emails or [])])
    bcc_value = _join_outlook(payload.bcc_emails)
    html_body = payload.body_html or _html_from_text(payload.body)

    script = f"""
$ErrorActionPreference = 'Stop'
function Decode([string]$s) {{
    return [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($s))
}}
$outlook = New-Object -ComObject Outlook.Application
$mail = $outlook.CreateItem(0)
$mail.To = Decode('{_b64(to_value)}')
$mail.CC = Decode('{_b64(cc_value)}')
$mail.BCC = Decode('{_b64(bcc_value)}')
$mail.Subject = Decode('{_b64(payload.subject)}')
$mail.HTMLBody = Decode('{_b64(html_body)}')
$mail.Display()
Write-Output 'OUTLOOK_DRAFT_OPENED'
"""

    encoded_script = base64.b64encode(script.encode("utf-16le")).decode("ascii")

    try:
        result = subprocess.run(
            [
                powershell_exe,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-EncodedCommand",
                encoded_script,
            ],
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(504, "Timed out while opening Outlook draft.") from exc

    if result.returncode != 0 or "OUTLOOK_DRAFT_OPENED" not in (result.stdout or ""):
        detail = (result.stderr or result.stdout or "Unable to open Outlook draft.").strip()
        raise HTTPException(500, detail)


@router.post("/generate-po", response_model=MailDraftPoOut)
def generate_po_draft(payload: MailDraftPoRequest, db: Session = Depends(get_db)):
    result = po_followup_mail_service.create_po_followup_mail(
        db,
        supplier_name=payload.supplier_name,
        supplier_po_no=payload.supplier_po_no,
        mail_type=payload.mail_type,
        force_new=payload.force_new,
    )
    if result.skipped_reason:
        raise HTTPException(404, "No procurement records for this supplier + PO")

    return MailDraftPoOut(
        history_id=result.history_id or 0,
        procurement_record_id=result.procurement_record_id or 0,
        supplier_name=result.supplier_name,
        supplier_po_no=result.supplier_po_no or payload.supplier_po_no,
        to_emails=result.to_emails or [],
        cc_emails=result.cc_emails or [],
        bcc_emails=result.bcc_emails or [],
        escalation_emails=result.escalation_emails or [],
        subject=result.subject or "",
        body=result.body or "",
        body_html=result.body_html or "",
        mail_type=result.mail_type or "PO_FOLLOWUP_GROUP",
        overall_signal=result.overall_signal or "GREEN",
        material_count=result.material_count,
        materials=result.materials or [],
        reused_existing=result.reused_existing,
        notes=result.notes,
    )


@router.post("/open-outlook", response_model=OutlookComposeOut)
def open_outlook_draft(payload: OutlookComposeRequest, db: Session = Depends(get_db)):
    history = db.get(MailHistory, payload.history_id)
    if history is None:
        raise HTTPException(404, "Mail draft not found")

    _open_outlook_compose(payload)
    return OutlookComposeOut(ok=True, message="Outlook draft opened.")

"""Mail template service — picks correct template and renders it for a procurement record."""
from __future__ import annotations
from html import escape
from typing import Any, Optional
from jinja2 import Template
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.mail_template import MailTemplate
from ..models.supplier_email import SupplierEmail
from ..models.supplier import SupplierMaster
from ..models.procurement import ProcurementRecord
from .followup_engine import get_followup_rule, red_day_index


_PO_MATERIAL_COLUMNS: list[tuple[str, str]] = [
    ("Sr No", "sr"),
    ("CRM No", "crm_no"),
    ("Material Name", "material_name"),
    ("PO Qty", "po_qty"),
    ("UOM", "uom"),
    ("Due Date", "due_date"),
    ("Current Status", "current_status"),
    ("Last Commitment Date", "last_commitment_date"),
    ("Last Supplier Remark", "last_supplier_remark"),
]

PO_REPLY_INSTRUCTIONS = (
    "Please reply by filling the following columns for each material row "
    "(keep the table format intact):\n"
    "| CRM No | Material Name | Qty | Commitment Date (DD-MM-YYYY) | Remark | Status |\n"
    "Status values: CONFIRMED / DELAYED / PARTIAL / DISPATCHED / ON_HOLD / CANCELLED."
)

# Allowed supplier reply statuses and their email-safe colors.
PO_REPLY_STATUSES = (
    "CONFIRMED",
    "DELAYED",
    "PARTIAL",
    "DISPATCHED",
    "ON_HOLD",
    "CANCELLED",
)

_STATUS_COLORS: dict[str, tuple[str, str]] = {
    # status -> (background, text)
    "CONFIRMED": ("#dcfce7", "#166534"),
    "DISPATCHED": ("#dbeafe", "#1e40af"),
    "PARTIAL": ("#fef9c3", "#854d0e"),
    "DELAYED": ("#ffedd5", "#9a3412"),
    "ON_HOLD": ("#e2e8f0", "#334155"),
    "CANCELLED": ("#fee2e2", "#991b1b"),
    "GREEN": ("#dcfce7", "#166534"),
    "YELLOW": ("#fef9c3", "#854d0e"),
    "RED": ("#fee2e2", "#991b1b"),
    "BLACK": ("#111827", "#f9fafb"),
}

_REPLY_COLUMNS: list[str] = [
    "CRM No",
    "Material Name",
    "Qty",
    "Commitment Date",
    "Remark",
    "Status",
]


def _status_badge(value: Any) -> str:
    """Return an inline-styled colored badge for a status value."""
    text = "" if value is None else str(value).strip()
    if not text:
        return "-"
    bg, fg = _STATUS_COLORS.get(text.upper(), ("#f1f5f9", "#334155"))
    return (
        f"<span style=\"display:inline-block;padding:2px 8px;border-radius:9999px;"
        f"background:{bg};color:{fg};font-size:11px;font-weight:600;"
        f"white-space:nowrap;\">{escape(text)}</span>"
    )


def render(tpl: str, ctx: dict) -> str:
    return Template(tpl or "").render(**ctx)


def build_context(rec: ProcurementRecord) -> dict:
    return {
        "supplier_name": rec.supplier_name or "",
        "po_no": rec.supplier_po_no,
        "crm_no": rec.crm_no,
        "material_name": rec.material_name,
        "qty": rec.qty,
        "shipment_date": rec.shipment_date.strftime("%d-%m-%Y") if rec.shipment_date else "",
        "customer_name": "",
        "supplier_po_no": rec.supplier_po_no,
        "uom": rec.uom or "",
        "rate": rec.rate,
    }


def _cell(value: Any) -> str:
    if value is None or value == "":
        return "-"
    return escape(str(value))


def render_po_materials_table_html(materials: list[dict[str, Any]]) -> str:
    """Render a self-contained HTML table for the PO group materials.

    Email-client friendly inline styles, no external CSS.
    """
    if not materials:
        return "<p>No materials available for this PO.</p>"

    th_style = (
        "background:#f1f5f9;padding:6px 8px;border:1px solid #cbd5e1;"
        "text-align:left;font-weight:600;color:#0f172a;"
    )
    td_style = "padding:6px 8px;border:1px solid #e2e8f0;color:#1e293b;vertical-align:top;"
    table_style = (
        "border-collapse:collapse;width:100%;font-family:Arial,Helvetica,sans-serif;"
        "font-size:12px;margin:8px 0;"
    )

    head = "".join(f"<th style=\"{th_style}\">{escape(label)}</th>" for label, _ in _PO_MATERIAL_COLUMNS)
    rows_html: list[str] = []
    for idx, mat in enumerate(materials, start=1):
        commitment = mat.get("commitment") or {}
        row_data = {
            "sr": idx,
            "crm_no": mat.get("crm_no") or mat.get("material_code"),
            "material_name": mat.get("material_name"),
            "po_qty": mat.get("po_qty"),
            "uom": mat.get("uom"),
            "due_date": mat.get("due_date"),
            "current_status": mat.get("current_status") or mat.get("signal"),
            "last_commitment_date": commitment.get("commitment_date"),
            "last_supplier_remark": commitment.get("supplier_remark"),
        }
        zebra = "#ffffff" if idx % 2 else "#f8fafc"
        cells = []
        for _, key in _PO_MATERIAL_COLUMNS:
            value = row_data.get(key)
            if key == "current_status":
                inner = _status_badge(value)
            else:
                inner = _cell(value)
            cells.append(f"<td style=\"{td_style}background:{zebra};\">{inner}</td>")
        rows_html.append(f"<tr>{''.join(cells)}</tr>")

    return (
        f"<table role=\"presentation\" style=\"{table_style}\">"
        f"<thead><tr>{head}</tr></thead>"
        f"<tbody>{''.join(rows_html)}</tbody>"
        "</table>"
    )


def render_po_reply_table_html(materials: list[dict[str, Any]]) -> str:
    """Render the blank reply table the supplier should fill in (HTML)."""
    th_style = (
        "background:#eef2ff;padding:6px 8px;border:1px solid #c7d2fe;"
        "text-align:left;font-weight:600;color:#3730a3;"
    )
    td_style = "padding:6px 8px;border:1px solid #e2e8f0;color:#1e293b;vertical-align:top;"
    table_style = (
        "border-collapse:collapse;width:100%;font-family:Arial,Helvetica,sans-serif;"
        "font-size:12px;margin:8px 0;"
    )
    head = "".join(f"<th style=\"{th_style}\">{escape(label)}</th>" for label in _REPLY_COLUMNS)
    rows_html: list[str] = []
    for idx, mat in enumerate(materials or [], start=1):
        zebra = "#ffffff" if idx % 2 else "#f8fafc"
        prefill = {
            "CRM No": mat.get("crm_no") or mat.get("material_code"),
            "Material Name": mat.get("material_name"),
            "Qty": mat.get("po_qty"),
        }
        cells = []
        for label in _REPLY_COLUMNS:
            value = prefill.get(label)
            cells.append(f"<td style=\"{td_style}background:{zebra};\">{_cell(value)}</td>")
        rows_html.append(f"<tr>{''.join(cells)}</tr>")
    if not rows_html:
        rows_html.append(
            f"<tr><td style=\"{td_style}\" colspan=\"{len(_REPLY_COLUMNS)}\">"
            "(add one row per material)</td></tr>"
        )
    return (
        f"<table role=\"presentation\" style=\"{table_style}\">"
        f"<thead><tr>{head}</tr></thead>"
        f"<tbody>{''.join(rows_html)}</tbody>"
        "</table>"
    )


def render_po_materials_table_text(materials: list[dict[str, Any]]) -> str:
    """Plain-text pipe-delimited table that the reply parser can round-trip."""
    if not materials:
        return "(no materials)"
    header = "| " + " | ".join(label for label, _ in _PO_MATERIAL_COLUMNS) + " |"
    sep = "| " + " | ".join("---" for _ in _PO_MATERIAL_COLUMNS) + " |"
    lines = [header, sep]
    for idx, mat in enumerate(materials, start=1):
        commitment = mat.get("commitment") or {}
        values = [
            str(idx),
            str(mat.get("crm_no") or mat.get("material_code") or "-"),
            str(mat.get("material_name") or "-"),
            str(mat.get("po_qty") if mat.get("po_qty") is not None else "-"),
            str(mat.get("uom") or "-"),
            str(mat.get("due_date") or "-"),
            str(mat.get("current_status") or mat.get("signal") or "-"),
            str(commitment.get("commitment_date") or "-"),
            str(commitment.get("supplier_remark") or "-"),
        ]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def build_po_group_context(group: dict[str, Any]) -> dict[str, Any]:
    """Context dict for PO-wise templates."""
    return {
        "supplier_name": group.get("supplier_name") or "",
        "supplier_po_no": group.get("supplier_po_no") or "",
        "po_no": group.get("supplier_po_no") or "",
        "material_count": group.get("material_count") or 0,
        "overall_signal": group.get("overall_signal") or "GREEN",
        "earliest_due_date": group.get("earliest_due_date") or "",
        "materials_table_html": render_po_materials_table_html(group.get("materials") or []),
        "materials_table_text": render_po_materials_table_text(group.get("materials") or []),
        "reply_table_html": render_po_reply_table_html(group.get("materials") or []),
        "reply_instructions": PO_REPLY_INSTRUCTIONS,
    }


PO_MAIL_TYPE_BY_SIGNAL: dict[str, str] = {
    "GREEN": "PO_FOLLOWUP_GREEN",
    "YELLOW": "PO_FOLLOWUP_YELLOW",
    "RED": "PO_FOLLOWUP_RED",
    "BLACK": "PO_FOLLOWUP_BLACK",
}


def pick_po_template(db: Session, overall_signal: str) -> Optional[MailTemplate]:
    """Pick a PO-wise template based on overall signal, falling back to PO_FOLLOWUP_GROUP."""
    sig = (overall_signal or "GREEN").upper()
    name = PO_MAIL_TYPE_BY_SIGNAL.get(sig, "PO_FOLLOWUP_GROUP")
    row = db.scalar(
        select(MailTemplate).where(
            MailTemplate.template_name == name,
            MailTemplate.active.is_(True),
        )
    )
    if row:
        return row
    return db.scalar(
        select(MailTemplate).where(
            MailTemplate.template_name == "PO_FOLLOWUP_GROUP",
            MailTemplate.active.is_(True),
        )
    )


def pick_template(db: Session, rec: ProcurementRecord) -> Optional[MailTemplate]:
    rule = get_followup_rule(rec)
    if rule.mail_type == "AI_REQUIRED":
        return None
    row = db.scalar(
        select(MailTemplate).where(
            MailTemplate.template_name == rule.mail_type,
            MailTemplate.active.is_(True),
        )
    )
    if row:
        return row

    sig = (rec.signal or "").upper()
    day = 0
    if sig == "RED":
        day = min(red_day_index(rec), 2)  # day 1 or 2; >2 -> AI
        if day > 2:
            return None
    rows = db.scalars(
        select(MailTemplate).where(
            MailTemplate.signal == sig,
            MailTemplate.active.is_(True),
        )
    ).all()
    if not rows:
        return None
    if sig == "RED":
        return next((r for r in rows if r.day_no == day), None) or rows[0]
    return next((r for r in rows if r.day_no == 0), None) or rows[0]


def find_supplier_email(db: Session, supplier_name: Optional[str]) -> Optional[SupplierEmail]:
    if not supplier_name:
        return None
    supplier = db.scalar(
        select(SupplierMaster).where(SupplierMaster.supplier_name == supplier_name)
    )
    if not supplier:
        return None
    return db.scalar(
        select(SupplierEmail).where(
            SupplierEmail.supplier_id == supplier.id,
            SupplierEmail.is_active.is_(True),
        )
    )

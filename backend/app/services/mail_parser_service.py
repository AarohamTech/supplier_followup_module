"""Regex-driven supplier-reply parser.

Rules are loaded from the `mail_parse_rules` table. Each rule maps a regex
pattern against the email subject/body and extracts a single field. The first
non-empty capture group (or full match) is taken as the field's value.

Quantity is coerced to float, date is parsed with several common formats,
all other fields are returned as trimmed strings.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.mail_parse_rule import MailParseRule, PARSE_FIELDS

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Default fallback rules (used only if no DB rule fires for a given field)
# These are deliberately conservative and ignore-case.
# ─────────────────────────────────────────────────────────────────────────────
_FALLBACK_PATTERNS: dict[str, list[str]] = {
    "supplier_po_no": [
        r"\bPO\s*(?:No\.?|Number)\s*[:#-]?\s*([A-Z0-9][A-Z0-9\-\/]{3,})",
        r"\bPO\s*[:#-]\s*([A-Z0-9\-\/]*\d[A-Z0-9\-\/]{2,})",
    ],
    "status": [
        r"\b(dispatched|shipped|ready|delayed|hold|on\s+hold|cancelled|in\s+production|partial)\b",
    ],
    "expected_dispatch_date": [
        r"\b(?:dispatch|ship(?:ment)?|delivery)\s*(?:date|on|by)?\s*[:\-]?\s*"
        r"(\d{1,2}[\-\/\.][A-Za-z0-9]{2,9}[\-\/\.]\d{2,4}|\d{4}-\d{2}-\d{2})",
    ],
    "quantity": [
        r"\b(?:qty|quantity)\s*[:\-]?\s*(\d+(?:\.\d+)?)\b",
    ],
}

_DATE_FORMATS = (
    "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y",
    "%d-%b-%Y", "%d %b %Y", "%d-%B-%Y", "%d %B %Y",
    "%d-%m-%y", "%d/%m/%y",
)


def _compile(pattern: str) -> re.Pattern[str] | None:
    try:
        return re.compile(pattern, re.IGNORECASE | re.MULTILINE)
    except re.error as exc:
        log.warning("Invalid regex pattern %r: %s", pattern, exc)
        return None


def _apply_rule(rx: re.Pattern[str], subject: str, body: str, source: str) -> str | None:
    haystacks: list[str] = []
    if source == "subject":
        haystacks = [subject]
    elif source == "body":
        haystacks = [body]
    else:
        haystacks = [subject, body]

    for text in haystacks:
        if not text:
            continue
        m = rx.search(text)
        if not m:
            continue
        if m.groups():
            for grp in m.groups():
                if grp:
                    return grp.strip()
        return m.group(0).strip()
    return None


def _primary_reply_section(body: str) -> str:
    if not body:
        return ""

    lines: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if re.match(r"^On .+ wrote:\s*$", stripped, re.IGNORECASE):
            break
        if stripped.startswith(">"):
            break
        if stripped in {"-----Original Message-----", "From:"}:
            break
        lines.append(line)
    return "\n".join(lines).strip()


def _coerce_qty(value: str | None) -> float | None:
    if value is None:
        return None
    cleaned = re.sub(r"[^\d.]", "", value)
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _coerce_date(value: str | None) -> datetime | None:
    if not value:
        return None
    val = value.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(val, fmt)
        except ValueError:
            continue
    return None


def parse_email(
    db: Session,
    subject: str,
    body: str,
    supplier_id: int | None = None,
) -> dict[str, Any]:
    """Apply DB rules (then fallback patterns) and return parsed fields."""
    subject = subject or ""
    body = body or ""
    parsed_body = _primary_reply_section(body) or body

    rules: Iterable[MailParseRule] = db.scalars(
        select(MailParseRule)
        .where(MailParseRule.active.is_(True))
        .where(
            (MailParseRule.supplier_id.is_(None))
            | (MailParseRule.supplier_id == supplier_id)
        )
        .order_by(MailParseRule.priority.asc(), MailParseRule.id.asc())
    ).all()

    parsed: dict[str, Any] = {f: None for f in PARSE_FIELDS}

    for rule in rules:
        if rule.field_name not in PARSE_FIELDS:
            continue
        if parsed.get(rule.field_name) is not None:
            continue
        rx = _compile(rule.regex_pattern)
        if rx is None:
            continue
        match = _apply_rule(rx, subject, parsed_body, rule.source or "subject_or_body")
        if match is not None:
            parsed[rule.field_name] = match

    # Fallbacks for fields still missing.
    for field, patterns in _FALLBACK_PATTERNS.items():
        if parsed.get(field) is not None:
            continue
        for pat in patterns:
            rx = _compile(pat)
            if rx is None:
                continue
            match = _apply_rule(rx, subject, parsed_body, "subject_or_body")
            if match is not None:
                parsed[field] = match
                break

    # Type coercion for known fields.
    parsed_typed: dict[str, Any] = dict(parsed)
    parsed_typed["quantity"] = _coerce_qty(parsed.get("quantity"))
    parsed_dt = _coerce_date(parsed.get("expected_dispatch_date"))
    parsed_typed["expected_dispatch_date"] = (
        parsed_dt.isoformat() if parsed_dt else parsed.get("expected_dispatch_date")
    )
    parsed_typed["_expected_dispatch_date_dt"] = parsed_dt
    return parsed_typed

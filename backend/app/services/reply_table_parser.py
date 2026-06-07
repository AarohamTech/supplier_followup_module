"""Material-wise supplier reply parser.

Given a free-form email body, extract per-material lines so each row can be
written to `supplier_material_commitments`. Supports two shapes:

1. Pipe / markdown tables:
       | CRM No | Material Name | Qty | Commitment Date | Remark | Status |
2. Newline-delimited lines using `|` or `;` as field separators with a
   leading material code or material name.

The parser is intentionally tolerant: rows missing some fields are still
returned with the missing ones as None.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Optional

_DATE_FORMATS = (
    "%Y-%m-%d",
    "%d-%m-%Y",
    "%d/%m/%Y",
    "%d.%m.%Y",
    "%d-%b-%Y",
    "%d %b %Y",
    "%d-%B-%Y",
    "%d %B %Y",
    "%d-%m-%y",
    "%d/%m/%y",
)

_STATUS_VOCAB: dict[str, str] = {
    "confirmed": "CONFIRMED",
    "confirm": "CONFIRMED",
    "ok": "CONFIRMED",
    "delayed": "DELAYED",
    "delay": "DELAYED",
    "partial": "PARTIAL",
    "dispatched": "DISPATCHED",
    "shipped": "DISPATCHED",
    "cancelled": "CANCELLED",
    "cancel": "CANCELLED",
    "on hold": "ON_HOLD",
    "hold": "ON_HOLD",
    "pending": "PENDING",
}

_HEADER_ALIASES: dict[str, list[str]] = {
    "material_code": ["crm", "crm no", "code", "material code", "item code", "sku"],
    "material_name": ["material", "material name", "item", "description", "name"],
    "quantity": ["qty", "quantity", "po qty", "pending qty", "pending"],
    "commitment_date": ["commitment date", "commit date", "dispatch date", "eta", "date"],
    "remark": ["remark", "remarks", "reason", "note", "notes"],
    "status": ["status", "current status"],
}


def _norm_header(cell: str) -> Optional[str]:
    c = cell.strip().lower()
    if not c:
        return None
    for canonical, aliases in _HEADER_ALIASES.items():
        if c in aliases:
            return canonical
        for alias in aliases:
            if alias in c:
                return canonical
    return None


def _coerce_qty(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    cleaned = re.sub(r"[^\d.]", "", value)
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _coerce_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    text = value.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _coerce_status(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    key = value.strip().lower()
    if key in _STATUS_VOCAB:
        return _STATUS_VOCAB[key]
    for raw, canonical in _STATUS_VOCAB.items():
        if raw in key:
            return canonical
    return None


def _primary_reply_section(body: str) -> str:
    lines: list[str] = []
    for line in (body or "").splitlines():
        stripped = line.strip()
        if re.match(r"^On .+ wrote:\s*$", stripped, re.IGNORECASE):
            break
        if stripped.startswith(">"):
            break
        if stripped in {"-----Original Message-----", "From:"}:
            break
        lines.append(line)
    return "\n".join(lines).strip()


def _split_row(line: str) -> list[str]:
    if "|" in line:
        parts = [p.strip() for p in line.strip().strip("|").split("|")]
    elif "\t" in line:
        parts = [p.strip() for p in re.split(r"\t+", line.strip())]
    else:
        parts = [p.strip() for p in line.strip().split(";")]
    return [p for p in parts if p != ""]


def _is_separator_row(parts: list[str]) -> bool:
    return all(re.fullmatch(r":?-+:?", p or "") for p in parts) if parts else False


def _is_header_like_value(value: Optional[str]) -> bool:
    if not value:
        return False
    return _norm_header(value) is not None


def _is_header_like_row(row: dict[str, Any]) -> bool:
    material_code = row.get("material_code")
    material_name = row.get("material_name")
    return bool(material_code or material_name) and all(
        _is_header_like_value(value)
        for value in [material_code, material_name]
        if value
    )


_CRM_TOKEN = r"[A-Za-z0-9][A-Za-z0-9\-/_]{3,}"
_PLAIN_ROW_START = re.compile(rf"^\d+\s+{_CRM_TOKEN}\b")
_PLAIN_ROW_PATTERN = re.compile(
    r"^\d+\s+"
    rf"(?P<material_code>{_CRM_TOKEN})\s+"
    r"(?P<material_name>.*?)\s+"
    r"(?P<quantity>\d+(?:\.\d+)?)\s+"
    r"(?P<uom>[A-Z]{1,10})\s+"
    r"(?P<due_date>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}|\d{1,2}[\-\/.][A-Za-z0-9]{2,9}[\-\/.]\d{2,4}|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{2,4})\s+"
    r"(?P<current_status>[A-Z_]+(?:\s+[A-Z_]+)?)\s*"
    r"(?P<tail>.*)$"
)


def _parse_plain_tail(tail: str) -> tuple[Optional[date], Optional[str], Optional[str]]:
    text = re.sub(r"\s+", " ", (tail or "").strip())
    if not text or text == "-":
        return None, None, None

    parts = text.split(" ", 1)
    first = parts[0]
    maybe_date = _coerce_date(first)
    if maybe_date is not None:
        remark = parts[1].strip() if len(parts) > 1 else None
        if remark == "-":
            remark = None
        return maybe_date, remark, None

    maybe_status = _coerce_status(text)
    if maybe_status and len(text.split()) <= 3:
        return None, None, maybe_status

    text = re.sub(r"\s+-\s*$", "", text).strip()
    return None, (text or None), None


def _parse_plaintext_po_table(lines: list[str]) -> list[dict[str, Any]]:
    header_idx: Optional[int] = None
    for idx, line in enumerate(lines):
        norm = re.sub(r"\s+", " ", line.strip().upper())
        if norm.startswith("SR NO CRM NO MATERIAL NAME PO QTY UOM DUE DATE CURRENT STATUS LAST"):
            header_idx = idx
            break

    if header_idx is None:
        return []

    blocks: list[list[str]] = []
    current: list[str] = []
    for line in lines[header_idx + 1 :]:
        stripped = line.strip()
        if not stripped:
            if current:
                blocks.append(current)
                current = []
            continue
        if re.match(r"^(PLEASE REPLY|REGARDS[, ]*$)", stripped, re.IGNORECASE):
            break
        if _PLAIN_ROW_START.match(stripped):
            if current:
                blocks.append(current)
            current = [stripped]
            continue
        if current:
            current.append(stripped)
    if current:
        blocks.append(current)

    rows: list[dict[str, Any]] = []
    for block in blocks:
        text = re.sub(r"\s+", " ", " ".join(block)).strip()
        match = _PLAIN_ROW_PATTERN.match(text)
        if not match:
            continue
        commitment_date, remark, supplier_status = _parse_plain_tail(match.group("tail"))
        rows.append(
            {
                "material_code": match.group("material_code"),
                "material_name": match.group("material_name").strip(),
                "quantity": _coerce_qty(match.group("quantity")),
                "commitment_date": commitment_date,
                "remark": remark,
                "supplier_status": supplier_status,
            }
        )
    return rows


_VERTICAL_SKIP_HEADERS = {
    "sr no", "sr. no", "sr.no", "sr", "s.no", "s no",
    "uom", "unit", "units",
    "due date", "due", "po due date",
}

_VERTICAL_STOP_LINE = re.compile(
    r"^(please\s+reply|regards\b|thanks\b|thank\s+you\b|on\s+.+\s+wrote\s*:?)",
    re.IGNORECASE,
)


def _vertical_clean(line: str) -> str:
    return re.sub(r"^[*\s]+|[*\s]+$", "", line).strip()


def _vertical_header_for(cell: str) -> Optional[str]:
    cleaned = cell.strip().lower()
    if not cleaned:
        return None
    if cleaned in _VERTICAL_SKIP_HEADERS:
        return "__skip__"
    return _norm_header(cleaned)


def _build_vertical_row(headers: list[str], values: list[str]) -> Optional[dict[str, Any]]:
    row: dict[str, Any] = {
        "material_code": None,
        "material_name": None,
        "quantity": None,
        "commitment_date": None,
        "remark": None,
        "supplier_status": None,
    }
    for header, value in zip(headers, values):
        if not value or value.strip() in {"-", "--", "n/a", "na"}:
            continue
        if header == "__skip__":
            continue
        if header == "quantity":
            row["quantity"] = _coerce_qty(value)
        elif header == "commitment_date":
            row["commitment_date"] = _coerce_date(value)
        elif header == "status":
            row["supplier_status"] = _coerce_status(value)
        elif header == "remark":
            row["remark"] = value.strip() or None
        elif header == "material_code":
            row["material_code"] = value.strip() or None
        elif header == "material_name":
            row["material_name"] = value.strip() or None
    if not (row["material_code"] or row["material_name"]):
        return None
    return row


def _parse_vertical_po_table(lines: list[str]) -> list[dict[str, Any]]:
    """Parse the 'one-cell-per-line' email layout (common when HTML tables
    are flattened to text by mail clients).

    Strategy:
    1. Collect non-empty cells (with markdown bold ``*...*`` stripped).
    2. Find the longest run of consecutive cells that map to canonical
       header tokens (or known skip tokens like ``Sr No``/``UOM``/``Due Date``).
    3. Treat the run length ``N`` as the column count and chunk subsequent
       cells into groups of ``N`` to form material rows.
    """
    cells: list[str] = []
    for ln in lines:
        cleaned = _vertical_clean(ln)
        if cleaned:
            cells.append(cleaned)
    if len(cells) < 6:
        return []

    best_start = -1
    best_headers: list[str] = []
    i = 0
    while i < len(cells):
        run: list[str] = []
        j = i
        while j < len(cells):
            mapped = _vertical_header_for(cells[j])
            if mapped is None:
                break
            run.append(mapped)
            j += 1
        if len(run) > len(best_headers):
            best_headers = run
            best_start = i
        i = j + 1 if j > i else i + 1

    # Need at least 3 headers with at least one of material_code/material_name.
    if (
        best_start < 0
        or len(best_headers) < 3
        or not any(h in {"material_code", "material_name"} for h in best_headers)
    ):
        return []

    n = len(best_headers)
    data = cells[best_start + n :]

    rows: list[dict[str, Any]] = []
    chunk: list[str] = []
    for val in data:
        if _VERTICAL_STOP_LINE.match(val):
            break
        chunk.append(val)
        if len(chunk) == n:
            row = _build_vertical_row(best_headers, chunk)
            if row and not _is_header_like_row(row):
                rows.append(row)
            chunk = []
    return rows


def parse_reply_table(body: Optional[str]) -> list[dict[str, Any]]:
    """Extract per-material commitment rows from a reply body.

    Returns a list of dicts with keys: material_code, material_name,
    quantity, commitment_date, remark, supplier_status.
    """
    if not body:
        return []

    body = _primary_reply_section(body)
    if not body:
        return []

    lines = [ln for ln in body.splitlines() if ln.strip()]
    if not lines:
        return []

    vertical_rows = _parse_vertical_po_table(lines)
    if vertical_rows:
        return vertical_rows

    plain_rows = _parse_plaintext_po_table(lines)
    if plain_rows:
        return plain_rows

    header_idx: Optional[int] = None
    header_map: dict[int, str] = {}
    for idx, line in enumerate(lines):
        parts = _split_row(line)
        if len(parts) < 2:
            continue
        canonical = [(i, _norm_header(p)) for i, p in enumerate(parts)]
        recognised = [c for c in canonical if c[1] is not None]
        if len(recognised) >= 2:
            header_idx = idx
            header_map = {i: name for i, name in recognised}
            break

    rows: list[dict[str, Any]] = []
    if header_idx is None:
        # Loose mode: scan lines that have at least 3 pipe-separated cells.
        for line in lines:
            parts = _split_row(line)
            if len(parts) < 3:
                continue
            rows.append(
                {
                    "material_code": parts[0],
                    "material_name": parts[1] if len(parts) > 1 else None,
                    "quantity": _coerce_qty(parts[2]) if len(parts) > 2 else None,
                    "commitment_date": _coerce_date(parts[3]) if len(parts) > 3 else None,
                    "remark": parts[4] if len(parts) > 4 else None,
                    "supplier_status": _coerce_status(parts[5]) if len(parts) > 5 else None,
                }
            )
        return [r for r in rows if r.get("material_name") or r.get("material_code")]

    for line in lines[header_idx + 1 :]:
        parts = _split_row(line)
        if not parts or _is_separator_row(parts):
            continue
        if len(parts) < 2:
            continue
        row: dict[str, Any] = {
            "material_code": None,
            "material_name": None,
            "quantity": None,
            "commitment_date": None,
            "remark": None,
            "supplier_status": None,
        }
        for col_idx, value in enumerate(parts):
            field = header_map.get(col_idx)
            if not field:
                continue
            if field == "quantity":
                row["quantity"] = _coerce_qty(value)
            elif field == "commitment_date":
                row["commitment_date"] = _coerce_date(value)
            elif field == "status":
                row["supplier_status"] = _coerce_status(value)
            elif field == "remark":
                row["remark"] = value or None
            elif field == "material_code":
                row["material_code"] = value or None
            elif field == "material_name":
                row["material_name"] = value or None
        if (row.get("material_name") or row.get("material_code")) and not _is_header_like_row(row):
            rows.append(row)

    return rows

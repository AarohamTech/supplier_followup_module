"""Harmony Intelligence Summary — daily admin digest.

Gathers current procurement state, renders a branded HTML email, and sends it
once per local calendar day to an admin-configured recipient list. All config
lives in AppSetting key `admin_digest` (see settings_service).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from ..models.communication_message import CommunicationMessage
from ..models.procurement import ProcurementRecord
from . import ai_service, brand_email, settings_service
from ..core.config import settings
from ..workers import mail_send_worker

log = logging.getLogger(__name__)

CRITICAL_ESCALATIONS = ("CRITICAL", "LEVEL_2")
OPEN_FOLLOWUP_STATUSES = (
    "REMINDER_DUE", "URGENT_FOLLOWUP", "STRONG_FOLLOWUP",
    "AI_FOLLOWUP", "CRITICAL_ESCALATION", "PENDING_ACK",
)


def _days_late(shipment_date: datetime | None, today: datetime) -> int | None:
    if shipment_date is None:
        return None
    delta = (today.date() - shipment_date.date()).days
    return delta if delta > 0 else 0


def _po(r: Any) -> str:
    return r.supplier_po_no or "—"


def summarize_counts(active_rows, overdue_count, critical_count, new_replies) -> dict:
    signals = {"GREEN": 0, "YELLOW": 0, "RED": 0, "BLACK": 0}
    open_followups = 0
    for r in active_rows:
        if r.signal in signals:
            signals[r.signal] += 1
        if getattr(r, "followup_status", None) in OPEN_FOLLOWUP_STATUSES:
            open_followups += 1
    return {
        "active": len(active_rows),
        "open_followups": open_followups,
        "overdue": overdue_count,
        "critical": critical_count,
        "new_replies": new_replies,
        "signals": signals,
    }


def format_critical(rows, today) -> list[dict]:
    return [{
        "po": _po(r), "supplier": r.supplier_name or "—", "material": r.material_name or "",
        "signal": (r.signal or "").title(), "days_late": _days_late(r.shipment_date, today),
        "risk": r.risk_score,
    } for r in rows]


def format_overdue(rows, today) -> list[dict]:
    out = []
    for r in rows:
        late = _days_late(r.shipment_date, today)
        status = "Due today" if late == 0 else "Overdue"
        ship = r.shipment_date.strftime("%d %b") if r.shipment_date else "—"
        out.append({"po": _po(r), "supplier": r.supplier_name or "—",
                    "shipment": ship, "status": status, "days_late": late})
    return out


def format_risk(rows) -> list[dict]:
    return [{"po": _po(r), "supplier": r.supplier_name or "—",
             "reason": r.risk_reason or "", "score": r.risk_score or 0} for r in rows]


def _gather_counts(db: Session) -> dict:
    today = datetime.utcnow()
    active = list(db.scalars(select(ProcurementRecord)).all())
    overdue = sum(1 for r in active if r.shipment_date and r.shipment_date.date() < today.date())
    critical = sum(1 for r in active
                   if r.signal == "BLACK" or r.escalation_level in CRITICAL_ESCALATIONS)
    since = today - timedelta(hours=24)
    new_replies = db.scalar(
        select(func.count()).select_from(CommunicationMessage).where(
            CommunicationMessage.direction == "INCOMING",
            CommunicationMessage.received_at >= since,
        )
    ) or 0
    return summarize_counts(active, overdue, critical, new_replies)


def _gather_critical(db: Session, limit: int) -> list[dict]:
    rows = db.scalars(
        select(ProcurementRecord)
        .where(or_(ProcurementRecord.signal == "BLACK",
                   ProcurementRecord.escalation_level.in_(CRITICAL_ESCALATIONS)))
        .order_by(ProcurementRecord.risk_score.desc().nullslast())
        .limit(limit)
    ).all()
    return format_critical(rows, datetime.utcnow())


def _gather_risk(db: Session, limit: int) -> list[dict]:
    rows = db.scalars(
        select(ProcurementRecord)
        .where(ProcurementRecord.risk_band == "HIGH")
        .order_by(ProcurementRecord.risk_score.desc().nullslast())
        .limit(limit)
    ).all()
    return format_risk(rows)


def _gather_overdue(db: Session, limit: int) -> list[dict]:
    today = datetime.utcnow()
    rows = db.scalars(
        select(ProcurementRecord)
        .where(ProcurementRecord.shipment_date.isnot(None),
               ProcurementRecord.shipment_date <= today)
        .order_by(ProcurementRecord.shipment_date.asc())
        .limit(limit)
    ).all()
    return format_overdue(rows, today)


HEAT_TONE_LABELS = {"frustrated", "tense", "angry", "calm", "neutral"}


def _fallback_summary(counts: dict) -> str:
    s = counts["signals"]
    return (
        f"{counts['critical']} critical POs need attention and "
        f"{counts['overdue']} shipments are overdue. Signal mix is "
        f"{s['GREEN']} green / {s['YELLOW']} yellow / {s['RED']} red / {s['BLACK']} black "
        f"across {counts['active']} active POs, with {counts['open_followups']} open "
        f"follow-ups and {counts['new_replies']} new supplier replies in the last 24 hours."
    )


def _ai_summary(counts: dict, critical: list[dict], heated: list[dict]) -> str:
    if not ai_service.is_enabled():
        return _fallback_summary(counts)
    try:
        crit = "; ".join(f"{c['po']} {c['supplier']} ({c['signal']}, risk {c['risk']})"
                         for c in critical[:5]) or "none"
        heat = "; ".join(f"{h['supplier']} {h['po']} ({h['tone']})" for h in heated[:5]) or "none"
        result = ai_service.complete_json(
            system=("You are Harmony Intelligence, a procurement analyst. Write ONE concise "
                    "paragraph (max 60 words) summarizing the day's supplier delivery state. "
                    "Return JSON {\"summary\": \"...\"}. No markdown, no lists."),
            user=(f"Counts: {counts}. Most critical: {crit}. Heated threads: {heat}."),
            temperature=0.3,
        )
        text = (result or {}).get("summary", "").strip()
        return text or _fallback_summary(counts)
    except Exception:  # noqa: BLE001
        log.exception("admin digest AI summary failed; using fallback")
        return _fallback_summary(counts)


def rank_heated_candidates(rows) -> list:
    """rows: objects with .recent_count, .msg_count, .escalation_level."""
    esc_weight = {"CRITICAL": 3, "LEVEL_2": 2, "LEVEL_1": 1, "NONE": 0}
    return sorted(
        rows,
        key=lambda r: (r.recent_count * 2 + r.msg_count
                       + esc_weight.get(getattr(r, "escalation_level", "NONE"), 0)),
        reverse=True,
    )


def _gather_heated(db: Session, limit: int) -> list[dict]:
    """Rank PO threads by recent activity, then LLM-score tone (fallback: heuristic)."""
    since = datetime.utcnow() - timedelta(hours=24)
    # Aggregate per-PO message activity.
    agg = db.execute(
        select(
            CommunicationMessage.supplier_po_no,
            CommunicationMessage.supplier_name,
            func.count().label("msg_count"),
            func.sum(case((CommunicationMessage.received_at >= since, 1), else_=0)
                     ).label("recent_count"),
        )
        .where(CommunicationMessage.supplier_po_no.isnot(None))
        .group_by(CommunicationMessage.supplier_po_no, CommunicationMessage.supplier_name)
        .order_by(func.count().desc())
        .limit(max(limit * 3, 6))
    ).all()
    candidates = [
        type("C", (), {"supplier_po_no": a[0], "supplier_name": a[1],
                       "msg_count": int(a[2] or 0), "recent_count": int(a[3] or 0),
                       "escalation_level": "NONE"})()
        for a in agg
    ]
    ranked = rank_heated_candidates(candidates)[:limit]
    out: list[dict] = []
    for c in ranked:
        try:
            tone, score, quote = _score_tone(db, c)
        except Exception:  # noqa: BLE001
            log.exception("_score_tone failed for %s; skipping", c.supplier_po_no)
            continue
        if tone in ("frustrated", "tense", "angry"):
            out.append({"supplier": c.supplier_name or "—", "po": c.supplier_po_no or "—",
                        "tone": tone.title(), "score": score,
                        "msg_count": c.msg_count, "recent_count": c.recent_count, "quote": quote})
    return out


def _score_tone(db: Session, candidate) -> tuple[str, float, str | None]:
    """Return (tone, score, quote). LLM if enabled, else heuristic by activity."""
    last = db.scalars(
        select(CommunicationMessage)
        .where(CommunicationMessage.supplier_po_no == candidate.supplier_po_no,
               CommunicationMessage.direction == "INCOMING")
        .order_by(CommunicationMessage.received_at.desc().nullslast())
        .limit(1)
    ).first()
    quote = (last.body or "")[:160].strip() if last and last.body else None
    if not ai_service.is_enabled() or not quote:
        # Heuristic: lots of recent back-and-forth reads as tense.
        tone = "tense" if candidate.recent_count >= 3 else "neutral"
        return tone, min(0.6, 0.2 + candidate.recent_count * 0.1), quote
    try:
        result = ai_service.complete_json(
            system=("Classify the tone of this supplier message. Return JSON "
                    "{\"tone\": one of [calm, neutral, tense, frustrated, angry], "
                    "\"score\": 0..1}."),
            user=quote,
            temperature=0.0,
        )
        tone = str((result or {}).get("tone", "neutral")).lower()
        if tone not in HEAT_TONE_LABELS:
            tone = "neutral"
        score = float((result or {}).get("score", 0.5) or 0.5)
        return tone, round(score, 2), quote
    except Exception:  # noqa: BLE001
        log.exception("admin digest tone scoring failed; using heuristic")
        tone = "tense" if candidate.recent_count >= 3 else "neutral"
        return tone, min(0.6, 0.2 + candidate.recent_count * 0.1), quote


# ---------------------------------------------------------------------------
# Task 5: HTML rendering
# ---------------------------------------------------------------------------

INK = brand_email.BRAND_INK      # "#1f2937"
MUTED = brand_email.BRAND_MUTED  # "#6B7280"
RED = brand_email.BRAND_RED      # "#E11D2E"
HAIR = brand_email.BRAND_BORDER  # "#ECECEC"
FAINT = "#9aa0a6"                # column-label gray
ROW = "#F4F4F5"                  # row-separator gray

_LABEL = (f'font-size:11px;font-weight:700;letter-spacing:1.5px;'
          f'text-transform:uppercase;color:{MUTED};padding-bottom:12px;')
_SECTION = f'padding:24px 32px 0;'
_DIVIDER = f'border-top:1px solid {HAIR};padding-top:20px;'


def digest_subject(data: dict) -> str:
    date_part = data["generated_at_local"].split(" · ")[0]
    return f"Harmony Intelligence Summary — {date_part}"


def _esc(v: Any) -> str:
    s = "" if v is None else str(v)
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _section(label: str, inner: str, *, first: bool = False) -> str:
    div = "" if first else _DIVIDER
    return (f'<div style="{_SECTION}"><div style="{div}">'
            f'<div style="{_LABEL}">{label}</div>{inner}</div></div>')


def _counts_html(c: dict) -> str:
    tiles = [("Active POs", c["active"], INK), ("Open follow-ups", c["open_followups"], INK),
             ("Overdue", c["overdue"], RED), ("Critical", c["critical"], INK),
             ("New replies", c["new_replies"], INK)]
    cells = "".join(
        f'<td style="padding:0 16px;border-right:1px solid {HAIR};">'
        f'<div style="font-size:28px;font-weight:700;color:{color};">{_esc(val)}</div>'
        f'<div style="font-size:12px;color:{MUTED};padding-top:3px;">{_esc(lbl)}</div></td>'
        for lbl, val, color in tiles)
    s = c["signals"]
    sig = (f'<div style="font-size:13px;color:{MUTED};padding-top:16px;">'
           f'<span style="color:{INK};">Signal mix</span>&nbsp;&nbsp;'
           f'Green <b style="color:{INK};">{s["GREEN"]}</b> &middot; '
           f'Yellow <b style="color:{INK};">{s["YELLOW"]}</b> &middot; '
           f'Red <b style="color:{INK};">{s["RED"]}</b> &middot; '
           f'Black <b style="color:{INK};">{s["BLACK"]}</b></div>')
    return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0">'
            f'<tr>{cells}</tr></table>{sig}')


def _table(headers: list[tuple[str, str]], rows: list[str]) -> str:
    head = "".join(
        f'<td style="font-size:11px;font-weight:700;letter-spacing:.4px;text-transform:uppercase;'
        f'color:{FAINT};padding:0 0 8px;{align}">{_esc(h)}</td>' for h, align in headers)
    return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            f'style="border-collapse:collapse;"><tr style="border-bottom:1px solid {HAIR};">'
            f'{head}</tr>{"".join(rows)}</table>')


def _critical_html(items: list[dict]) -> str:
    rows = []
    for it in items:
        late = "—" if it["days_late"] is None else it["days_late"]
        rows.append(
            f'<tr style="border-bottom:1px solid {ROW};">'
            f'<td style="padding:13px 0;font-size:13px;color:{INK};"><b>{_esc(it["po"])}</b><br>'
            f'<span style="font-size:12px;color:{MUTED};">{_esc(it["supplier"])} &middot; {_esc(it["material"])}</span></td>'
            f'<td style="padding:13px 0;font-size:12px;font-weight:700;color:{INK};">{_esc(it["signal"])}</td>'
            f'<td style="padding:13px 0;font-size:13px;font-weight:700;color:{RED};text-align:right;">{late}</td>'
            f'<td style="padding:13px 0;font-size:13px;font-weight:700;color:{INK};text-align:right;">{_esc(it["risk"])}</td></tr>')
    return _table([("PO / Supplier", ""), ("Signal", ""),
                   ("Days late", "text-align:right;"), ("Risk", "text-align:right;")], rows)


def _heated_html(items: list[dict]) -> str:
    blocks = []
    for it in items:
        blocks.append(
            f'<div style="padding-bottom:14px;">'
            f'<table role="presentation" width="100%"><tr>'
            f'<td style="font-size:13px;font-weight:700;color:{INK};">{_esc(it["supplier"])} &middot; {_esc(it["po"])}</td>'
            f'<td style="text-align:right;font-size:12px;color:{RED};font-weight:700;">{_esc(it["tone"])} &middot; {_esc(it["score"])}</td>'
            f'</tr></table>'
            f'<div style="font-size:12px;color:{MUTED};padding-top:5px;line-height:1.55;">'
            f'{_esc(it["msg_count"])} messages, {_esc(it["recent_count"])} in the last 24h.'
            + (f' &ldquo;<i>{_esc(it["quote"])}</i>&rdquo;' if it.get("quote") else "")
            + '</div></div>')
    return "".join(blocks)


def _risk_html(items: list[dict]) -> str:
    rows = [
        f'<tr style="border-bottom:1px solid {ROW};">'
        f'<td style="padding:12px 0;font-size:13px;color:{INK};"><b>{_esc(it["po"])}</b> &middot; '
        f'<span style="color:{MUTED};">{_esc(it["supplier"])}</span></td>'
        f'<td style="padding:12px 0;font-size:12px;color:{MUTED};">{_esc(it["reason"])}</td>'
        f'<td style="padding:12px 0;font-size:13px;font-weight:700;color:{INK};text-align:right;">{_esc(it["score"])}</td></tr>'
        for it in items]
    return _table([("PO / Supplier", ""), ("Why", ""), ("Score", "text-align:right;")], rows)


def _overdue_html(items: list[dict]) -> str:
    rows = [
        f'<tr style="border-bottom:1px solid {ROW};">'
        f'<td style="padding:12px 0;font-size:13px;color:{INK};"><b>{_esc(it["po"])}</b> &middot; '
        f'<span style="color:{MUTED};">{_esc(it["supplier"])}</span></td>'
        f'<td style="padding:12px 0;font-size:12px;font-weight:700;color:{RED};">{_esc(it["shipment"])}</td>'
        f'<td style="padding:12px 0;font-size:12px;color:{MUTED};text-align:right;">{_esc(it["status"])}</td></tr>'
        for it in items]
    return _table([("PO / Supplier", ""), ("Shipment", ""), ("Status", "text-align:right;")], rows)


def render_digest_html(data: dict, cfg: dict) -> str:
    sec = cfg.get("sections", {})
    parts = [
        f'<div style="padding:28px 32px 0;">'
        f'<div style="font-size:22px;font-weight:700;letter-spacing:-.2px;color:{INK};">Harmony Intelligence Summary</div>'
        f'<div style="font-size:13px;color:{MUTED};padding-top:5px;">{_esc(data["generated_at_local"])} &middot; covering the last 24 hours</div></div>'
    ]
    if sec.get("counts", True) and data.get("counts"):
        parts.append(_section("At a glance", _counts_html(data["counts"]), first=True))
    if sec.get("summary", True) and data.get("summary"):
        parts.append(_section("Summary",
                     f'<div style="font-size:14px;line-height:1.6;color:{INK};">{_esc(data["summary"])}</div>'))
    if sec.get("critical", True) and data.get("critical"):
        parts.append(_section("Most critical", _critical_html(data["critical"])))
    if sec.get("heated", True) and data.get("heated"):
        parts.append(_section("Heated conversations", _heated_html(data["heated"])))
    if sec.get("risk", True) and data.get("risk"):
        parts.append(_section("Top delay-risk POs", _risk_html(data["risk"])))
    if sec.get("overdue", True) and data.get("overdue"):
        parts.append(_section("Overdue &amp; due today", _overdue_html(data["overdue"])))
    parts.append('<div style="padding:28px 32px;"></div>')
    inner = (brand_email.header_html("Intelligence Summary") + "".join(parts)
             + brand_email.footer_html(
                 "You receive this because you are on the Harmony Intelligence Summary list. "
                 "Manage recipients, send time, and sections in Settings &rarr; Daily Summary."))
    return brand_email.shell(inner)


def build_digest_data(db: "Session", cfg: dict) -> dict:  # type: ignore[name-defined]
    sec = cfg.get("sections", {})
    lim = cfg.get("limits", {})
    now_local = datetime.utcnow().replace(tzinfo=ZoneInfo("UTC")).astimezone(
        ZoneInfo(cfg.get("timezone", "Asia/Kolkata")))
    tz_abbr = "IST" if cfg.get("timezone") == "Asia/Kolkata" else now_local.tzname() or ""
    counts = _gather_counts(db) if sec.get("counts", True) else None
    critical = _gather_critical(db, lim.get("critical", 10)) if sec.get("critical", True) else []
    heated = _gather_heated(db, lim.get("heated", 5)) if sec.get("heated", True) else []
    risk = _gather_risk(db, lim.get("risk", 10)) if sec.get("risk", True) else []
    overdue = _gather_overdue(db, lim.get("overdue", 15)) if sec.get("overdue", True) else []
    summary = (_ai_summary(counts, critical, heated)
               if sec.get("summary", True) and counts else "")
    return {
        "generated_at_local": now_local.strftime(f"%d %B %Y · %H:%M {tz_abbr}").lstrip("0"),
        "counts": counts or {"active": 0, "open_followups": 0, "overdue": 0, "critical": 0,
                             "new_replies": 0, "signals": {"GREEN": 0, "YELLOW": 0, "RED": 0, "BLACK": 0}},
        "summary": summary, "critical": critical, "heated": heated, "risk": risk, "overdue": overdue,
    }


# ---------------------------------------------------------------------------
# Task 6: Send orchestration + once-per-day due gating
# ---------------------------------------------------------------------------

def send_digest_if_due(db: Session, *, now: datetime | None = None) -> dict:
    cfg = settings_service.get_admin_digest(db)
    if not cfg["enabled"]:
        return {"skipped": "disabled"}
    if not cfg["recipients"]:
        return {"skipped": "no recipients"}
    if not getattr(settings, "SMTP_ENABLED", False):
        return {"skipped": "smtp disabled"}
    now_utc = now or datetime.utcnow()
    local = now_utc.replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo(cfg["timezone"]))
    if local.hour < int(cfg["send_hour"]):
        return {"skipped": "before send_hour"}
    today_iso = local.date().isoformat()
    if cfg.get("last_sent_date") == today_iso:
        return {"skipped": "already sent today"}

    data = build_digest_data(db, cfg)
    html = render_digest_html(data, cfg)
    result = mail_send_worker.send_html_email(cfg["recipients"], digest_subject(data), html)
    if not result.get("sent"):
        return {"error": True, "reason": result.get("reason", "send failed")}
    settings_service.mark_admin_digest_sent(db, today_iso)
    return {"sent": result.get("recipients", len(cfg["recipients"])), "date": today_iso}


def send_test_digest(db: Session, to_email: str) -> dict:
    cfg = settings_service.get_admin_digest(db)
    data = build_digest_data(db, cfg)
    html = render_digest_html(data, cfg)
    return mail_send_worker.send_html_email([to_email], digest_subject(data), html)

"""Shared brand styling for outgoing HTML emails (Harmony × Hariom theme).

The website theme is brand red (#E11D2E) on white, so emails match that instead
of the old dark/slate header. The Harmony logo mark is inlined as a base64 SVG
data URI (renders in Gmail / Apple Mail / most webmail; Outlook desktop falls back
to the wordmark text beside it).
"""
from __future__ import annotations

import base64
import html as _html

from ..core.config import settings

BRAND_RED = "#E11D2E"
BRAND_RED_DARK = "#B01624"
BRAND_INK = "#1f2937"
BRAND_MUTED = "#6B7280"
BRAND_SURFACE = "#f5f5f7"
BRAND_BORDER = "#ECECEC"

_MARK_PATH = (
    "M135 134 L135 394 M378 134 L378 394 M135 394 L256 108 "
    "M378 394 L256 108 M135 134 L378 394 M378 134 L135 394"
)


def _logo_data_uri(stroke: str = "#ffffff") -> str:
    svg = (
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 512 512' fill='none' "
        f"stroke='{stroke}' stroke-linecap='round' stroke-linejoin='round'>"
        "<rect x='64' y='64' width='384' height='384' rx='92' stroke-width='32'/>"
        f"<path d='{_MARK_PATH}' stroke-width='26'/></svg>"
    )
    b64 = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{b64}"


def _logo_src() -> str:
    """Logo URL for emails. Gmail (and many clients) block inline SVG data URIs,
    so prefer a hosted PNG served by the frontend; fall back to the SVG data URI
    only when no public base URL is configured.
    """
    base = (settings.APP_BASE_URL or "").strip().rstrip("/")
    if base:
        return f"{base}/email-logo.png"
    return _logo_data_uri("#ffffff")


def _zanvar_src() -> str:
    """Hosted Zanvar Group logo for emails. Only available when a public base URL is
    configured (there is no inline SVG fallback for a client raster logo); returns ""
    otherwise so the header simply omits the co-brand instead of a broken image."""
    base = (settings.APP_BASE_URL or "").strip().rstrip("/")
    return f"{base}/zanvar-logo.png" if base else ""


def header_html(subtitle: str) -> str:
    """Brand-red header bar with the 'Zanvar Group × Harmony' co-brand lockup."""
    logo = _logo_src()
    zanvar = _zanvar_src()
    # Zanvar's mark sits on a white chip so its dark wordmark stays legible on the
    # brand-red bar; the "×" mirrors the in-app lockup. Omitted when no hosted asset.
    zanvar_cell = (
        (
            '<td style="vertical-align:middle;padding-right:10px;">'
            f'<img src="{zanvar}" height="30" alt="Zanvar Group" '
            'style="display:block;height:30px;width:auto;background:#ffffff;'
            'border-radius:5px;padding:3px;"/></td>'
            '<td style="vertical-align:middle;padding-right:10px;color:#ffe3e6;'
            'font-size:16px;font-weight:700;">&#215;</td>'
        )
        if zanvar
        else ""
    )
    return (
        f'<div style="background:{BRAND_RED};padding:14px 20px;">'
        '<table role="presentation" cellpadding="0" cellspacing="0" '
        'style="border-collapse:collapse;">'
        '<tr>'
        f'{zanvar_cell}'
        '<td style="vertical-align:middle;padding-right:12px;">'
        f'<img src="{logo}" width="30" height="30" alt="Harmony" style="display:block;"/>'
        '</td>'
        '<td style="vertical-align:middle;">'
        '<div style="color:#ffffff;font-size:15px;font-weight:700;letter-spacing:.2px;">'
        'Harmony</div>'
        f'<div style="color:#ffe3e6;font-size:11px;">{subtitle}</div>'
        '</td>'
        '</tr></table>'
        '</div>'
    )


def shell(inner_html: str, *, max_width: int = 760) -> str:
    """Wrap body content in the branded card (white card on a light surface)."""
    return (
        f'<div style="background:{BRAND_SURFACE};padding:18px;'
        'font-family:Arial,Helvetica,sans-serif;">'
        f'<div style="max-width:{max_width}px;margin:0 auto;background:#ffffff;'
        f'border:1px solid {BRAND_BORDER};border-radius:12px;overflow:hidden;">'
        f'{inner_html}'
        '</div></div>'
    )


def footer_html(note: str) -> str:
    return (
        f'<div style="background:#fff5f6;border-top:1px solid {BRAND_BORDER};'
        f'padding:10px 20px;font-size:11px;color:{BRAND_MUTED};">{note}</div>'
    )


def text_email_html(text: str, *, subtitle: str = "Supplier Follow-up") -> str:
    """Wrap a plain-text body in the branded HTML shell.

    Every outgoing mail should leave the platform as HTML. Messages that were
    composed as plain text (hub replies, acknowledgements, escalations) have no
    authored ``body_html``; this renders them inside the same brand-red header /
    white card treatment as the templated follow-ups. Content is HTML-escaped and
    line breaks are preserved, so arbitrary user text is safe to embed.
    """
    safe = _html.escape(text or "").replace("\r\n", "\n").replace("\n", "<br/>")
    inner = (
        header_html(subtitle)
        + f'<div style="padding:20px 22px;color:{BRAND_INK};font-size:14px;'
        f'line-height:1.65;">{safe}</div>'
        + footer_html("Sent via Harmony &#215; Hariom &#183; Supplier Follow-up")
    )
    return shell(inner)

"""Shared brand styling for outgoing HTML emails (Harmony × Hariom theme).

The website theme is brand red (#E11D2E) on white, so emails match that instead
of the old dark/slate header. The Harmony logo mark is inlined as a base64 SVG
data URI (renders in Gmail / Apple Mail / most webmail; Outlook desktop falls back
to the wordmark text beside it).
"""
from __future__ import annotations

import base64

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


def header_html(subtitle: str) -> str:
    """Brand-red header bar with the Harmony mark + 'Harmony × Hariom' wordmark."""
    logo = _logo_data_uri("#ffffff")
    return (
        f'<div style="background:{BRAND_RED};padding:14px 20px;">'
        '<table role="presentation" cellpadding="0" cellspacing="0" '
        'style="border-collapse:collapse;">'
        '<tr>'
        '<td style="vertical-align:middle;padding-right:12px;">'
        f'<img src="{logo}" width="30" height="30" alt="Harmony" style="display:block;"/>'
        '</td>'
        '<td style="vertical-align:middle;">'
        '<div style="color:#ffffff;font-size:15px;font-weight:700;letter-spacing:.2px;">'
        'Harmony &#215; Hariom</div>'
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

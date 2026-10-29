"""Text + HTML views of a stored message, for chat-style threads.

Our own outgoing mails (PO follow-ups, credentials, customer replies) carry the
branded HTML in ``body_html``; threads show that as the real email. Inbound mail
whose only part was text/html lands the raw HTML in ``body`` (see
mail_fetch_worker._extract_body) — that is detected here too, so it renders
instead of showing tags. The frontend renders ``html`` in a sandboxed iframe
(no scripts), so it is never injected into the app page.
"""
from __future__ import annotations

import re
from html import unescape
from typing import Any

_TAG_RE = re.compile(r"<[^>]+>")
_BLOCK_RE = re.compile(r"(?is)<(script|style|head)\b.*?</\1\s*>")
_LOOKS_HTML_RE = re.compile(r"(?i)<\s*(html|body|div|table|p|br|span|td|font|a)\b[^>]*>")


def looks_like_html(text: str | None) -> bool:
    return bool(text) and bool(_LOOKS_HTML_RE.search(text or ""))


def html_to_text(html: str) -> str:
    text = _BLOCK_RE.sub(" ", html)
    text = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|li|h[1-6])\s*>", "\n", text)
    text = unescape(_TAG_RE.sub(" ", text))
    lines = [re.sub(r"[ \t\xa0]+", " ", ln).strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln).strip()


def text_and_html(message: Any) -> tuple[str, str | None]:
    """(plain text for previews/search, HTML to render or None)."""
    body = (getattr(message, "body", None) or "").strip()
    html = (getattr(message, "body_html", None) or "").strip() or None
    if html is None and looks_like_html(body):
        html, body = body, ""
    if not body and html:
        body = html_to_text(html)
    return body, html

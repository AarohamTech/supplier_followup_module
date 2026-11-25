"""Inbound multipart mail keeps its HTML part (what the sender saw), minus quotes."""
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.workers.mail_fetch_worker import _extract_body, _extract_html


def _alt(text: str, html: str) -> MIMEMultipart:
    m = MIMEMultipart("alternative")
    m.attach(MIMEText(text, "plain"))
    m.attach(MIMEText(html, "html"))
    return m


def test_multipart_keeps_plain_body_and_html():
    m = _alt("*Email *: a@b.com", "<div><b>Email</b>: a@b.com</div>")
    assert _extract_body(m) == "*Email *: a@b.com"
    assert _extract_html(m) == "<div><b>Email</b>: a@b.com</div>"


def test_gmail_quote_is_cut():
    html = '<div dir="ltr">Dispatched today.</div><br><div class="gmail_quote">On Mon wrote: old</div>'
    assert _extract_html(_alt("Dispatched today.", html)) == '<div dir="ltr">Dispatched today.</div><br>'


def test_outlook_reply_header_is_cut():
    html = '<p>Noted.</p><div id="divRplyFwdMsg">From: us</div>'
    assert _extract_html(_alt("Noted.", html)) == "<p>Noted.</p>"


def test_single_part_has_no_separate_html():
    assert _extract_html(MIMEText("hello", "plain")) is None

"""Threads show emails as they actually looked: stored body_html is passed
through, raw HTML that landed in `body` is detected, plain chat stays plain."""
import unittest
from types import SimpleNamespace

from app.services.message_html import text_and_html


class MessageHtmlTests(unittest.TestCase):
    def test_branded_outgoing_mail_keeps_text_and_html(self):
        m = SimpleNamespace(body="Dear supplier, please confirm.", body_html="<table><tr><td>PO</td></tr></table>")
        self.assertEqual(text_and_html(m), ("Dear supplier, please confirm.", "<table><tr><td>PO</td></tr></table>"))

    def test_html_only_mail_gets_a_text_fallback(self):
        m = SimpleNamespace(body="", body_html="<style>x{}</style><p>Hello&nbsp;there</p><p>Line 2</p>")
        text, html = text_and_html(m)
        self.assertEqual(text, "Hello there\nLine 2")
        self.assertIn("<p>Hello", html)

    def test_raw_html_in_body_is_rendered_not_shown_as_tags(self):
        m = SimpleNamespace(body="<html><body><div>Dispatch on <b>Friday</b></div></body></html>", body_html=None)
        text, html = text_and_html(m)
        self.assertEqual(text, "Dispatch on Friday")
        self.assertTrue(html.startswith("<html>"))

    def test_plain_chat_message_stays_plain(self):
        m = SimpleNamespace(body="Will dispatch 5 < 10 units tomorrow", body_html=None)
        self.assertEqual(text_and_html(m), ("Will dispatch 5 < 10 units tomorrow", None))


if __name__ == "__main__":
    unittest.main()

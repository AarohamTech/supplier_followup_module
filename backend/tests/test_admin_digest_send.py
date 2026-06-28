import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

from app.services import admin_digest_service as svc

# 2026-06-27 04:00 UTC == 09:30 IST (after send_hour=9)
AFTER = datetime(2026, 6, 27, 4, 0)
# 2026-06-27 02:00 UTC == 07:30 IST (before send_hour=9)
BEFORE = datetime(2026, 6, 27, 2, 0)

BASE_CFG = {
    "enabled": True, "recipients": ["a@x.com"], "send_hour": 9, "timezone": "Asia/Kolkata",
    "sections": {"counts": True, "summary": False, "critical": False, "heated": False,
                 "risk": False, "overdue": False},
    "limits": {"critical": 10, "heated": 5, "risk": 10, "overdue": 15}, "last_sent_date": None,
}


def _cfg(**over):
    c = {**BASE_CFG, **over}
    return c


class SendIfDueTests(unittest.TestCase):
    def _patches(self, cfg):
        return (
            patch.object(svc.settings_service, "get_admin_digest", return_value=cfg),
            patch.object(svc.settings_service, "mark_admin_digest_sent"),
            patch.object(svc, "build_digest_data", return_value={"generated_at_local": "27 June 2026 · 09:30 IST"}),
            patch.object(svc, "render_digest_html", return_value="<html></html>"),
            patch.object(svc, "digest_subject", return_value="Harmony Intelligence Summary — 27 June 2026"),
            patch.object(svc.settings, "SMTP_ENABLED", True),
        )

    def test_skips_when_disabled(self):
        with patch.object(svc.settings_service, "get_admin_digest", return_value=_cfg(enabled=False)):
            out = svc.send_digest_if_due(MagicMock(), now=AFTER)
        self.assertIn("skipped", out)

    def test_skips_when_no_recipients(self):
        with patch.object(svc.settings_service, "get_admin_digest", return_value=_cfg(recipients=[])):
            out = svc.send_digest_if_due(MagicMock(), now=AFTER)
        self.assertEqual(out["skipped"], "no recipients")

    def test_skips_before_send_hour(self):
        with patch.object(svc.settings_service, "get_admin_digest", return_value=_cfg()), \
             patch.object(svc.settings, "SMTP_ENABLED", True):
            out = svc.send_digest_if_due(MagicMock(), now=BEFORE)
        self.assertEqual(out["skipped"], "before send_hour")

    def test_skips_when_already_sent_today(self):
        with patch.object(svc.settings_service, "get_admin_digest",
                          return_value=_cfg(last_sent_date="2026-06-27")), \
             patch.object(svc.settings, "SMTP_ENABLED", True):
            out = svc.send_digest_if_due(MagicMock(), now=AFTER)
        self.assertEqual(out["skipped"], "already sent today")

    def test_sends_and_marks_when_due(self):
        cfg = _cfg()
        p = self._patches(cfg)
        with p[0], p[1] as mark, p[2], p[3], p[4], p[5], \
             patch.object(svc.mail_send_worker, "send_html_email",
                          return_value={"sent": True, "recipients": 1, "reason": ""}) as send:
            out = svc.send_digest_if_due(MagicMock(), now=AFTER)
        self.assertEqual(out["sent"], 1)
        send.assert_called_once()
        mark.assert_called_once_with(unittest.mock.ANY, "2026-06-27")

    def test_does_not_mark_when_send_fails(self):
        cfg = _cfg()
        p = self._patches(cfg)
        with p[0], p[1] as mark, p[2], p[3], p[4], p[5], \
             patch.object(svc.mail_send_worker, "send_html_email",
                          return_value={"sent": False, "recipients": 0, "reason": "smtp down"}):
            out = svc.send_digest_if_due(MagicMock(), now=AFTER)
        self.assertIn("error", out)
        mark.assert_not_called()

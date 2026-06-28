import unittest

from app.services import admin_digest_service as svc

CFG = {
    "sections": {"counts": True, "summary": True, "critical": True,
                 "heated": False, "risk": True, "overdue": True},
    "limits": {"critical": 10, "heated": 5, "risk": 10, "overdue": 15},
    "timezone": "Asia/Kolkata", "send_hour": 9,
}

DATA = {
    "generated_at_local": "27 June 2026 · 09:00 IST",
    "counts": {"active": 418, "open_followups": 63, "overdue": 17, "critical": 12,
               "new_replies": 9, "signals": {"GREEN": 291, "YELLOW": 84, "RED": 31, "BLACK": 12}},
    "summary": "Twelve critical POs need attention.",
    "critical": [{"po": "HO-PO-1", "supplier": "Shree Steel", "material": "Flange",
                  "signal": "Black", "days_late": 19, "risk": 96}],
    "heated": [{"supplier": "Shree Steel", "po": "HO-PO-1", "tone": "Frustrated",
                "score": 0.88, "msg_count": 14, "recent_count": 5, "quote": "stop emailing"}],
    "risk": [{"po": "HO-PO-2", "supplier": "Metro", "reason": "no date", "score": 84}],
    "overdue": [{"po": "HO-PO-1", "supplier": "Shree", "shipment": "08 Jun",
                 "status": "Overdue", "days_late": 19}],
}


class RenderTests(unittest.TestCase):
    def test_title_and_brand_present(self):
        html = svc.render_digest_html(DATA, CFG)
        self.assertIn("Harmony Intelligence Summary", html)
        self.assertIn("#E11D2E", html)
        self.assertIn("418", html)            # a count rendered

    def test_disabled_section_omitted(self):
        html = svc.render_digest_html(DATA, CFG)
        self.assertNotIn("Heated conversations", html)   # heated disabled in CFG
        self.assertIn("Most critical", html)             # critical enabled

    def test_subject_uses_date(self):
        self.assertEqual(svc.digest_subject(DATA),
                         "Harmony Intelligence Summary — 27 June 2026")

    def test_no_emoji_or_arrows(self):
        html = svc.render_digest_html(DATA, CFG)
        for ch in ("✨", "→", "↗", "🔥"):
            self.assertNotIn(ch, html)

    def test_empty_data_section_omitted(self):
        data = dict(DATA, critical=[])           # critical enabled in CFG but no data
        html = svc.render_digest_html(data, CFG)
        self.assertNotIn("Most critical", html)  # section omitted when data is empty

import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services import admin_digest_service as svc


class HeatedAndSummaryTests(unittest.TestCase):
    def test_ai_summary_falls_back_when_disabled(self):
        counts = {"active": 100, "critical": 5, "overdue": 9,
                  "signals": {"GREEN": 70, "YELLOW": 16, "RED": 9, "BLACK": 5},
                  "open_followups": 12, "new_replies": 3}
        with patch.object(svc.ai_service, "is_enabled", return_value=False):
            text = svc._ai_summary(counts, critical=[], heated=[])
        self.assertIn("5", text)         # mentions critical count
        self.assertIn("overdue", text.lower())
        self.assertTrue(len(text) > 0)

    def test_ai_summary_uses_llm_when_enabled(self):
        counts = {"active": 1, "critical": 1, "overdue": 1,
                  "signals": {"GREEN": 0, "YELLOW": 0, "RED": 0, "BLACK": 1},
                  "open_followups": 0, "new_replies": 0}
        with patch.object(svc.ai_service, "is_enabled", return_value=True), \
             patch.object(svc.ai_service, "complete_json",
                          return_value={"summary": "LLM written paragraph."}) as cj:
            text = svc._ai_summary(counts, critical=[], heated=[])
        self.assertEqual(text, "LLM written paragraph.")
        cj.assert_called_once()

    def test_ai_summary_survives_llm_exception(self):
        counts = {"active": 1, "critical": 0, "overdue": 0,
                  "signals": {"GREEN": 1, "YELLOW": 0, "RED": 0, "BLACK": 0},
                  "open_followups": 0, "new_replies": 0}
        with patch.object(svc.ai_service, "is_enabled", return_value=True), \
             patch.object(svc.ai_service, "complete_json", side_effect=RuntimeError("boom")):
            text = svc._ai_summary(counts, critical=[], heated=[])
        self.assertTrue(len(text) > 0)   # fell back, no raise

    def test_score_tone_falls_back_to_heuristic_on_llm_exception(self):
        candidate = SimpleNamespace(supplier_po_no="PO-1", supplier_name="Acme",
                                    msg_count=4, recent_count=4, escalation_level="NONE")
        last = SimpleNamespace(body="we are very upset", direction="INCOMING",
                               received_at=datetime.utcnow())
        db = MagicMock()
        db.scalars.return_value.first.return_value = last
        with patch.object(svc.ai_service, "is_enabled", return_value=True), \
             patch.object(svc.ai_service, "complete_json", side_effect=RuntimeError("boom")):
            tone, score, quote = svc._score_tone(db, candidate)
        self.assertEqual(tone, "tense")   # heuristic: recent_count >= 3
        self.assertTrue(0 <= score <= 1)
        self.assertEqual(quote, "we are very upset")

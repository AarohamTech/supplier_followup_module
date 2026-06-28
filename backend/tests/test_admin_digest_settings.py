import unittest
from unittest.mock import MagicMock

from app.services import settings_service as svc


class AdminDigestSettingsTests(unittest.TestCase):
    def _db_with(self, stored):
        """A MagicMock db whose AppSetting row .value is `stored` (or None)."""
        db = MagicMock()
        row = None if stored is None else MagicMock(value=dict(stored))
        db.get.return_value = row
        return db, row

    def test_get_returns_full_defaults_when_unset(self):
        db, _ = self._db_with(None)
        cfg = svc.get_admin_digest(db)
        self.assertFalse(cfg["enabled"])
        self.assertEqual(cfg["recipients"], [])
        self.assertEqual(cfg["send_hour"], 9)
        self.assertEqual(cfg["timezone"], "Asia/Kolkata")
        self.assertTrue(cfg["sections"]["critical"])
        self.assertEqual(cfg["limits"]["critical"], 10)
        self.assertIsNone(cfg["last_sent_date"])

    def test_get_merges_stored_over_defaults(self):
        db, _ = self._db_with({"enabled": True, "recipients": ["a@x.com"], "send_hour": 7})
        cfg = svc.get_admin_digest(db)
        self.assertTrue(cfg["enabled"])
        self.assertEqual(cfg["recipients"], ["a@x.com"])
        self.assertEqual(cfg["send_hour"], 7)
        # untouched keys still defaulted
        self.assertTrue(cfg["sections"]["overdue"])

    def test_set_sanitizes_and_clamps(self):
        db, _ = self._db_with(None)
        out = svc.set_admin_digest(db, {
            "send_hour": 99, "recipients": ["a@x.com", "bad", "b@y.com", 5],
            "limits": {"critical": -3, "heated": 4},
        })
        self.assertEqual(out["send_hour"], 23)          # clamped 0..23
        self.assertEqual(out["recipients"], ["a@x.com", "b@y.com"])  # invalid dropped
        self.assertEqual(out["limits"]["critical"], 1)  # min 1
        self.assertEqual(out["limits"]["heated"], 4)
        db.commit.assert_called_once()

    def test_mark_sent_writes_only_last_sent_date(self):
        db, _ = self._db_with({"enabled": True})
        svc.mark_admin_digest_sent(db, "2026-06-27")
        cfg = svc.get_admin_digest(db)
        self.assertEqual(cfg["last_sent_date"], "2026-06-27")
        db.commit.assert_called()

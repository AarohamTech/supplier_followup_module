import unittest
from unittest.mock import MagicMock, patch

from app.routers import settings as settings_router


class AdminDigestRouteTests(unittest.TestCase):
    def test_get_returns_config(self):
        db = MagicMock()
        with patch.object(settings_router.settings_service, "get_admin_digest",
                          return_value={"enabled": False, "recipients": []}):
            out = settings_router.get_admin_digest_settings(db=db)
        self.assertIn("admin_digest", out)
        self.assertFalse(out["admin_digest"]["enabled"])

    def test_put_persists_partial_update(self):
        db = MagicMock()
        payload = settings_router.AdminDigestUpdate(enabled=True, recipients=["a@x.com"])
        with patch.object(settings_router.settings_service, "set_admin_digest",
                          return_value={"enabled": True, "recipients": ["a@x.com"]}) as setter:
            out = settings_router.update_admin_digest_settings(payload, db=db)
        setter.assert_called_once_with(db, {"enabled": True, "recipients": ["a@x.com"]})
        self.assertTrue(out["admin_digest"]["enabled"])

    def test_test_endpoint_sends_to_caller(self):
        db = MagicMock()
        user = MagicMock(email="me@hariom.com")
        with patch.object(settings_router.admin_digest_service, "send_test_digest",
                          return_value={"sent": True, "recipients": 1}) as send:
            out = settings_router.send_admin_digest_test(db=db, current_user=user)
        send.assert_called_once_with(db, "me@hariom.com")
        self.assertTrue(out["sent"])

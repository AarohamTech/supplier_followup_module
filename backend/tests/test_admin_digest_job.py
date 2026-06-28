import unittest
from unittest.mock import patch

from app.scheduler import jobs


class AdminDigestJobTests(unittest.TestCase):
    def test_spec_registered(self):
        names = [s.job_name for s in jobs.JOB_SPECS]
        self.assertIn("admin_digest_cron", names)
        spec = next(s for s in jobs.JOB_SPECS if s.job_name == "admin_digest_cron")
        self.assertEqual(spec.default_interval_minutes, 15)
        self.assertEqual(spec.runner, jobs.admin_digest_runner)

    def test_runner_delegates_to_service(self):
        with patch("app.scheduler.jobs.SessionLocal") as SL, \
             patch("app.services.admin_digest_service.send_digest_if_due",
                   return_value={"sent": 2}) as send:
            out = jobs.admin_digest_runner()
        self.assertEqual(out, {"sent": 2})
        send.assert_called_once()
        SL.return_value.close.assert_called_once()

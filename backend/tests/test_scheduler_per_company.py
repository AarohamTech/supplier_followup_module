import unittest
from unittest.mock import patch

from app.scheduler import jobs


class PerCompanyRunnerTests(unittest.TestCase):
    def test_active_companies_fallback_to_default(self):
        with patch.object(jobs, "_list_active_companies", side_effect=Exception("boom")):
            companies = jobs._active_companies()
        assert ("102", "public", True) in companies

    def test_crm_runner_loops_companies_and_wraps_schema(self):
        seen = []

        def fake_poll(db, cfg, *, desk_label=None, trigger="auto"):
            from app.core.tenant import get_current_schema
            seen.append((desk_label, get_current_schema()))
            return {"ok": True, "desk": desk_label}

        companies = [("102", "public", True), ("101", "company_101", False)]
        from app.services.crm_config import CrmConfig
        cfg = CrmConfig(base_url="http://x", desk_id="d", login_email="e", login_password="p", device_id="d")
        with patch.object(jobs, "_active_companies", return_value=companies), \
             patch.object(jobs.settings, "CRM_INGEST_ENABLED", True), \
             patch.object(jobs, "get_crm_config", return_value=cfg), \
             patch("app.services.crm_ingest_service.poll_and_ingest", side_effect=fake_poll):
            out = jobs.crm_ingestion_runner()
        assert dict(seen)["102"] == "public"
        assert dict(seen)["101"] == "company_101"
        assert set(out.keys()) == {"102", "101"}

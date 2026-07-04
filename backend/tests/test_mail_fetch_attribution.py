import unittest
from unittest.mock import patch

from app.workers import mail_fetch_worker as f


class AttributionTests(unittest.TestCase):
    def test_resolves_default_when_unknown(self):
        with patch.object(f, "_active_companies", return_value=[("102", "public", True), ("101", "company_101", False)]), \
             patch("app.services.communication_message_service.find_supplier_by_email", return_value=(None, None)):
            assert f.resolve_company_schema_for_sender("nobody@x.com") == "public"

    def test_routes_to_company_owning_the_sender(self):
        def fake_find(db, email):
            from app.core.tenant import get_current_schema
            if get_current_schema() == "company_101":
                return (5, "ACME 101")
            return (None, None)

        with patch.object(f, "_active_companies", return_value=[("102", "public", True), ("101", "company_101", False)]), \
             patch("app.services.communication_message_service.find_supplier_by_email", side_effect=fake_find):
            assert f.resolve_company_schema_for_sender("orders@acme101.com") == "company_101"

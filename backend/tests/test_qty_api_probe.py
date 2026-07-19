"""The Hariom quantity-API probe: per-variant verdicts and the admin route.

The newer CRM desk API (`api/crmappservices/getpendinguserdesk`) carries the
receipt quantities (PoQty/GrnQty/PendQty) that the classic pending-desk feed
lacks (verified 2026-07-10 — it was LAN-only inside Hariom). The probe re-checks
it from the server — the only host the CRM accepts calls from — so the admin
panel shows the moment Hariom IT exposes it publicly.
"""
import os
os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_qty_probe.sqlite")

import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.main as main_mod
from app.database import Base, get_db
from app.services import company_service, user_service
from app.services import crm_ingest_service as ingest
from app.services.crm_config import CrmConfig

CFG = CrmConfig(
    base_url="http://crm.example:8599", desk_id="102",
    login_email="x@y.z", login_password="pw", device_id="102",
)


def _resp(status=200, payload=None):
    m = MagicMock()
    m.status_code = status
    m.json.return_value = payload
    return m


class ProbeTests(unittest.TestCase):
    def test_all_variants_not_found(self):
        with patch.object(ingest, "get_token", return_value="tok"), \
             patch.object(ingest.requests, "get", return_value=_resp(404)) as fake:
            out = ingest.probe_qty_api(CFG)
        self.assertTrue(out.startswith("qty-api probe:"))
        self.assertEqual(out.count("HTTP 404"), len(ingest.QTY_API_VARIANTS))
        for call in fake.call_args_list:
            self.assertTrue(call.args[0].startswith("http://crm.example:8599/api/"))
        # the confirmed-public pending-PO-list endpoint is probed first
        self.assertIn("getpendingpolist/102", fake.call_args_list[0].args[0])

    def test_live_variant_reports_rows_and_qty_keys(self):
        rows = [{"TrnNo": "1", "PoQty": 5, "GrnQty": 2, "PendQty": 3, "PoType": "Basic"}] * 2
        with patch.object(ingest, "get_token", return_value="tok"), \
             patch.object(ingest.requests, "get", return_value=_resp(200, {"Data": rows})):
            out = ingest.probe_qty_api(CFG)
        self.assertIn("HTTP 200 rows=2", out)
        self.assertIn("qty_keys=PoQty,GrnQty,PendQty,PoType", out)

    def test_unreachable_is_reported_not_raised(self):
        with patch.object(ingest, "get_token", return_value="tok"), \
             patch.object(ingest.requests, "get", side_effect=ConnectionError("boom")):
            out = ingest.probe_qty_api(CFG)
        self.assertEqual(out.count("unreachable (ConnectionError)"), len(ingest.QTY_API_VARIANTS))


class RouteTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool, future=True
        )
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)
        self.db = self.Session()
        company_service.seed_companies(self.db)
        main_mod.app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(main_mod.app)

    def tearDown(self):
        main_mod.app.dependency_overrides.clear()
        self.db.close()
        self.engine.dispose()

    def _token(self, email, role):
        user_service.create_user(self.db, email=email, password="secret123", full_name=role, role=role)
        r = self.client.post("/api/auth/login", json={"email": email, "password": "secret123"})
        return r.json()["access_token"]

    def test_probe_route_is_admin_only_and_reports_live(self):
        admin = self._token("admin@x.com", "admin")
        manager = self._token("mgr@x.com", "manager")

        with patch("app.routers.procurement._current_crm_config", return_value=CFG), \
             patch.object(ingest, "probe_qty_api", return_value="qty-api probe: v -> HTTP 200 rows=1 qty_keys=PoQty"):
            ok = self.client.get(
                "/api/procurement/crm-quantity-api-probe",
                headers={"Authorization": f"Bearer {admin}"},
            )
            blocked = self.client.get(
                "/api/procurement/crm-quantity-api-probe",
                headers={"Authorization": f"Bearer {manager}"},
            )
        self.assertEqual(ok.status_code, 200, ok.text)
        self.assertTrue(ok.json()["live"])
        self.assertIn("HTTP 200", ok.json()["result"])
        self.assertEqual(blocked.status_code, 403, blocked.text)

    def test_probe_route_without_crm_config(self):
        admin = self._token("admin2@x.com", "admin")
        with patch("app.routers.procurement._current_crm_config", return_value=None):
            r = self.client.get(
                "/api/procurement/crm-quantity-api-probe",
                headers={"Authorization": f"Bearer {admin}"},
            )
        self.assertEqual(r.status_code, 503, r.text)


if __name__ == "__main__":
    unittest.main()

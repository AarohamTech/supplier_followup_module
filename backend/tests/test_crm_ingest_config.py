import unittest
from unittest.mock import patch

from app.services import crm_ingest_service as ingest
from app.services.crm_config import CrmConfig


CFG_A = CrmConfig(base_url="http://a", desk_id="101", login_email="a@x", login_password="pa", device_id="101")
CFG_B = CrmConfig(base_url="http://b", desk_id="102", login_email="b@x", login_password="pb", device_id="102")


class CrmTokenCacheTests(unittest.TestCase):
    def setUp(self):
        ingest._token_caches.clear()

    def test_token_cache_is_per_config(self):
        calls = []

        def fake_login(cfg):
            calls.append(cfg.login_email)
            return "tok-" + cfg.login_email

        with patch.object(ingest, "_login", side_effect=fake_login), \
             patch.object(ingest, "_token_exp", return_value=0.0):
            t1 = ingest.get_token(CFG_A)
            t1b = ingest.get_token(CFG_A)
            t2 = ingest.get_token(CFG_B)
        assert t1 == "tok-a@x" and t1b == "tok-a@x"
        assert t2 == "tok-b@x"
        assert calls == ["a@x", "b@x"]


class CrmUpsertPortabilityTests(unittest.TestCase):
    def test_upsert_conflict_targets_columns_not_constraint_name(self):
        import inspect
        src = inspect.getsource(ingest._bulk_upsert)
        assert 'index_elements=["crm_no", "supplier_po_no", "material_name"]' in src \
            or "index_elements=['crm_no', 'supplier_po_no', 'material_name']" in src
        assert 'constraint="uq_procurement_match_latest"' not in src

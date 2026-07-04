import os
import unittest
from unittest.mock import patch

from app.services.crm_config import CrmConfig, get_crm_config


class CrmConfigTests(unittest.TestCase):
    def test_non_default_reads_prefixed_env(self):
        env = {
            "CRM_101_DESK_ID": "101",
            "CRM_101_LOGIN_EMAIL": "e101@x.com",
            "CRM_101_LOGIN_PASSWORD": "secret101",
            "CRM_101_BASE_URL": "http://crm.example:8599",
        }
        with patch.dict(os.environ, env, clear=False):
            cfg = get_crm_config("101", is_default=False)
        assert isinstance(cfg, CrmConfig)
        assert cfg.desk_id == "101"
        assert cfg.login_email == "e101@x.com"
        assert cfg.login_password == "secret101"
        assert cfg.base_url == "http://crm.example:8599"
        assert cfg.device_id == "101"

    def test_incomplete_config_returns_none(self):
        with patch.dict(os.environ, {"CRM_101_DESK_ID": "101"}, clear=False):
            assert get_crm_config("101", is_default=False) is None

    def test_default_company_uses_legacy_settings(self):
        from app.services import crm_config as mod
        with patch.object(mod.settings, "CRM_DESK_ID", "102"), \
             patch.object(mod.settings, "CRM_LOGIN_EMAIL", "e102@x.com"), \
             patch.object(mod.settings, "CRM_LOGIN_PASSWORD", "secret102"), \
             patch.object(mod.settings, "CRM_API_BASE_URL", "http://crm.example:8599"), \
             patch.object(mod.settings, "CRM_DEVICE_ID", "102"):
            cfg = get_crm_config("102", is_default=True)
        assert cfg is not None
        assert cfg.desk_id == "102"
        assert cfg.login_email == "e102@x.com"

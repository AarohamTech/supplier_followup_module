import os
import unittest
from unittest.mock import patch

from app.services import crm_config as mod
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

    def test_non_default_inherits_shared_login_needs_only_desk_id(self):
        # Same CRM account as 102 (shared login/token), different desk. Only
        # CRM_<CODE>_DESK_ID is required; email/password/base inherit from settings.
        env = {
            "CRM_101_DESK_ID": "101",
            "CRM_101_LOGIN_EMAIL": "",
            "CRM_101_LOGIN_PASSWORD": "",
            "CRM_101_BASE_URL": "",
            "CRM_101_DEVICE_ID": "",
        }
        with patch.dict(os.environ, env, clear=False), \
             patch.object(mod.settings, "CRM_LOGIN_EMAIL", "shared@x.com"), \
             patch.object(mod.settings, "CRM_LOGIN_PASSWORD", "sharedpw"), \
             patch.object(mod.settings, "CRM_API_BASE_URL", "http://crm.example:8599"):
            cfg = get_crm_config("101", is_default=False)
        assert cfg is not None
        assert cfg.desk_id == "101"                       # its own desk
        assert cfg.login_email == "shared@x.com"          # inherited from 102
        assert cfg.login_password == "sharedpw"           # inherited from 102
        assert cfg.base_url == "http://crm.example:8599"  # inherited
        assert cfg.device_id == "101"                     # defaults to desk id

    def test_returns_none_without_desk_id(self):
        # Desk id is the one thing a non-default company must supply.
        env = {
            "CRM_101_DESK_ID": "",
            "CRM_101_LOGIN_EMAIL": "",
            "CRM_101_LOGIN_PASSWORD": "",
            "CRM_101_BASE_URL": "",
        }
        with patch.dict(os.environ, env, clear=False), \
             patch.object(mod.settings, "CRM_LOGIN_EMAIL", "shared@x.com"), \
             patch.object(mod.settings, "CRM_LOGIN_PASSWORD", "sharedpw"), \
             patch.object(mod.settings, "CRM_API_BASE_URL", "http://crm.example:8599"):
            assert get_crm_config("101", is_default=False) is None

    def test_returns_none_when_no_login_anywhere(self):
        env = {"CRM_101_DESK_ID": "101", "CRM_101_LOGIN_EMAIL": "", "CRM_101_LOGIN_PASSWORD": ""}
        with patch.dict(os.environ, env, clear=False), \
             patch.object(mod.settings, "CRM_LOGIN_EMAIL", ""), \
             patch.object(mod.settings, "CRM_LOGIN_PASSWORD", ""), \
             patch.object(mod.settings, "CRM_API_BASE_URL", "http://crm.example:8599"):
            assert get_crm_config("101", is_default=False) is None

    def test_reads_per_company_desk_from_env_file_not_os_environ(self):
        # Regression: the app loads .env into `settings` (pydantic), NOT into
        # os.environ. Per-company CRM vars must be read from the .env FILE — else a
        # box whose .env has CRM_101_DESK_ID would never actually ingest 101.
        import pathlib
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            envp = pathlib.Path(d) / ".env"
            envp.write_text("CRM_101_DESK_ID=101\n")
            with patch.dict(os.environ, {}, clear=False), \
                 patch.object(mod, "ENV_FILE", envp), \
                 patch.object(mod.settings, "CRM_LOGIN_EMAIL", "shared@x.com"), \
                 patch.object(mod.settings, "CRM_LOGIN_PASSWORD", "sharedpw"), \
                 patch.object(mod.settings, "CRM_API_BASE_URL", "http://crm.example:8599"):
                os.environ.pop("CRM_101_DESK_ID", None)  # ensure it is NOT a process env var
                cfg = get_crm_config("101", is_default=False)
        assert cfg is not None
        assert cfg.desk_id == "101"                # read from the .env FILE
        assert cfg.login_email == "shared@x.com"   # inherited from shared settings

    def test_default_company_uses_legacy_settings(self):
        with patch.object(mod.settings, "CRM_DESK_ID", "102"), \
             patch.object(mod.settings, "CRM_LOGIN_EMAIL", "e102@x.com"), \
             patch.object(mod.settings, "CRM_LOGIN_PASSWORD", "secret102"), \
             patch.object(mod.settings, "CRM_API_BASE_URL", "http://crm.example:8599"), \
             patch.object(mod.settings, "CRM_DEVICE_ID", "102"):
            cfg = get_crm_config("102", is_default=True)
        assert cfg is not None
        assert cfg.desk_id == "102"
        assert cfg.login_email == "e102@x.com"

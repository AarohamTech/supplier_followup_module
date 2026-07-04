"""Regression test for the manual CRM-sync cross-tenant bug.

`poll_and_ingest(db, cfg=None, ...)` must resolve the CRM config for the
CURRENT tenant (ambient schema), not hard-code the legacy 102 desk. Otherwise
a manual sync triggered under a non-default company (e.g. 101 / company_101)
would fetch 102's feed with 102's credentials and write 102's POs into the
wrong schema.
"""
from __future__ import annotations

import os
import unittest
from contextlib import contextmanager
from unittest.mock import patch

# Force a throwaway SQLite DB before importing app modules.
os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_crm_tenant_resolve.sqlite")

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.database import Base  # noqa: E402
from app.services import company_service  # noqa: E402
from app.services import crm_ingest_service as ingest  # noqa: E402


@contextmanager
def _temp_db():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = Session()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


class CrmIngestTenantResolveTests(unittest.TestCase):
    def test_non_default_tenant_without_creds_does_not_fetch_default_feed(self):
        """Under company_101 (no CRM_101_* creds), poll_and_ingest must NOT fall
        back to 102's config/feed — it should return DISABLED and never call
        fetch_desk.

        The 102 (default) creds are deliberately patched to *valid* values here
        so that, under the pre-fix code (which hard-codes `is_default=True`
        regardless of the ambient tenant), `get_crm_config` would resolve
        successfully and `fetch_desk` WOULD be called — reproducing the
        cross-tenant bug. After the fix, the non-default schema must resolve
        company 101's (unset) CRM_101_* creds instead, yielding no config."""
        with _temp_db() as db:
            company_service.seed_companies(db)  # creates 101 (company_101) + 102 (public)
            with patch("app.core.tenant.get_current_schema", return_value="company_101"), \
                 patch.object(ingest.settings, "CRM_INGEST_ENABLED", True), \
                 patch.object(ingest.settings, "CRM_DESK_ID", "102"), \
                 patch.object(ingest.settings, "CRM_LOGIN_EMAIL", "e@x"), \
                 patch.object(ingest.settings, "CRM_LOGIN_PASSWORD", "p"), \
                 patch.object(ingest.settings, "CRM_API_BASE_URL", "http://crm"), \
                 patch.object(ingest, "fetch_desk", side_effect=AssertionError("must not fetch")):
                result = ingest.poll_and_ingest(db)  # cfg=None
            self.assertEqual(result["status"], "DISABLED")

    def test_default_tenant_resolves_102_config_and_fetches(self):
        """Under the default schema (public / 102), poll_and_ingest must resolve
        the legacy 102 config from CRM_* settings and DOES fetch its feed."""
        with _temp_db() as db:
            company_service.seed_companies(db)
            with patch("app.core.tenant.get_current_schema", return_value="public"), \
                 patch.object(ingest.settings, "CRM_INGEST_ENABLED", True), \
                 patch.object(ingest.settings, "CRM_DESK_ID", "102"), \
                 patch.object(ingest.settings, "CRM_LOGIN_EMAIL", "e@x"), \
                 patch.object(ingest.settings, "CRM_LOGIN_PASSWORD", "p"), \
                 patch.object(ingest.settings, "CRM_API_BASE_URL", "http://crm"), \
                 patch.object(ingest, "fetch_desk", return_value=[]) as fake_fetch:
                result = ingest.poll_and_ingest(db)
            fake_fetch.assert_called_once()
            self.assertEqual(result["status"], "OK")


if __name__ == "__main__":
    unittest.main()

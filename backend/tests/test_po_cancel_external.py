"""Outbound PO-cancel request to the CRM/ERP: payload carries every original CRM
feed field per line, posts with the desk-feed bearer token, and never raises."""
import unittest
from contextlib import contextmanager
from datetime import date, datetime
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import ProcurementRecord
from app.services import po_cancel_service as pcs
from app.services.crm_config import CrmConfig


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


RAW = {
    "CRMNo": "2627-001703", "PoNo": "000449", "MaterialName": "BLIND SLEEVE",
    "PoShortRefTrnNo": "2627-001703", "PoRefTrnNo": "118262770111005059",
    "PoLongName": "VEDANT TOOLS PVT LTD", "PoStatus": "APPROVED", "Quantity": 1800,
    "LongName": "SHRIRAM FOUNDRY PVT LTD - DEWAS", "RefTrnNo": "119262770111000130",
    "DocType": "PO", "PoAmendNo": 0, "SomeUnmappedField": "kept verbatim",
}

CFG = CrmConfig(base_url="http://crm.test:8599/", desk_id="102", login_email="u@x",
                login_password="p", device_id="102")


def _row(db, *, crm="2627-001703", raw=None, **over):
    r = ProcurementRecord(
        crm_no=crm, material_name="BLIND SLEEVE", supplier_po_no="000449",
        supplier_name="VEDANT TOOLS PVT LTD", supplier_date=date(2026, 6, 14),
        po_short_ref="2627-001703", po_trn_no="118262770111005059", qty=1800,
        customer_name="SHRIRAM FOUNDRY PVT LTD - DEWAS", po_no="119262770111000130",
        po_date=date(2026, 6, 10), po_status="APPROVED", crm_raw=raw, owner_emp_code="E1",
        **over,
    )
    db.add(r)
    db.commit()
    return r


class PayloadTests(unittest.TestCase):
    def test_raw_feed_row_is_forwarded_verbatim(self):
        with _temp_db() as db:
            r = _row(db, raw=RAW)
            body = pcs.build_cancel_payload(
                [r], company_id="102", supplier_po_no="000449",
                supplier_name="VEDANT TOOLS PVT LTD", requested_by="E1", remark="dup",
                requested_at=datetime(2026, 9, 3, 10, 0),
            )
        self.assertEqual(body["CompanyId"], "102")
        self.assertEqual(body["PoShortRefTrnNo"], "2627-001703")
        self.assertEqual(body["RequestedAt"], "2026-09-03T10:00:00Z")
        line = body["Lines"][0]
        self.assertEqual(line["CrmNo"], "2627-001703")
        self.assertEqual(line["CustomerPoNo"], "119262770111000130")
        # every original field, including ones we never mapped to a column
        self.assertEqual(line["CrmFields"], RAW)
        self.assertEqual(line["CrmFields"]["SomeUnmappedField"], "kept verbatim")

    def test_legacy_rows_rebuild_the_crm_fields_from_columns(self):
        with _temp_db() as db:
            r = _row(db, raw=None)
            fields = pcs.crm_fields_for(r)
        self.assertEqual(fields["PoNo"], "000449")
        self.assertEqual(fields["PoShortRefTrnNo"], "2627-001703")
        self.assertEqual(fields["PoLongName"], "VEDANT TOOLS PVT LTD")
        self.assertEqual(fields["LongName"], "SHRIRAM FOUNDRY PVT LTD - DEWAS")
        self.assertEqual(fields["RefTrnNo"], "119262770111000130")
        self.assertEqual(fields["Quantity"], 1800.0)
        self.assertEqual(fields["PoRefTrnDate"], "2026-06-14")


class _Resp:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body
        self.text = str(body)

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


class OutboundTests(unittest.TestCase):
    def test_posts_to_crm_with_bearer_token_and_reports_success(self):
        calls = []

        def fake_post(url, json=None, headers=None, timeout=None):
            calls.append((url, json, headers))
            return _Resp(200, {"Status": "RECEIVED", "Message": ""})

        with _temp_db() as db:
            _row(db, raw=RAW)
            with (
                patch("app.services.crm_config.get_current_crm_config", return_value=CFG),
                patch("app.services.crm_ingest_service.get_token", return_value="tok123"),
                patch("requests.post", side_effect=fake_post),
            ):
                res = pcs.request_cancellation(
                    db, supplier_po_no="000449", supplier_name="VEDANT TOOLS PVT LTD",
                    requested_by="E1", remark="Material no longer required",
                )
        self.assertEqual(res["cancellation_status"], "PENDING")
        ext = res["external"]
        self.assertTrue(ext["raised"], ext)
        self.assertEqual(ext["status_code"], 200)
        self.assertEqual(ext["response"]["Status"], "RECEIVED")
        url, body, headers = calls[0]
        self.assertEqual(url, "http://crm.test:8599/api/crm/PoCancelRequest")
        self.assertEqual(headers["Authorization"], "Bearer tok123")
        self.assertEqual(body["Remark"], "Material no longer required")
        self.assertEqual(body["Lines"][0]["CrmFields"]["PoStatus"], "APPROVED")

    def test_401_forces_one_token_refresh(self):
        tokens = []
        responses = iter([_Resp(401, "expired"), _Resp(200, {"Status": "RECEIVED"})])

        def fake_token(cfg, force_refresh=False):
            tokens.append(force_refresh)
            return "t2" if force_refresh else "t1"

        with _temp_db() as db:
            r = _row(db, raw=RAW)
            with (
                patch("app.services.crm_config.get_current_crm_config", return_value=CFG),
                patch("app.services.crm_ingest_service.get_token", side_effect=fake_token),
                patch("requests.post", side_effect=lambda *a, **k: next(responses)),
            ):
                res = pcs.request_line_cancellation(db, record_id=r.id, requested_by="E1")
        self.assertTrue(res["external"]["raised"])
        self.assertEqual(tokens, [False, True])

    def test_network_failure_keeps_po_pending_and_never_raises(self):
        def boom(*a, **k):
            raise ConnectionError("ERP down")

        with _temp_db() as db:
            _row(db, raw=RAW)
            with (
                patch("app.services.crm_config.get_current_crm_config", return_value=CFG),
                patch("app.services.crm_ingest_service.get_token", return_value="tok"),
                patch("requests.post", side_effect=boom),
            ):
                res = pcs.request_cancellation(
                    db, supplier_po_no="000449", supplier_name="VEDANT TOOLS PVT LTD",
                    requested_by="E1",
                )
            self.assertEqual(res["cancellation_status"], "PENDING")
            self.assertFalse(res["external"]["raised"])
            self.assertIn("ERP down", res["external"]["reason"])
            row = db.query(ProcurementRecord).one()
            self.assertEqual(row.cancellation_status, "PENDING")

    def test_unconfigured_crm_reports_why_nothing_was_sent(self):
        with _temp_db() as db:
            _row(db, raw=RAW)
            with (
                patch("app.services.crm_config.get_current_crm_config", return_value=None),
                patch("requests.post") as post,
            ):
                res = pcs.request_cancellation(
                    db, supplier_po_no="000449", supplier_name="VEDANT TOOLS PVT LTD",
                    requested_by="E1",
                )
        post.assert_not_called()
        self.assertFalse(res["external"]["raised"])
        self.assertIn("not configured", res["external"]["reason"])


if __name__ == "__main__":
    unittest.main()

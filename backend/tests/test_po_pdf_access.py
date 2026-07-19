"""PO PDF download access: staff proxy + the employee-scoped eportal route.

The PDF must be reachable by every internal user type: any staff role hits
/api/procurement/po-pdf (router-level read RBAC), employees hit
/api/eportal/po-pdf which additionally enforces the own-PO boundary
(po_trn_no must belong to a line the employee owns).
"""
import os
import unittest
from contextlib import contextmanager
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_po_pdf.sqlite")

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.database import Base  # noqa: E402
from app.models import ProcurementRecord  # noqa: E402
from app.routers import employee_portal, procurement  # noqa: E402
from app.services import user_service  # noqa: E402
from app.services.crm_config import CrmConfig  # noqa: E402

CFG = CrmConfig(
    base_url="http://crm.example:8599", desk_id="102",
    login_email="x@y.z", login_password="pw", device_id="102",
)
TRN = "102262770111002342"


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


def _seed(db):
    e1 = user_service.create_user(
        db, email="e1@employee.local", password="pw", full_name="Owner One",
        role="employee", emp_code="E1", username="DESK1",
    )
    e2 = user_service.create_user(
        db, email="e2@employee.local", password="pw", full_name="Owner Two",
        role="employee", emp_code="E2", username="DESK2",
    )
    db.add(ProcurementRecord(
        crm_no="C1", supplier_po_no="PO-1", material_name="Drill",
        supplier_name="ACME", owner_emp_code="E1", po_trn_no=TRN,
    ))
    db.commit()
    return e1, e2


class EmployeePoPdfTests(unittest.TestCase):
    def test_owner_can_download(self):
        with _temp_db() as db:
            e1, _ = _seed(db)
            with patch("app.services.crm_config.get_current_crm_config", return_value=CFG), \
                 patch("app.services.crm_ingest_service.fetch_po_pdf",
                       return_value=(b"%PDF-fake", "application/pdf")) as fetch:
                resp = employee_portal.po_pdf(trn_no=TRN, user=e1, db=db)
        self.assertEqual(resp.body, b"%PDF-fake")
        self.assertIn("PO-", resp.headers["Content-Disposition"])
        fetch.assert_called_once_with(CFG, TRN, 0)

    def test_non_owner_gets_404(self):
        with _temp_db() as db:
            _, e2 = _seed(db)
            with patch("app.services.crm_ingest_service.fetch_po_pdf") as fetch:
                with self.assertRaises(HTTPException) as ctx:
                    employee_portal.po_pdf(trn_no=TRN, user=e2, db=db)
        self.assertEqual(ctx.exception.status_code, 404)
        fetch.assert_not_called()


class StaffPoPdfTests(unittest.TestCase):
    def test_staff_proxy_returns_pdf(self):
        with _temp_db() as db:
            with patch("app.routers.procurement._current_crm_config", return_value=CFG), \
                 patch("app.services.crm_ingest_service.fetch_po_pdf",
                       return_value=(b"%PDF-fake", "application/pdf")):
                resp = procurement.po_pdf(trn_no=TRN, amend_no=0, db=db)
        self.assertEqual(resp.body, b"%PDF-fake")

    def test_crm_failure_becomes_502(self):
        with _temp_db() as db:
            with patch("app.routers.procurement._current_crm_config", return_value=CFG), \
                 patch("app.services.crm_ingest_service.fetch_po_pdf",
                       side_effect=RuntimeError("CRM PO PDF fetch failed (500)")):
                with self.assertRaises(HTTPException) as ctx:
                    procurement.po_pdf(trn_no=TRN, amend_no=0, db=db)
        self.assertEqual(ctx.exception.status_code, 502)


if __name__ == "__main__":
    unittest.main()

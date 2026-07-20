"""PO PDF download access.

Client decision (2026-07-20): the official PO document is only for ADMINS and
the SUPPLIER it belongs to. The staff route is admin-gated at the route level,
the employee route no longer exists, and the supplier route enforces the
own-PO boundary (po_trn_no must belong to a line addressed to that supplier).
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
    def test_employee_route_no_longer_exists(self):
        # Client decision 2026-07-20: employees must NOT be able to fetch PO PDFs.
        self.assertFalse(hasattr(employee_portal, "po_pdf"))

    def test_staff_route_is_admin_gated(self):
        from app.routers.procurement import router as proc_router
        from app.core.deps import require_admin

        route = next(r for r in proc_router.routes if getattr(r, "path", "") == "/api/procurement/po-pdf")
        dep_calls = [d.dependency for d in getattr(route, "dependencies", [])]
        self.assertIn(require_admin, dep_calls)


class SupplierPoPdfTests(unittest.TestCase):
    def test_own_supplier_can_download_others_cannot(self):
        from app.models import SupplierMaster
        from app.routers import portal

        with _temp_db() as db:
            sup = SupplierMaster(supplier_name="ACME", is_active=True)
            other = SupplierMaster(supplier_name="OTHER", is_active=True)
            db.add_all([sup, other])
            db.commit()
            owner = user_service.create_user(
                db, email="sup@acme.local", password="pw", role="supplier", supplier_id=sup.id,
            )
            stranger = user_service.create_user(
                db, email="sup@other.local", password="pw", role="supplier", supplier_id=other.id,
            )
            db.add(ProcurementRecord(
                crm_no="C1", supplier_po_no="PO-1", material_name="Drill",
                supplier_name="ACME", po_trn_no=TRN,
            ))
            db.commit()

            with patch("app.services.crm_config.get_current_crm_config", return_value=CFG), \
                 patch("app.services.crm_ingest_service.fetch_po_pdf",
                       return_value=(b"%PDF-fake", "application/pdf")):
                resp = portal.po_pdf(trn_no=TRN, user=owner, db=db)
                self.assertEqual(resp.body, b"%PDF-fake")
                with self.assertRaises(HTTPException) as ctx:
                    portal.po_pdf(trn_no=TRN, user=stranger, db=db)
            self.assertEqual(ctx.exception.status_code, 404)


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

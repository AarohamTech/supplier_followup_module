"""Employee-scoped Black Follow-ups endpoints — security boundary tests.

Mirrors test_eportal_hub_scope.py: call the route functions directly with a
constructed employee User + Session. In-memory SQLite; prod data untouched.
Every endpoint must only ever surface / act on POs the employee owns
(ProcurementRecord.owner_emp_code == user.emp_code), else 404 / excluded.
"""
from __future__ import annotations

import os
import unittest
from contextlib import contextmanager

os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_eportal_black.sqlite")

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.core.roles import Role  # noqa: E402
from app.database import Base  # noqa: E402
from app.models import (  # noqa: E402,F401
    CommunicationMessage,
    CommunicationTask,
    MailHistory,
    Notification,
    ProcurementRecord,
    SupplierMaster,
    User,
)
from app.models.followup_attempt import FollowupAttempt  # noqa: E402,F401
from app.routers import ai_insights  # noqa: E402
from app.routers import employee_portal as ep  # noqa: E402
from app.services import followup_audit_service as audit  # noqa: E402
from app.services import user_service  # noqa: E402


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


def _emp(db, emp_code):
    return user_service.create_user(
        db, email=f"{emp_code}@corp.com", password="x" * 8, role=Role.EMPLOYEE,
        emp_code=emp_code, username=emp_code,
    )


def _po(db, *, po, name, owner, signal="BLACK"):
    rec = ProcurementRecord(
        crm_no=f"CRM-{po}", material_name="Widget", supplier_po_no=po,
        supplier_name=name, owner_emp_code=owner, signal=signal,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


class EmployeeBlackFollowupsScopeTests(unittest.TestCase):
    def test_black_followups_only_owned(self):
        with _temp_db() as db:
            emp1 = _emp(db, "EMP1")
            _po(db, po="PO-A1", name="ACME TOOLS", owner="EMP1", signal="BLACK")
            _po(db, po="PO-B1", name="BETA PARTS", owner="EMP2", signal="BLACK")
            out = ep.employee_black_followups(user=emp1, db=db)
            self.assertEqual({i["supplier_po_no"] for i in out["items"]}, {"PO-A1"})
            self.assertEqual(out["count"], 1)

    def test_followup_history_only_owned(self):
        with _temp_db() as db:
            emp1 = _emp(db, "EMP1")
            _po(db, po="PO-A1", name="ACME TOOLS", owner="EMP1", signal="BLACK")
            _po(db, po="PO-B1", name="BETA PARTS", owner="EMP2", signal="BLACK")
            audit.record(db, supplier_po_no="PO-A1", supplier_name="ACME TOOLS",
                         signal="BLACK", commit=True)
            audit.record(db, supplier_po_no="PO-B1", supplier_name="BETA PARTS",
                         signal="BLACK", commit=True)
            out = ep.employee_followup_history(user=emp1, db=db)
            self.assertEqual({i["supplier_po_no"] for i in out["items"]}, {"PO-A1"})

    def test_command_foreign_404(self):
        with _temp_db() as db:
            emp1 = _emp(db, "EMP1")
            _po(db, po="PO-B1", name="BETA PARTS", owner="EMP2", signal="BLACK")
            payload = ai_insights.FollowupCommand(
                supplier_po_no="PO-B1", instruction="chase it", send=False
            )
            with self.assertRaises(HTTPException) as cm:
                ep.employee_black_followup_command(payload, user=emp1, db=db)
            self.assertEqual(cm.exception.status_code, 404)

    def test_command_owned_preview_ok(self):
        with _temp_db() as db:
            emp1 = _emp(db, "EMP1")
            _po(db, po="PO-A1", name="ACME TOOLS", owner="EMP1", signal="BLACK")
            payload = ai_insights.FollowupCommand(
                supplier_po_no="PO-A1", instruction="ask for a firm dispatch date", send=False
            )
            out = ep.employee_black_followup_command(payload, user=emp1, db=db)
            self.assertTrue(out["found"])
            self.assertFalse(out["sent"])


if __name__ == "__main__":
    unittest.main()

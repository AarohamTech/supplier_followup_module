"""Staff scope on follow-ups, AI insights, AI chat tools, mail log/history and
ASNs (client 2026-11-25: only admin sees all). Route functions are called
directly with an explicit scope. In-memory SQLite; production data untouched."""
from __future__ import annotations

import os
import unittest
from contextlib import contextmanager

os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_staff_scope_misc.sqlite")

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.core.roles import Role  # noqa: E402
from app.database import Base  # noqa: E402
from app.models import CommunicationMessage, MailHistory, ProcurementRecord, User  # noqa: E402,F401
from app.models.asn import Asn  # noqa: E402
from app.models.followup_attempt import FollowupAttempt  # noqa: E402,F401
from app.models.supplier import SupplierMaster  # noqa: E402
from app.models.supplier_assignment import SupplierAssignment  # noqa: E402
from app.routers import ai_insights, asns, mail_history, mail_log, po_followups  # noqa: E402
from app.services import ai_tools_service, staff_scope, user_service  # noqa: E402
from app.services import followup_audit_service as audit  # noqa: E402


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


def _user(db, name, role, emp_code=None):
    return user_service.create_user(
        db, email=f"{name}@corp.com", password="x" * 8, role=role,
        emp_code=emp_code, username=name, full_name=name.title(),
    )


def _rec(db, po, name, owner=None, signal="RED"):
    rec = ProcurementRecord(
        crm_no=f"CRM-{po}-{name}", material_name="Bolt", supplier_po_no=po,
        supplier_name=name, owner_emp_code=owner, signal=signal,
        risk_score=80, risk_band="HIGH",
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


def _supplier(db, name):
    s = SupplierMaster(supplier_name=name, is_active=True)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


class StaffScopeMiscTests(unittest.TestCase):
    def setUp(self):
        self._cm = _temp_db()
        self.db = db = self._cm.__enter__()
        self.admin = _user(db, "admin", Role.ADMIN)
        self.vijay = _user(db, "vijay", Role.USER, emp_code="E2")
        self.acme = _supplier(db, "ACME")
        self.beta = _supplier(db, "BETA")
        self.gamma = _supplier(db, "GAMMA")
        self.r1 = _rec(db, "001", "ACME", owner="E2")
        # Same recycled counter, other supplier, other owner: must NOT leak.
        self.r2 = _rec(db, "001", "BETA", owner="E7")
        self.r3 = _rec(db, "002", "GAMMA", owner="E7", signal="BLACK")  # assigned supplier
        self.r4 = _rec(db, "003", "BETA", owner="E7")
        db.add(SupplierAssignment(supplier_id=self.gamma.id, user_id=self.vijay.id))
        db.commit()
        self.scope = staff_scope.for_user(db, self.vijay)
        assert staff_scope.for_user(db, self.admin) is None

    def tearDown(self):
        self._cm.__exit__(None, None, None)

    @staticmethod
    def _keys(items):
        return {(i["supplier_name"], i["supplier_po_no"]) for i in items}

    # ── PO follow-ups ────────────────────────────────────────────────────
    def test_groups_scoped(self):
        mine = po_followups.list_groups(
            signal=None, supplier_name=None, supplier_po_no=None, search=None,
            page=1, size=25, include_closed=True, db=self.db, scope=self.scope,
        )
        self.assertEqual(self._keys(mine["items"]), {("ACME", "001"), ("GAMMA", "002")})
        self.assertEqual(mine["total"], 2)
        allg = po_followups.list_groups(
            signal=None, supplier_name=None, supplier_po_no=None, search=None,
            page=1, size=25, include_closed=True, db=self.db, scope=None,
        )
        self.assertEqual(allg["total"], 4)

    def test_group_by_key_404_out_of_scope(self):
        with self.assertRaises(HTTPException) as cm:
            po_followups.group_by_key(
                supplier_name="BETA", supplier_po_no="001", include_closed=True,
                db=self.db, scope=self.scope,
            )
        self.assertEqual(cm.exception.status_code, 404)
        ok = po_followups.group_by_key(
            supplier_name="ACME", supplier_po_no="001", include_closed=True,
            db=self.db, scope=self.scope,
        )
        self.assertEqual(ok["supplier_name"], "ACME")

    # ── AI insights ──────────────────────────────────────────────────────
    def test_delay_risk_scoped(self):
        out = ai_insights.delay_risk(db=self.db, band=None, limit=50, scope=self.scope)
        self.assertEqual(self._keys(out["items"]), {("ACME", "001"), ("GAMMA", "002")})

    def test_black_followups_only_allowed(self):
        out = ai_insights.black_followups(db=self.db, limit=100, scope=self.scope)
        for i in out["items"]:
            self.assertTrue(self.scope.allows_pair(i["supplier_name"], i["supplier_po_no"]))

    def test_followup_history_scoped(self):
        audit.record(self.db, supplier_po_no="001", supplier_name="ACME", signal="RED",
                     mail_type="PO_FOLLOWUP_RED", source="auto", outcome="QUEUED")
        audit.record(self.db, supplier_po_no="003", supplier_name="BETA", signal="RED",
                     mail_type="PO_FOLLOWUP_RED", source="auto", outcome="QUEUED")
        out = ai_insights.followup_history(
            db=self.db, signal=None, outcome=None, supplier_po_no=None, limit=100,
            scope=self.scope,
        )
        self.assertEqual(self._keys(out["items"]), {("ACME", "001")})

    def test_command_404_for_foreign_po(self):
        payload = ai_insights.FollowupCommand(supplier_po_no="003", instruction="chase")
        with self.assertRaises(HTTPException) as cm:
            ai_insights.black_followup_command(
                payload=payload, db=self.db, user=self.vijay, scope=self.scope
            )
        self.assertEqual(cm.exception.status_code, 404)

    def test_supplier_scorecards_scoped(self):
        out = ai_insights.supplier_scorecards(db=self.db, limit=100, scope=self.scope)
        self.assertEqual({i["supplier_name"] for i in out["items"]}, {"ACME", "GAMMA"})
        with self.assertRaises(HTTPException):
            ai_insights.supplier_scorecard(name="BETA", db=self.db, scope=self.scope)

    def test_direct_call_without_di_is_unscoped(self):
        # employee_portal calls black_followups(db=, limit=) directly.
        out = ai_insights.black_followups(db=self.db, limit=300)
        self.assertIn("items", out)

    # ── Mail log / mail history ──────────────────────────────────────────
    def _msg(self, name, po, sid):
        m = CommunicationMessage(direction="OUTGOING", status="SENT", supplier_name=name,
                                 supplier_po_no=po, supplier_id=sid, mail_type="PO_FOLLOWUP_RED",
                                 subject=f"{name} {po}")
        self.db.add(m)
        self.db.commit()
        return m

    def test_mail_log_scoped(self):
        self._msg("ACME", "001", self.acme.id)
        self._msg("BETA", "001", self.beta.id)
        self._msg("GAMMA", None, self.gamma.id)  # assigned supplier, no PO
        out = mail_log.list_mail_log(status=None, mail_type=None, search=None, date_from=None,
                                     date_to=None, page=1, size=50, db=self.db, scope=self.scope)
        self.assertEqual({i["supplier_name"] for i in out["items"]}, {"ACME", "GAMMA"})
        self.assertEqual(out["total"], 2)
        self.assertEqual(sum(out["counts"].values()), 2)
        full = mail_log.list_mail_log(status=None, mail_type=None, search=None, date_from=None,
                                      date_to=None, page=1, size=50, db=self.db, scope=None)
        self.assertEqual(full["total"], 3)

    def _hist(self, rec):
        h = MailHistory(procurement_record_id=rec.id, supplier_name=rec.supplier_name,
                        supplier_po_no=rec.supplier_po_no, material_name="Bolt",
                        subject="s", body="b", mail_type="PO_FOLLOWUP_RED")
        self.db.add(h)
        self.db.commit()
        return h

    def test_mail_history_scoped(self):
        mine = self._hist(self.r1)
        other = self._hist(self.r2)
        rows = mail_history.list_history(db=self.db, supplier=None, po_no=None,
                                         supplier_po_no=None, subject=None, mail_type=None,
                                         status=None, limit=200, scope=self.scope)
        self.assertEqual([r.id for r in rows], [mine.id])
        self.assertEqual(mail_history.get_history(mine.id, db=self.db, scope=self.scope).id, mine.id)
        with self.assertRaises(HTTPException) as cm:
            mail_history.get_history(other.id, db=self.db, scope=self.scope)
        self.assertEqual(cm.exception.status_code, 404)
        self.assertEqual(mail_history.by_record(self.r2.id, db=self.db, scope=self.scope), [])

    # ── ASNs ─────────────────────────────────────────────────────────────
    def _asn(self, no, sup, po):
        a = Asn(asn_no=no, supplier_id=sup.id, supplier_name=sup.supplier_name,
                supplier_po_no=po, status="SUBMITTED")
        self.db.add(a)
        self.db.commit()
        return a

    def test_asns_scoped(self):
        mine = self._asn("A1", self.acme, "001")
        other = self._asn("A2", self.beta, "001")
        assigned = self._asn("A3", self.gamma, "999")  # assigned supplier, any PO
        out = asns.list_asns(db=self.db, tab=None, status=None, search=None, scope=self.scope)
        self.assertEqual({i.id for i in out.items}, {mine.id, assigned.id})
        self.assertEqual(asns.summary(db=self.db, scope=self.scope).total, 2)
        with self.assertRaises(HTTPException) as cm:
            asns.get_asn(other.id, db=self.db, scope=self.scope)
        self.assertEqual(cm.exception.status_code, 404)
        self.assertEqual(asns.summary(db=self.db, scope=None).total, 3)

    # ── AI chat tools ────────────────────────────────────────────────────
    def test_ai_tools_scoped(self):
        run = ai_tools_service.make_executor(self.db, ai_tools_service.ToolScope(staff=self.scope))
        self.assertFalse(run("get_po_status", {"supplier_po_no": "003"})["found"])
        st = run("get_po_status", {"supplier_po_no": "001"})
        self.assertEqual(st["supplier_name"], "ACME")
        red = run("list_red_pos", {"limit": 50})
        self.assertEqual(self._keys(red["purchase_orders"]), {("ACME", "001"), ("GAMMA", "002")})
        self.assertEqual(run("search_supplier", {"query": "BETA"})["count"], 0)
        self.assertEqual(run("get_overview", {})["total_records"], 2)
        self.assertNotIn("open_customer_mails", run("get_overview", {}))


if __name__ == "__main__":
    unittest.main()

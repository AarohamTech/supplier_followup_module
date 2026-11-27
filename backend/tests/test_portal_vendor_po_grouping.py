"""Supplier portal: one logical PO per supplier + vendor PO number.

`supplier_po_no` is an internal CRM counter the CRM recycles; the number the
supplier knows is the vendor PO ref (`po_short_ref`). One vendor PO can span
several counters (e.g. 012736 and 012738 both carrying 2627-019982), which used
to list the same vendor PO twice in the portal. The portal now groups a
supplier's counters sharing a vendor ref into one row, keeps every counter, and
every PO action works on any counter of the group — without ever merging two
suppliers' POs.

DB-backed with in-memory SQLite (production data untouched).
"""
from __future__ import annotations

import os
import unittest
from contextlib import contextmanager
from datetime import date, datetime

os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_portal_vendor_po.sqlite")

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.core.roles import Role  # noqa: E402
from app.database import Base  # noqa: E402
from app.models import (  # noqa: E402,F401
    CommunicationMessage,
    CommunicationTask,
    ProcurementRecord,
    SupplierMaster,
    SupplierMaterialCommitment,
    User,
)
from app.models.asn import Asn  # noqa: E402
from app.routers import po_ack, portal  # noqa: E402
from app.schemas.portal import (  # noqa: E402
    PortalCommitmentItem,
    PortalCommitmentSubmit,
    PortalEscalateIn,
)
from app.services import po_ack_service, po_followup_service, user_service  # noqa: E402

ACME = "ACME TOOLS"
BETA = "BETA PARTS"
REF = "2627-019982"


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


_seq = iter(range(1, 10_000))


def _line(db, counter, ref, material, *, supplier=ACME, signal="GREEN",
          ship=None, qty=10, trn=None, **extra) -> ProcurementRecord:
    rec = ProcurementRecord(
        crm_no=f"CRM-{next(_seq)}", supplier_po_no=counter, po_short_ref=ref,
        material_name=material, supplier_name=supplier, signal=signal,
        po_status="APPROVED", shipment_date=ship, qty=qty, po_trn_no=trn,
        owner_emp_code="EMP1", **extra,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


def _supplier_user(db, name) -> User:
    s = db.scalar(select(SupplierMaster).where(SupplierMaster.supplier_name == name))
    if s is None:
        s = SupplierMaster(supplier_name=name, is_active=True)
        db.add(s)
        db.commit()
        db.refresh(s)
    slug = name.split()[0].lower()
    return user_service.create_user(
        db, email=f"sup@{slug}.com", password="x" * 8, role=Role.SUPPLIER, supplier_id=s.id)


def _commit(db, counter, material, supplier, remark, rec_id=None):
    return po_followup_service.upsert_commitment(
        db, supplier_po_no=counter, material_name=material, procurement_record_id=rec_id,
        supplier_id=None, supplier_name=supplier, material_code=None, commitment_qty=5,
        commitment_date_value=date(2026, 12, 15), supplier_status="CONFIRMED",
        supplier_remark=remark, reply_mail_id=None, commit=True,
    )


def _msg(db, user, counter, direction="OUTGOING", status="SENT"):
    cm = CommunicationMessage(
        direction=direction, status=status, supplier_id=user.supplier_id,
        supplier_po_no=counter, subject=f"msg {counter}", body="hello",
    )
    db.add(cm)
    db.commit()
    return cm


def _pos(db, user):
    return portal.list_pos(user=user, db=db)


class GroupingHelperTests(unittest.TestCase):
    def test_counters_sharing_a_ref_merge_transitively(self):
        recs = [
            ProcurementRecord(supplier_po_no="A", po_short_ref="X"),
            ProcurementRecord(supplier_po_no="B", po_short_ref="X"),
            ProcurementRecord(supplier_po_no="B", po_short_ref="Y"),
            ProcurementRecord(supplier_po_no="C", po_short_ref=" y "),
            ProcurementRecord(supplier_po_no="D", po_short_ref=None),
        ]
        self.assertEqual(portal._logical_po_groups(recs), [["A", "B", "C"], ["D"]])


class VendorPoGroupingTests(unittest.TestCase):
    # 1 — same supplier + same vendor PO + two counters → shown once.
    def test_same_vendor_po_on_two_counters_is_listed_once(self):
        with _temp_db() as db:
            sup = _supplier_user(db, ACME)
            _line(db, "012736", REF, "SC DRILL")
            _line(db, "012738", REF, "SPOT FACE")

            resp = _pos(db, sup)
            self.assertEqual(resp.count, 1)
            po = resp.items[0]
            self.assertEqual(po.po_ref, REF)
            self.assertEqual(po.supplier_po_no, "012736")          # anchor counter
            self.assertEqual(po.supplier_po_nos, ["012736", "012738"])  # both kept
            self.assertEqual(po.material_count, 2)

            s = portal.summary(user=sup, db=db)
            self.assertEqual((s.total_pos, s.pending_pos), (1, 1))

    # 2 — same supplier + different vendor POs → stay separate.
    def test_different_vendor_pos_stay_separate(self):
        with _temp_db() as db:
            sup = _supplier_user(db, ACME)
            _line(db, "012736", REF, "SC DRILL")
            _line(db, "012740", "2627-020001", "SPOT FACE")
            _line(db, "012741", None, "REAMER")  # no vendor ref → its own PO

            resp = _pos(db, sup)
            self.assertEqual(resp.count, 3)
            self.assertEqual(
                sorted(p.supplier_po_nos[0] for p in resp.items), ["012736", "012740", "012741"])
            self.assertTrue(all(len(p.supplier_po_nos) == 1 for p in resp.items))
            self.assertEqual(portal.summary(user=sup, db=db).total_pos, 3)

    # 3 — different suppliers + same vendor PO → never merged.
    def test_different_suppliers_with_same_vendor_po_are_not_merged(self):
        with _temp_db() as db:
            acme = _supplier_user(db, ACME)
            beta = _supplier_user(db, BETA)
            _line(db, "012736", REF, "SC DRILL", supplier=ACME)
            _line(db, "012738", REF, "BETA PART", supplier=BETA)
            _line(db, "012736", REF, "BETA PART 2", supplier=BETA)  # recycled counter
            _commit(db, "012736", "SC DRILL", BETA, "beta's commitment")

            a = _pos(db, acme)
            self.assertEqual(a.count, 1)
            self.assertEqual(a.items[0].supplier_po_nos, ["012736"])
            self.assertEqual(a.items[0].material_count, 1)
            b = _pos(db, beta)
            self.assertEqual(b.count, 1)
            self.assertEqual(b.items[0].supplier_po_nos, ["012736", "012738"])

            mats = portal.po_materials("012736", user=acme, db=db)
            self.assertEqual([m.material_name for m in mats], ["SC DRILL"])
            self.assertIsNone(mats[0].commitment_remark)  # BETA's commitment never leaks
            # ACME cannot reach BETA's sibling counter through the vendor ref.
            self.assertEqual(portal.po_materials("012738", user=acme, db=db), [])

    # 4 — same PO with multiple line items (spread over both counters).
    def test_multiple_line_items_across_counters(self):
        with _temp_db() as db:
            sup = _supplier_user(db, ACME)
            a = _line(db, "012736", REF, "SC DRILL", signal="GREEN")
            b = _line(db, "012736", REF, "SPOT FACE LH", signal="YELLOW")
            c = _line(db, "012738", REF, "SPOT FACE RH", signal="BLACK")

            po = _pos(db, sup).items[0]
            self.assertEqual(po.material_count, 3)
            self.assertEqual(po.overall_signal, "BLACK")
            self.assertEqual(portal.summary(user=sup, db=db).blocked_count, 1)

            for counter in ("012736", "012738"):  # any counter opens the whole PO
                ids = sorted(m.procurement_record_id for m in portal.po_materials(counter, user=sup, db=db))
                self.assertEqual(ids, sorted([a.id, b.id, c.id]))

    # 5 — existing commitments, acknowledgement, messages, ASN, tasks keep working.
    def test_existing_commitments_are_preserved_per_counter(self):
        with _temp_db() as db:
            sup = _supplier_user(db, ACME)
            a = _line(db, "012736", REF, "SC DRILL")
            b = _line(db, "012736", REF, "SPOT FACE LH")
            c = _line(db, "012738", REF, "SPOT FACE RH")
            _commit(db, "012736", "SC DRILL", ACME, "on 012736", a.id)
            _commit(db, "012738", "SPOT FACE RH", ACME, "on 012738", c.id)

            mats = {m.procurement_record_id: m for m in portal.po_materials("012736", user=sup, db=db)}
            self.assertEqual(mats[a.id].commitment_remark, "on 012736")
            self.assertEqual(mats[c.id].commitment_remark, "on 012738")
            self.assertIsNone(mats[b.id].commitment_remark)

            # Saving via the anchor URL updates the line's OWN counter row in place.
            out = portal.submit_commitments(
                "012736",
                PortalCommitmentSubmit(items=[PortalCommitmentItem(
                    procurement_record_id=c.id, commitment_date="2026-12-20",
                    supplier_remark="updated")]),
                user=sup, db=db,
            )
            self.assertEqual({m.procurement_record_id: m.commitment_remark for m in out}[c.id], "updated")
            rows = db.scalars(select(SupplierMaterialCommitment)).all()
            self.assertEqual(len(rows), 2)  # no duplicate row under the anchor counter
            row = next(r for r in rows if r.material_name == "SPOT FACE RH")
            self.assertEqual((row.supplier_po_no, row.supplier_remark), ("012738", "updated"))
            db.refresh(c)
            self.assertEqual(c.commitment_date.date() if isinstance(c.commitment_date, datetime)
                             else c.commitment_date, date(2026, 12, 20))

    def test_acknowledgement_is_shared_by_the_whole_vendor_po(self):
        with _temp_db() as db:
            sup = _supplier_user(db, ACME)
            _line(db, "012736", REF, "SC DRILL")
            c = _line(db, "012738", REF, "SPOT FACE RH")
            row, created, _ = po_ack_service.acknowledge(
                db, supplier_name=ACME, supplier_po_no="012738", po_ref=REF,
                record_id=c.id, via="portal")
            self.assertTrue(created)
            status = po_ack.portal_status("012736", user=sup, db=db)
            self.assertTrue(status["acknowledged"])
            self.assertEqual(status["po_ref"], REF)

    def test_messages_asn_tasks_and_escalation_span_all_counters(self):
        with _temp_db() as db:
            sup = _supplier_user(db, ACME)
            beta = _supplier_user(db, BETA)
            _line(db, "012736", REF, "SC DRILL")
            _line(db, "012738", REF, "SPOT FACE RH")
            _msg(db, sup, "012738", "OUTGOING", "SENT")      # unread buyer message
            _msg(db, sup, "012736", "INCOMING", "RECEIVED")  # supplier's own
            db.add(Asn(asn_no="ASN-1", supplier_id=sup.supplier_id, supplier_name=ACME,
                       supplier_po_no="012738", status="DELIVERED"))
            db.add(CommunicationTask(title="chase", supplier_id=sup.supplier_id,
                                     supplier_name=ACME, supplier_po_no="012738", status="TODO"))
            db.commit()

            po = _pos(db, sup).items[0]
            self.assertEqual((po.message_count, po.unread_inbound, po.asn_count), (2, 1, 1))
            self.assertTrue(po.completed)
            s = portal.summary(user=sup, db=db)
            self.assertEqual((s.completed_pos, s.pending_pos), (1, 0))

            self.assertEqual(len(portal.list_po_messages("012736", user=sup, db=db)), 2)
            self.assertEqual([t.title for t in portal.po_tasks("012736", user=sup, db=db)], ["chase"])
            self.assertEqual(portal.mark_po_messages_read("012736", user=sup, db=db)["marked"], 1)
            self.assertEqual(_pos(db, sup).items[0].unread_inbound, 0)

            # Another supplier's open escalation on a recycled counter must not block.
            db.add(CommunicationTask(title="beta esc", supplier_id=beta.supplier_id,
                                     supplier_name=BETA, supplier_po_no="012736",
                                     task_source="ESCALATION", assigned_by="Supplier Portal",
                                     status="TODO"))
            db.commit()
            first = portal.escalate_po("012738", PortalEscalateIn(reason="late"), user=sup, db=db)
            self.assertFalse(first["already_escalated"])
            again = portal.escalate_po("012736", PortalEscalateIn(), user=sup, db=db)
            self.assertTrue(again["already_escalated"])  # one per logical PO
            self.assertEqual(again["task_id"], first["task_id"])
            flagged = db.scalars(select(ProcurementRecord).where(
                ProcurementRecord.supplier_name == ACME)).all()
            self.assertTrue(all(r.escalation_level == "ESCALATED" for r in flagged))
            self.assertTrue(_pos(db, sup).items[0].escalated)

    # 6 — a supplier can access only its own POs.
    def test_supplier_cannot_access_another_suppliers_po(self):
        with _temp_db() as db:
            acme = _supplier_user(db, ACME)
            beta = _supplier_user(db, BETA)
            own = _line(db, "012736", REF, "SC DRILL", supplier=ACME)
            other = _line(db, "099999", "2627-777777", "BETA ONLY", supplier=BETA)
            _msg(db, beta, "099999")

            self.assertEqual(_pos(db, acme).count, 1)
            self.assertEqual(portal.po_materials("099999", user=acme, db=db), [])
            self.assertEqual(portal.list_po_messages("099999", user=acme, db=db), [])
            for call in (
                lambda: portal.po_tasks("099999", user=acme, db=db),
                lambda: portal.mark_po_messages_read("099999", user=acme, db=db),
                lambda: portal.escalate_po("099999", PortalEscalateIn(), user=acme, db=db),
                lambda: portal.submit_commitments(
                    "099999", PortalCommitmentSubmit(items=[]), user=acme, db=db),
            ):
                with self.assertRaises(HTTPException) as ctx:
                    call()
                self.assertEqual(ctx.exception.status_code, 404)

            # Smuggling BETA's line id through ACME's own PO URL is ignored.
            portal.submit_commitments(
                "012736",
                PortalCommitmentSubmit(items=[
                    PortalCommitmentItem(procurement_record_id=other.id, commitment_date="2026-12-20"),
                    PortalCommitmentItem(procurement_record_id=own.id, commitment_date="2026-12-21"),
                ]),
                user=acme, db=db,
            )
            rows = db.scalars(select(SupplierMaterialCommitment)).all()
            self.assertEqual([(r.supplier_name, r.supplier_po_no) for r in rows], [(ACME, "012736")])

    # 7 — PO details stay correct after grouping.
    def test_po_details_are_correct_after_grouping(self):
        with _temp_db() as db:
            sup = _supplier_user(db, ACME)
            late = _line(db, "012736", REF, "SC DRILL", ship=datetime(2026, 12, 30), qty=4, trn="TRN-9")
            early = _line(db, "012738", REF, "SPOT FACE RH", ship=datetime(2026, 12, 5), qty=7, trn="TRN-9")
            # A fully received line drops out of the PO, but its counter stays reachable.
            _line(db, "012750", REF + "-OLD", "OLD PART", receipt_status="COMPLETED")

            po = _pos(db, sup).items[0]
            self.assertEqual(_pos(db, sup).count, 1)
            self.assertEqual(po.earliest_shipment_date, datetime(2026, 12, 5))
            self.assertEqual(po.po_trn_no, "TRN-9")

            via_anchor = portal.po_materials("012736", user=sup, db=db)
            via_sibling = portal.po_materials("012738", user=sup, db=db)
            self.assertEqual(
                [m.model_dump() for m in via_anchor], [m.model_dump() for m in via_sibling])
            # Ordered by shipment date; each line keeps its own CRM number + qty.
            self.assertEqual([m.procurement_record_id for m in via_anchor], [early.id, late.id])
            self.assertEqual([(m.crm_no, m.qty) for m in via_anchor],
                             [(early.crm_no, 7.0), (late.crm_no, 4.0)])

            # Closed-only counter: no lines, but still owned (tasks reachable, not 404).
            self.assertEqual(portal.po_materials("012750", user=sup, db=db), [])
            self.assertEqual(portal.po_tasks("012750", user=sup, db=db), [])


if __name__ == "__main__":
    unittest.main()

"""Courier tracking: geocoding + checkpoint ingestion (HTTP stubbed)."""
from __future__ import annotations

import unittest
from contextlib import contextmanager
from datetime import datetime
from unittest import mock

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Asn, AsnEvent  # noqa: F401
from app.models.asn import Asn as AsnModel, AsnEvent as AsnEventModel
from app.data.india_city_coords import geocode
from app.services import courier_tracking_service as cts


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


def _make_asn(db):
    asn = AsnModel(
        asn_no="ASN-2026-0001", supplier_id=1, supplier_po_no="PO-1",
        courier_code="delhivery", tracking_no="TRK123", status="IN_TRANSIT",
    )
    db.add(asn)
    db.commit()
    db.refresh(asn)
    return asn


_CHECKPOINTS = [
    {"location": "Mumbai", "detail": "Shipment picked up", "date": "01 Jul, 2026 09:00 hrs"},
    {"location": "Pune", "detail": "In Transit", "date": "02 Jul, 2026 14:00 hrs"},
    {"location": "Unknownville", "detail": "Out for delivery", "date": "03 Jul, 2026 08:00 hrs"},
]


class GeocodeTests(unittest.TestCase):
    def test_known_cities_resolve(self) -> None:
        self.assertIsNotNone(geocode("Mumbai"))
        self.assertIsNotNone(geocode("mumbai"))
        self.assertIsNotNone(geocode("Pune, MH"))

    def test_unknown_city_returns_none(self) -> None:
        self.assertIsNone(geocode("Atlantis"))
        self.assertIsNone(geocode(""))
        self.assertIsNone(geocode(None))


class PollTests(unittest.TestCase):
    def test_disabled_is_noop(self) -> None:
        with _temp_db() as db:
            _make_asn(db)
            with mock.patch.object(cts.settings, "COURIER_API_ENABLED", False):
                out = cts.poll_in_transit(db)
            self.assertFalse(out["enabled"])
            self.assertEqual(db.scalar(select(AsnEventModel.id)), None)

    def test_appends_geocoded_checkpoints_no_dupes(self) -> None:
        with _temp_db() as db:
            asn = _make_asn(db)
            with mock.patch.object(cts.settings, "COURIER_API_ENABLED", True), \
                 mock.patch.object(cts, "_fetch", return_value=_CHECKPOINTS):
                out1 = cts.poll_in_transit(db)
                out2 = cts.poll_in_transit(db)  # second run = no new events

            self.assertEqual(out1["updated"], 3)
            self.assertEqual(out2["updated"], 0)  # dedupe holds

            events = list(db.scalars(
                select(AsnEventModel).where(AsnEventModel.source == "COURIER_API")
            ).all())
            self.assertEqual(len(events), 3)
            by_loc = {e.location: e for e in events}
            self.assertIsNotNone(by_loc["Mumbai"].lat)  # known city geocoded
            self.assertIsNone(by_loc["Unknownville"].lat)  # unknown city has no coords

            # Stage advanced (out for delivery) but did not flip to DELIVERED.
            db.refresh(asn)
            self.assertEqual(asn.status, "OUT_FOR_DELIVERY")


if __name__ == "__main__":
    unittest.main()

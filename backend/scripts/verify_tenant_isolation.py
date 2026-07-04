"""Standalone tenant-isolation verification — RUN AGAINST A SCRATCH POSTGRES ONLY.

Never uses backend/.env. You MUST set TENANT_TEST_DATABASE_URL to a throwaway
Postgres database; this script binds the app to THAT url (not .env) BEFORE importing
any app module, then proves a write under use_company("company_101") lands in
company_101 and is invisible to the default (public) context, and cleans up.

Usage (from backend/):
    TENANT_TEST_DATABASE_URL="postgresql+psycopg2://user:pass@host:5432/scratch" \
        .venv/Scripts/python.exe scripts/verify_tenant_isolation.py
"""
import os
import sys


def main() -> int:
    url = os.environ.get("TENANT_TEST_DATABASE_URL", "").strip()
    if not url.startswith("postgresql"):
        print("REFUSING TO RUN: set TENANT_TEST_DATABASE_URL to a SCRATCH Postgres URL.")
        print("This script must never run against backend/.env (production).")
        return 1
    # Bind the app engine to the scratch DB BEFORE importing any app module, so
    # app.database.engine can never pick up backend/.env's production DATABASE_URL.
    os.environ["DATABASE_URL"] = url
    os.environ["DB_SCHEMA"] = ""

    from sqlalchemy import text
    from app.database import Base, engine, SessionLocal, create_company_schema
    from app.core.tenant import use_company
    from app.models.procurement import ProcurementRecord

    marker_public = "ISO-PUBLIC-0001"
    marker_101 = "ISO-101-0001"
    ok = True
    try:
        Base.metadata.create_all(bind=engine)
        create_company_schema("company_101")

        with SessionLocal() as db:                 # default context → public
            db.add(ProcurementRecord(crm_no=marker_public, supplier_po_no="P1",
                                     material_name="M", po_no="P1"))
            db.commit()
        with use_company("company_101"):
            with SessionLocal() as db:             # company_101 context
                db.add(ProcurementRecord(crm_no=marker_101, supplier_po_no="P1",
                                         material_name="M", po_no="P1"))
                db.commit()

        with SessionLocal() as db:                 # public sees ONLY its own row
            crms = {r.crm_no for r in db.query(ProcurementRecord).all()}
            assert marker_public in crms and marker_101 not in crms, crms
        with use_company("company_101"):
            with SessionLocal() as db:             # 101 sees ONLY its own row
                crms = {r.crm_no for r in db.query(ProcurementRecord).all()}
                assert marker_101 in crms and marker_public not in crms, crms
        print("PASS: tenant isolation verified (company_101 vs public).")
    except AssertionError as exc:
        ok = False
        print("FAIL: isolation assertion failed:", exc)
    finally:
        try:
            with engine.begin() as conn:
                conn.execute(text('DROP SCHEMA IF EXISTS "company_101" CASCADE'))
                conn.execute(text("DELETE FROM public.procurement_records WHERE crm_no = :m"),
                             {"m": marker_public})
        except Exception as exc:  # noqa: BLE001
            print("WARN: cleanup issue:", exc)
        engine.dispose()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

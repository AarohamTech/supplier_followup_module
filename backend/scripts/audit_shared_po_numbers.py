"""READ-ONLY audit: PO numbers shared across multiple suppliers.

CRM PoNo is a recycled counter, so the same supplier_po_no appears for many
suppliers. This report surfaces the offenders and any commitment rows whose
(supplier_po_no, material_name) is claimed by more than one supplier (the case
the supplier-scoped unique key protects against).

Run from backend/:
    .venv/Scripts/python.exe -m scripts.audit_shared_po_numbers
"""
from __future__ import annotations

from sqlalchemy import text

from app.database import SessionLocal


def _show(db, title: str, sql: str) -> None:
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)
    rows = db.execute(text(sql)).fetchall()
    if not rows:
        print("(no rows)")
        return
    print(" | ".join(rows[0]._fields))
    for r in rows:
        print(" | ".join("" if v is None else str(v) for v in r))


def main() -> None:
    db = SessionLocal()
    try:
        _show(
            db,
            "supplier_po_no shared by >1 supplier (top 25)",
            """
            SELECT supplier_po_no,
                   COUNT(DISTINCT supplier_name) AS n_suppliers,
                   COUNT(*) AS n_rows
            FROM procurement_records
            WHERE supplier_po_no IS NOT NULL AND supplier_po_no <> ''
            GROUP BY supplier_po_no
            HAVING COUNT(DISTINCT supplier_name) > 1
            ORDER BY n_suppliers DESC, n_rows DESC
            LIMIT 25
            """,
        )
        _show(
            db,
            "commitments where (po_no, material) is claimed by >1 supplier",
            """
            SELECT supplier_po_no, material_name,
                   COUNT(DISTINCT supplier_name) AS n_suppliers,
                   STRING_AGG(DISTINCT supplier_name, ' || ') AS suppliers
            FROM supplier_material_commitments
            GROUP BY supplier_po_no, material_name
            HAVING COUNT(DISTINCT supplier_name) > 1
            ORDER BY n_suppliers DESC
            LIMIT 25
            """,
        )
        print("\nDONE (read-only).")
    finally:
        db.close()


if __name__ == "__main__":
    main()

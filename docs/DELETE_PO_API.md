# Delete Purchase Order API

Admin-only endpoints to remove purchase orders from `procurement_records`.

> **Why `supplier_name` is required:** the CRM `PoNo` (stored as `supplier_po_no`)
> is a recycled counter — the same PO number is reused across many suppliers
> (e.g. `000440` belongs to *both* Vedant Tools and Global Tools). A PO number
> alone is therefore ambiguous; the canonical PO identity is
> `(supplier_name, supplier_po_no)`.

Auth: all endpoints require the **admin** role (Bearer JWT).

---

## Delete a whole PO (all material lines) for one supplier

```
DELETE /api/procurement/po?supplier_po_no={po}&supplier_name={name}
```

| Query param       | Required | Notes                                             |
| ----------------- | -------- | ------------------------------------------------- |
| `supplier_po_no`  | yes      | The supplier PO number, e.g. `000440`.            |
| `supplier_name`   | yes      | Exact supplier name (case-insensitive match).     |

**Behavior**
- Deletes every `procurement_records` row matching `(supplier_name, supplier_po_no)`.
- Active `supplier_material_commitments` for that `(supplier, PO)` are **deactivated**
  (`is_active = false`) so they stop surfacing.
- Mail history and tasks are **retained** for audit (they reference the PO number,
  not a hard FK).

**Responses**
- `200`:
  ```json
  {
    "ok": true,
    "supplier_name": "Vedant Tools Pvt Ltd",
    "supplier_po_no": "000440",
    "deleted_lines": 1,
    "commitments_deactivated": 1
  }
  ```
- `404`: no PO found for that supplier + PO number.
- `403`: caller is not an admin.

**Example**
```bash
curl -X DELETE \
  "$BASE/api/procurement/po?supplier_po_no=000440&supplier_name=Vedant%20Tools%20Pvt%20Ltd" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

---

## Delete a single PO material line

```
DELETE /api/procurement/{rec_id}
```

Deletes one `procurement_records` row by its numeric id.

**Responses**
- `200`: `{ "ok": true, "deleted_id": 944 }`
- `404`: no record with that id.
- `403`: caller is not an admin.

**Example**
```bash
curl -X DELETE "$BASE/api/procurement/944" -H "Authorization: Bearer $ADMIN_TOKEN"
```

# Hariom quantity APIs (PO receipt quantities)

Source: "RE: Hariom User Desk API" mail thread (Vinayak Shankardas / Ninad Pawar,
June–July 2026). The classic pending-desk feed we ingest
(`GET /api/crm/GetPendingUserDesk/{deskId}`) carries **no** quantity fields —
receipt quantities live in two other feeds.

## 1. getpendingpolist — PUBLIC, confirmed live (this is what we consume)

```
GET http://hariomapp.dyndns-server.com:8599/api/procurement/getpendingpolist/{CompanyId}
Authorization: Bearer <token>   (same login flow as GetPendingUserDesk)
```

Confirmed 200 OK on the public host in Ninad's Postman screenshot (2026-07-11;
~7 MB response for desk 102). One row per PO material line. Fields observed:

| Field | Meaning |
|---|---|
| `TrnNo` | PO transaction number — join key to `procurement_records.po_trn_no` (the desk feed's `PoRefTrnNo`) |
| `PoNo` | e.g. "PO 002342" |
| `AmendNo`, `TrnDate`, `PoValidity` | PO header details |
| `PoType` | "One Time" / "Open" — Open quantities are unreliable (PoQty echoed as PendQty), no receipt_status derived |
| `SiNo`, `DocType` | line number, document type |
| `MaterialCode`, `MaterialName`, `MaterialUom`, `Rate`, `RatePer` | material line |
| `PoQty` | ordered quantity |
| `GrnQty` | material inward (received) at Hariom |
| `PendQty` | still to receive; `<= 0` ⇒ line COMPLETED |
| `SupplierName` | vendor |
| `LongName` | end customer — null for direct POs |

Consumed by `crm_ingest_service.sync_quantities` (flag `CRM_QTY_SYNC_ENABLED`,
throttle `CRM_QTY_SYNC_INTERVAL_MINUTES`, forced by the admin Sync-now button).
Join: `(TrnNo, upper(MaterialName))` → `(po_trn_no, upper(material_name))`.
Verdict line `qty-sync: rows=… recs=… matched=… updated=…` is appended to the
CRM Ingestion log message — **matched=0 with rows present means the join key
assumption is wrong**; check the probe's `trn_sample` against stored
`po_trn_no` values.

## 2. crmappservices desk API — LAN-only (as of 2026-07-10)

```
Tech:        http://10.10.1.18:8701/api/crmappservices/getpendinguserdesk
Enterprises: http://10.10.1.18:8301/api/crmappservices/getpendinguserdesk
```

The "newer" desk API from Vinayak's 2026-06-27 mail. Not reachable from AWS;
Ninad asked for it to be opened ("please provide open api so we can access it
from AWS"). The hourly probe (`probe_qty_api`, admin CRM Ingestion page →
Check availability) watches for it appearing on the public host.

## Related APIs from the same thread (already integrated)

- **PO PDF**: `GET /api/procurement/getpopdf?CompanyId=…&TrnNo=…&AmendNo=0`
  (proxied by `GET /api/procurement/po-pdf`).
- **PO cancel contract** (H-Connect → ERP `POST /api/crm/PoCancelRequest`,
  confirm webhook `POST /api/webhooks/po-cancel-confirm`): see
  `docs/PO_CANCEL_ERP_API.md`.

Known vendor-side quirk (Ninad, 2026-07-11): field-naming conflict between the
APIs — one says "PO No.", the other "Full PO No."; Hariom IT was asked to align.

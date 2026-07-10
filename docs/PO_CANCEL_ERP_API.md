# PO Cancellation - API format for ERP integration

When a user requests a PO cancellation in H-Connect, the PO is marked "Pending
cancellation" and a cancel request is sent to the ERP. The PO stays pending until the
ERP confirms or rejects it.

Two calls are involved: one from us to the ERP (the request), one from the ERP back
to us (the confirmation).

## 1. Cancel request (H-Connect -> ERP)

The ERP team should provide an endpoint that accepts this request. Proposed format;
the field names can be adjusted to whatever the ERP prefers.

    POST {erp_host}/api/crm/PoCancelRequest
    Authorization: Bearer <token>   (same login flow as GetPendingUserDesk)

Body:

    {
      "CompanyId": "102",
      "PoNo": "000449",
      "SupplierName": "VEDANT TOOLS PVT LTD",
      "PoDate": "2026-06-14",
      "RequestedBy": "1010000028",
      "Remark": "Material no longer required",
      "RequestedAt": "2026-07-10T18:30:00Z",
      "Lines": [
        {
          "CrmNo": "2526-012467",
          "MaterialName": "BLIND SLEEVE 70 X 100",
          "Qty": 1800,
          "CustomerName": "SHRIRAM FOUNDRY PVT LTD - DEWAS",
          "CustomerPoNo": "119262770111000130",
          "CustomerPoDate": "2026-06-10"
        }
      ]
    }

Notes:
- PoNo is the CRM PoNo. SupplierName is needed because PoNo repeats across suppliers.
- PoDate is the supplier PO date.
- RequestedBy is the employee code (or email) of the person who raised the request.
- Remark is the reason typed by the requester (max 500 chars).
- Lines lists each CRM line under that PO with its customer context: the end
  customer the PO serves, the customer order reference (RefTrnNo) and its date.
  Lines from a PO not linked to any customer (direct PO) have CustomerName null.

Expected immediate response:

    { "Status": "RECEIVED", "Message": "" }

## 2. Confirmation (ERP -> H-Connect)

Once the ERP processes the cancellation, call our webhook to update the PO status:

    POST https://h-connect.harmonytech.in/api/webhooks/po-cancel-confirm
    X-Webhook-Secret: <shared secret, provided separately>

Body:

    {
      "po_no": "000449",
      "supplier_name": "VEDANT TOOLS PVT LTD",
      "status": "CANCELLED",
      "message": ""
    }

- status CANCELLED: the PO is marked Cancelled in H-Connect.
- status REJECTED: the pending flag is cleared and the PO returns to normal.

Response:

    { "ok": true, "po_no": "000449", "status": "CANCELLED", "records_updated": 2 }

Errors: 401 wrong/missing secret, 404 no pending cancellation for that PO,
422 status not CANCELLED/REJECTED.

## Current state

The H-Connect side is live: the request button, remark, pending state, and the
confirmation webhook all work. The outbound call in step 1 is a stub until the ERP
endpoint exists - once the ERP team confirms the URL and final field names, it is a
one-line wire-up in `backend/app/services/po_cancel_service.py`
(`_raise_external_cancel`).

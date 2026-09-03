# PO Cancellation - API format for ERP integration

When a user requests a PO cancellation in H-Connect, the PO is marked "Pending
cancellation" and a cancel request is POSTed to the ERP. The PO stays pending until
the ERP confirms or rejects it.

Two calls are involved: one from us to the ERP (the request), one from the ERP back
to us (the confirmation).

## 1. Cancel request (H-Connect -> ERP)

H-Connect sends this the moment a cancellation is raised (whole PO or a single
material line). The endpoint path is configurable on our side
(`CRM_CANCEL_API_PATH`, default below); the base URL and bearer token are the same
ones we use for `GetPendingUserDesk`.

    POST {crm_base_url}/api/crm/PoCancelRequest
    Authorization: Bearer <token>   (same login flow as GetPendingUserDesk)
    Content-Type: application/json

Body:

    {
      "CompanyId": "102",
      "PoNo": "000449",
      "PoShortRefTrnNo": "2627-001703",
      "PoRefTrnNo": "118262770111005059",
      "SupplierName": "VEDANT TOOLS PVT LTD",
      "PoDate": "2026-06-14",
      "RequestedBy": "1010000028",
      "Remark": "Material no longer required",
      "RequestedAt": "2026-09-03T10:00:00Z",
      "Lines": [
        {
          "ProcurementRecordId": 4821,
          "CrmNo": "2627-001703",
          "MaterialName": "BLIND SLEEVE 70 X 100",
          "Qty": 1800,
          "CustomerName": "SHRIRAM FOUNDRY PVT LTD - DEWAS",
          "CustomerPoNo": "119262770111000130",
          "CustomerPoDate": "2026-06-10",
          "CancelRemark": "Material no longer required",
          "CrmFields": {
            "CRMNo": "2627-001703",
            "PoNo": "000449",
            "PoShortRefTrnNo": "2627-001703",
            "PoRefTrnNo": "118262770111005059",
            "PoRefTrnDate": "2026-06-14",
            "PoLongName": "VEDANT TOOLS PVT LTD",
            "PoStatus": "APPROVED",
            "MaterialName": "BLIND SLEEVE 70 X 100",
            "MaterialUom": "NOS",
            "Quantity": 1800,
            "LongName": "SHRIRAM FOUNDRY PVT LTD - DEWAS",
            "RefTrnNo": "119262770111000130",
            "RefTrnDate": "2026-06-10",
            "UserId": "1010000028",
            "... every other field GetPendingUserDesk returned for this line ..."
          }
        }
      ]
    }

Notes:
- PoNo is the CRM PoNo (the customer-order-side counter). It repeats across
  suppliers, so SupplierName and PoShortRefTrnNo (the vendor PO document number)
  are sent too. PoRefTrnNo is the PO transaction number.
- PoDate is the supplier PO date (PoRefTrnDate).
- RequestedBy is the employee code (or email) of the person who raised the request.
- Remark is the reason typed by the requester (max 500 chars). CancelRemark on the
  line is the same value stored per line.
- Lines lists each CRM line being cancelled. For a whole-PO cancel that is every
  line under the PO; for a material-wise cancel it is the one line.
- **CrmFields is the complete original CRM record for that line, exactly as the
  `GetPendingUserDesk` feed returned it** - every field, including ones H-Connect
  does not otherwise use. The ERP can therefore match the line on whatever key it
  prefers (TrnNo, SiNo, DocType, ...). For lines ingested before H-Connect started
  storing the raw record, CrmFields is rebuilt from the stored columns using the
  same key names (a fixed subset of the above).
- Lines from a PO not linked to any customer (direct PO) have CustomerName null.

Expected immediate response (any 2xx is treated as accepted):

    { "Status": "RECEIVED", "Message": "" }

If the ERP returns a non-2xx or is unreachable, the PO still shows as "Pending
cancellation" in H-Connect and the API response to our user carries
`external.raised = false` with the reason, so the request can be repeated or
followed up manually.

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

Both directions are implemented on the H-Connect side. The outbound request in
step 1 is live (`backend/app/services/po_cancel_service.py`,
`_raise_external_cancel`) and controlled by two settings:

- `CRM_CANCEL_API_ENABLED` (default true) - set false to suppress the outbound call.
- `CRM_CANCEL_API_PATH` (default `/api/crm/PoCancelRequest`) - change if the ERP
  exposes the endpoint under a different path.

The request is per company: it uses the CRM base URL and login of the company the
PO belongs to (`CRM_*` for the default company, `CRM_<CODE>_*` for others).

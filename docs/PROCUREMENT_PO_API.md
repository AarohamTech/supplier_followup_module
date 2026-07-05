# Procurement PO Delete API

## Host

Production: https://h-connect.harmonytech.in
Local: http://localhost:8000

All endpoints are under /api, so the full URL is {host}/api/...

## Get a token

Log in to get a token, then send it on every request in the header:

    Authorization: Bearer <access_token>

POST /api/auth/login

Request body (JSON):

    {
      "email": "admin@example.com",
      "password": "your-password"
    }

Notes on the body:
- Use email for staff/supplier accounts, or username instead of email for internal employees.
- password is required.
- company is optional (a code like "102" or "101"); if left out it uses 102.

Response:

    {
      "access_token": "eyJhbGciOi...",
      "token_type": "bearer",
      "expires_in": 43200,
      "user": { "id": 1, "email": "admin@example.com", "role": "admin" },
      "company": { "code": "102", "display_name": "Hariom Tech" }
    }

Use access_token as the bearer token. expires_in is in seconds. The delete endpoints below need an admin account.

## Delete a full PO (all lines for one supplier)

DELETE /api/procurement/po

Query parameters:
- supplier_po_no (required): the PO number.
- supplier_name (required): the supplier name. It is needed because PO numbers repeat across suppliers.

Response:

    {
      "ok": true,
      "supplier_name": "Vedant Tools Pvt Ltd",
      "supplier_po_no": "000449",
      "deleted_lines": 3,
      "commitments_deactivated": 1
    }

Errors:
- 404: no PO found for that supplier and PO number.
- 401: token missing or expired.
- 403: not an admin.

Example:

    curl -X DELETE "https://h-connect.harmonytech.in/api/procurement/po?supplier_po_no=000449&supplier_name=Vedant%20Tools%20Pvt%20Ltd" -H "Authorization: Bearer YOUR_TOKEN"

## Delete a single PO line

DELETE /api/procurement/{rec_id}

Path parameter:
- rec_id: the record id of the line to delete.

Response:

    {
      "ok": true,
      "deleted_id": 1234
    }

Errors:
- 404: no record with that id.
- 401: token missing or expired.
- 403: not an admin.

Example:

    curl -X DELETE "https://h-connect.harmonytech.in/api/procurement/1234" -H "Authorization: Bearer YOUR_TOKEN"

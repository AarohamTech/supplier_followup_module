# Procurement PO — Delete / Cancel API

Endpoints for removing a purchase order (PO) from the system. Source router:
[`backend/app/routers/procurement.py`](../backend/app/routers/procurement.py).

> **Important — hard delete, not a status change.** These endpoints **delete** the
> procurement records. They do **not** set `po_status = "CANCELLED"`. Mail/task
> history for the PO is retained for audit, but the PO lines themselves are removed.
> If you need a reversible "cancel" that keeps the PO but marks it cancelled, that is
> a separate feature (not yet implemented).

## Conventions

- **Base path:** all endpoints are under `/api`, same-origin (the frontend proxies
  `/api/*` to the backend — see `frontend/next.config.mjs`). Example:
  `https://h-connect.harmonytech.in/api/procurement/po`.
- **Auth:** send `Authorization: Bearer <token>`. Get a token from
  `POST /api/auth/login` — see [Getting a token](#getting-a-token) below.
- **Tenant (multi-company):** the operation runs inside the company (Postgres schema)
  resolved from the token's `company` claim — it only affects that company's data.
- **Identity of a PO:** a PO is identified by **(`supplier_name`, `supplier_po_no`)**,
  not by PO number alone. The CRM `PoNo` counter is recycled across suppliers, so the
  supplier name is required to disambiguate.

## Hosts

| Environment | Base URL | Notes |
|-------------|----------|-------|
| **Production** | `https://h-connect.harmonytech.in` | Public app URL (from `APP_BASE_URL`). `/api/*` is proxied to the backend on AWS Mumbai EC2. Confirm this matches your actual deployment domain. |
| **Local (via frontend)** | `http://localhost:3000` | `npm run dev`; `/api/*` proxies to the backend at `NEXT_PUBLIC_API_BASE` (default `http://localhost:8000`). |
| **Local (backend direct)** | `http://localhost:8000` | Call the FastAPI backend directly, bypassing the frontend proxy. |

So the full URL is `{base}/api/procurement/po`, e.g.
`https://h-connect.harmonytech.in/api/procurement/po`.

## Getting a token

Obtain a bearer token from the login endpoint, then send it as
`Authorization: Bearer <access_token>` on every request.

| | |
|---|---|
| **Method / Path** | `POST /api/auth/login` |
| **Auth** | None (public) |
| **Handler** | `login` — [`auth.py:32`](../backend/app/routers/auth.py#L32) |

### Request body

| Field | Type | Required | Description |
|-------|------|:--------:|-------------|
| `email` | string | ✅¹ | Staff/supplier login. Use **either** `email` **or** `username`. |
| `username` | string | ✅¹ | Internal-employee login id (for accounts without an email). |
| `password` | string | ✅ | Account password. |
| `company` | string | ❌ | Company code (e.g. `"102"`, `"101"`). Omitted → the default company (`102`). |

¹ Provide exactly one of `email` or `username`.

### Response `200 OK`

```json
{
  "access_token": "eyJhbGciOi...",
  "token_type": "bearer",
  "expires_in": 43200,
  "user": { "id": 1, "email": "admin@example.com", "role": "admin", "...": "..." },
  "company": { "code": "102", "display_name": "Hariom Tech", "...": "..." }
}
```

Use `access_token` as the bearer token. `expires_in` is the lifetime in **seconds**;
re-login when it expires (a `401` from any endpoint means the token is missing/expired).

> **Admin required.** The PO delete/cancel endpoints below require the `admin` role, so
> log in with an admin account.

### Example

```bash
# 1) get a token (admin account)
TOKEN=$(curl -s -X POST "https://h-connect.harmonytech.in/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"YOUR_PASSWORD"}' \
  | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# 2) use it
curl -X DELETE \
  "https://h-connect.harmonytech.in/api/procurement/po?supplier_po_no=000449&supplier_name=Vedant%20Tools%20Pvt%20Ltd" \
  -H "Authorization: Bearer $TOKEN"
```

---

## 1. Delete a whole PO (all material lines) for one supplier

Deletes every material line of a purchase order for a single supplier, and deactivates
that PO's active supplier commitments so they stop surfacing.

| | |
|---|---|
| **Method / Path** | `DELETE /api/procurement/po` |
| **Auth** | Bearer token — **admin role required** |
| **Handler** | `delete_po` — [`procurement.py:203`](../backend/app/routers/procurement.py#L203) |

### Query parameters

| Name | Type | Required | Description |
|------|------|:--------:|-------------|
| `supplier_po_no` | string | ✅ | Supplier PO number to delete. |
| `supplier_name`  | string | ✅ | Supplier name. Required because the CRM PoNo is recycled across suppliers, so a PO number alone is ambiguous. Matched **case-insensitively**. |

### Behavior

1. Selects all `procurement_records` where `supplier_name` (case-insensitive) **and**
   `supplier_po_no` match.
2. Deactivates (`is_active = false`) every active `supplier_material_commitment` for
   that (supplier, PO).
3. Hard-deletes all matched procurement record lines.
4. Commits and returns the counts. Mail/task history is **not** deleted.

### Response `200 OK`

```json
{
  "ok": true,
  "supplier_name": "Vedant Tools Pvt Ltd",
  "supplier_po_no": "000449",
  "deleted_lines": 3,
  "commitments_deactivated": 1
}
```

| Field | Type | Description |
|-------|------|-------------|
| `ok` | boolean | Always `true` on success. |
| `supplier_name` | string | Trimmed supplier name that was matched. |
| `supplier_po_no` | string | Trimmed PO number that was matched. |
| `deleted_lines` | integer | Number of procurement record lines deleted. |
| `commitments_deactivated` | integer | Number of active commitments deactivated. |

### Errors

| Status | When |
|:------:|------|
| `404` | No PO found for that supplier + PO number. |
| `401` | Missing / expired / invalid token. |
| `403` | Authenticated but not an admin (or a portal account). |
| `422` | `supplier_po_no` or `supplier_name` missing. |

### Examples

```bash
curl -X DELETE \
  "https://h-connect.harmonytech.in/api/procurement/po?supplier_po_no=000449&supplier_name=Vedant%20Tools%20Pvt%20Ltd" \
  -H "Authorization: Bearer $TOKEN"
```

```ts
// frontend (same-origin); attach the bearer token as elsewhere in lib/api.ts
await fetch(
  `/api/procurement/po?supplier_po_no=${encodeURIComponent(poNo)}` +
    `&supplier_name=${encodeURIComponent(supplierName)}`,
  { method: "DELETE", headers: { Authorization: `Bearer ${token}` } },
);
```

---

## 2. Delete a single PO line by record id

Deletes one procurement material line by its numeric record id.

| | |
|---|---|
| **Method / Path** | `DELETE /api/procurement/{rec_id}` |
| **Auth** | Bearer token — **admin role required** |
| **Handler** | `delete_record` — [`procurement.py:255`](../backend/app/routers/procurement.py#L255) |

### Path parameters

| Name | Type | Description |
|------|------|-------------|
| `rec_id` | integer | The `procurement_records.id` of the line to delete. |

### Response `200 OK`

```json
{ "ok": true, "deleted_id": 1234 }
```

### Errors

| Status | When |
|:------:|------|
| `404` | No record with that id. |
| `401` | Missing / expired / invalid token. |
| `403` | Authenticated but not an admin (or a portal account). |

### Example

```bash
curl -X DELETE "https://h-connect.harmonytech.in/api/procurement/1234" \
  -H "Authorization: Bearer $TOKEN"
```

---

## Notes

- Both endpoints require the **admin** role (`Depends(require_admin)`), and the
  procurement router is additionally mounted behind the write guard
  (`require_writer_for_writes`), so portal (supplier/employee) accounts are rejected
  outright.
- There is currently **no frontend API-client method** wired for these endpoints
  (`frontend/lib/api.ts` has no `deletePo`); they are called directly or from admin
  tooling.
- To implement a reversible **soft cancel** (set `po_status = "CANCELLED"` instead of
  deleting), add a new endpoint (e.g. `POST /api/procurement/po/cancel`) — it is not
  part of the current API.

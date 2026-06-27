# Supplier Portal API — Mobile App Integration Guide

This document describes the REST API that powers the **Supplier Portal**. It is
the contract for the Android (and any future mobile) app. Every endpoint here is
already live in the backend — nothing extra needs to be built server-side for the
app to work.

> **Audience:** Android developer building the supplier app.
> **Style:** JSON over HTTPS, stateless JWT bearer auth, same endpoints the web
> portal uses.

---

## 1. Base URL

| Environment | Base URL | Notes |
|-------------|----------|-------|
| **Production** | `https://h-connect.harmonytech.in` | Paths under `/api/*` are served by the backend. Use this for the released app. |
| **Local backend (direct)** | `http://localhost:8000` | FastAPI dev server. |
| **Android emulator → local backend** | `http://10.0.2.2:8000` | `10.0.2.2` is the emulator’s alias for the host machine’s `localhost`. |

All paths in this document are **relative to the base URL** and already include
the `/api` prefix, e.g. the full login URL in production is
`https://h-connect.harmonytech.in/api/auth/login`.

**Interactive/auto-generated docs** (great for exploring + client codegen):

- Swagger UI: `{BASE_URL}/docs`
- ReDoc: `{BASE_URL}/redoc`
- OpenAPI JSON (import into Retrofit/OpenAPI generators): `{BASE_URL}/openapi.json`

---

## 2. Authentication

Auth is **stateless JWT**. There are no cookies and no refresh tokens — the app
logs in, stores the access token, and sends it on every request until it expires.

### 2.1 Header on every authenticated request

```
Authorization: Bearer <access_token>
Content-Type: application/json
```

### 2.2 Login

`POST /api/auth/login`

Request:
```json
{
  "email": "buyer.contact@supplier.com",
  "password": "TempPass123"
}
```

Response `200`:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 28800,
  "user": {
    "id": 42,
    "email": "buyer.contact@supplier.com",
    "full_name": null,
    "role": "supplier",
    "is_active": true,
    "supplier_id": 7,
    "must_change_password": true,
    "supplier_name": "M/S SUPERB TOOLS",
    "last_login_at": "2026-06-27T09:14:02",
    "created_at": "2026-05-01T10:00:00",
    "updated_at": "2026-06-27T09:14:02"
  }
}
```

- `expires_in` is **seconds** (default token lifetime is 8 hours / 28800s). When
  the token expires, calls return `401` and the app must log in again.
- A **supplier** account always has `role: "supplier"` and a non-null
  `supplier_id`. (Internal staff accounts have `supplier_id: null` and cannot use
  the portal endpoints — see §2.5.)

Errors:
- `401 { "detail": "Invalid email or password" }`

### 2.3 First login — forced password change

Supplier logins are provisioned by the buyer’s team; the first password is a
temporary one sent by email. On that first login the user object has
**`must_change_password: true`**.

The app should detect this flag right after login and force a change-password
screen before showing portal data. Changing the password clears the flag.

`POST /api/auth/change-password` (requires the bearer token)

Request:
```json
{
  "current_password": "TempPass123",
  "new_password": "MyNewStrongPass!"
}
```
- `new_password` must be **8–128 characters**.

Response `200`:
```json
{ "ok": true }
```

Errors:
- `400 { "detail": "Current password is incorrect" }`
- `422` validation error (e.g. new password too short)

### 2.4 Who am I

`GET /api/auth/me` → returns the same `user` object shape as in the login
response. Useful on app start to validate a stored token and re-read
`must_change_password`. A `401` means the stored token is invalid/expired.

> There is also `GET /api/portal/me` (a lighter supplier-scoped profile) — see §4.1.

### 2.5 Authorization scope (important)

- A supplier token is accepted **only** on `/api/auth/*`, `/api/notifications`,
  and the `/api/portal/*` endpoints in this document.
- All internal staff endpoints (`/api/procurement`, `/api/suppliers`, etc.)
  return **`403`** for a supplier token. Do not call them from the app.
- Every `/api/portal/*` endpoint is automatically scoped to the logged-in
  supplier — you never pass a `supplier_id`; the server derives it from the
  token. A supplier can only ever see their own POs, ASNs, tasks and messages.

---

## 3. Conventions

- **Dates/times**: all timestamps are ISO-8601 strings (e.g.
  `"2026-06-27T09:14:02"`, UTC). Date-only inputs (commitments) use
  `"YYYY-MM-DD"`.
- **Money/quantities**: numbers (may be `null`).
- **Errors**: standard FastAPI shape.
  - Business/auth errors: `{ "detail": "human readable message" }`
  - Validation errors (`422`): `{ "detail": [ { "loc": [...], "msg": "...", "type": "..." } ] }`
- **Status codes** you should handle:
  | Code | Meaning | App action |
  |------|---------|-----------|
  | `200` / `201` | OK | proceed |
  | `400` | Bad request (business rule) | show `detail` |
  | `401` | Missing/expired token | drop token → login screen |
  | `403` | Wrong account type | not a supplier endpoint / not your data |
  | `404` | PO/ASN not found or not yours | show "not found" |
  | `422` | Validation failed | show field errors |
  | `503` / `502` | Assistant temporarily unavailable | retry / hide AI |

---

## 4. Endpoints

All endpoints below require the `Authorization: Bearer` header and a **supplier**
account.

### 4.1 Profile & Dashboard

#### `GET /api/portal/me`
Lightweight profile for the logged-in supplier.
```json
{
  "id": 42,
  "email": "buyer.contact@supplier.com",
  "supplier_id": 7,
  "supplier_name": "M/S SUPERB TOOLS",
  "must_change_password": false
}
```

#### `GET /api/portal/summary`
Dashboard KPI counts.
```json
{
  "supplier_name": "M/S SUPERB TOOLS",
  "total_pos": 12,
  "pending_pos": 9,
  "completed_pos": 3,
  "blocked_count": 1,
  "asn": {
    "active": 4,
    "pending": 2,
    "urgent": 1,
    "finalized": 3,
    "total": 10,
    "drafts": 1
  }
}
```
- `completed_pos` = POs that have a **Delivered** ASN; `pending_pos` = the rest.
- `blocked_count` = POs at risk signal **BLACK**.
- `asn` buckets are explained in §5.3.

### 4.2 Purchase Orders

#### `GET /api/portal/pos`
List of the supplier’s POs (grouped by PO number). Sorted: escalated first, then
worst risk signal, then PO number.
```json
{
  "count": 12,
  "items": [
    {
      "supplier_po_no": "PO-2026-0042",
      "crm_no": "CRM-991",
      "material_count": 5,
      "overall_signal": "RED",
      "po_status": "OPEN",
      "earliest_shipment_date": "2026-07-10T00:00:00",
      "completed": false,
      "asn_count": 1,
      "message_count": 3,
      "escalated": true
    }
  ]
}
```

#### `GET /api/portal/pos/{supplier_po_no}/materials`
Material lines for one PO, each merged with its current commitment (if any).
`{supplier_po_no}` must be URL-encoded if it contains special characters.
```json
[
  {
    "procurement_record_id": 5012,
    "crm_no": "CRM-991",
    "material_name": "Hex Bolt M12",
    "uom": "NOS",
    "qty": 5000,
    "po_date": "2026-06-01T00:00:00",
    "shipment_date": "2026-07-10T00:00:00",
    "signal": "RED",
    "po_status": "OPEN",
    "commitment_date": null,
    "commitment_qty": null,
    "commitment_status": null,
    "commitment_remark": null
  }
]
```
- `shipment_date` is the **required-by** date; `commitment_date` is what the
  supplier has promised (null until they submit one).

### 4.3 Commitments (supplier promises a dispatch date)

This is the core supplier action: for each material, submit a committed dispatch
date. Once **every** material on a PO has a commitment date, the automated
follow-up emails for that PO stop.

#### `POST /api/portal/pos/{supplier_po_no}/commitments`

Request — send one entry per material you want to commit/update:
```json
{
  "items": [
    {
      "procurement_record_id": 5012,
      "commitment_date": "2026-07-08",
      "commitment_qty": 5000,
      "supplier_status": "CONFIRMED",
      "supplier_remark": "Will dispatch in two batches"
    }
  ]
}
```
- `commitment_date` is **`"YYYY-MM-DD"`**. An item **without** a valid
  `commitment_date` is **ignored** (a commitment requires a date).
- `supplier_status` is optional; defaults to `CONFIRMED`. Allowed values in §5.2.
- Only `procurement_record_id`s that belong to this PO + supplier are accepted;
  others are silently skipped.

Response `200`: the **full updated material list** for the PO (same shape as
`GET …/materials`, now with the commitment fields populated). The buyer’s team is
notified automatically.

Errors:
- `404 { "detail": "PO not found for your account" }`

### 4.4 Buyer Tasks (read-only)

#### `GET /api/portal/pos/{supplier_po_no}/tasks`
Read-only view of the internal tasks the buyer’s team is tracking for this PO
(open tasks first, then by due date).
```json
[
  {
    "id": 88,
    "title": "Share revised test certificate",
    "description": "Q2 batch needs updated MTC",
    "material_name": "Hex Bolt M12",
    "status": "IN_PROGRESS",
    "priority": "HIGH",
    "signal": "RED",
    "due_date": "2026-07-02T00:00:00",
    "created_at": "2026-06-20T11:00:00",
    "closed_at": null
  }
]
```
Errors: `404` if the PO isn’t yours.

### 4.5 PO Messaging (shared thread with the buyer)

A simple chat thread per PO, shared with the staff Communication Hub.

#### `GET /api/portal/pos/{supplier_po_no}/messages`
Oldest → newest. Use `mine` to align chat bubbles (true = sent by this supplier).
```json
[
  {
    "id": 301,
    "direction": "OUTGOING",
    "mine": false,
    "author": "Procurement · Harmony × Hariom",
    "subject": "Follow-up | PO No. PO-2026-0042",
    "body": "Please confirm dispatch dates.",
    "mail_type": "PO_FOLLOWUP_RED",
    "status": "SENT",
    "at": "2026-06-25T08:30:00"
  },
  {
    "id": 305,
    "direction": "INCOMING",
    "mine": true,
    "author": "M/S SUPERB TOOLS",
    "subject": "Supplier message · PO PO-2026-0042",
    "body": "Dispatching on the 8th.",
    "mail_type": "PORTAL_MESSAGE",
    "status": "RECEIVED",
    "at": "2026-06-25T10:05:00"
  }
]
```

#### `POST /api/portal/pos/{supplier_po_no}/messages`
Send a message to the buyer (appears in their hub + raises their unread badge).

Request:
```json
{ "body": "Dispatching on the 8th.", "subject": "Optional subject" }
```
- `body` is required (min length 1). `subject` is optional (auto-generated if
  omitted).

Response `201`: the created `PortalMessage` (same shape as above).
Errors: `404` if the PO isn’t yours.

### 4.6 ASN — Advance Shipping Notices (shipment tracking)

#### `GET /api/portal/asns/summary`
The 4 dashboard cards (same `asn` object embedded in `/summary`):
```json
{ "active": 4, "pending": 2, "urgent": 1, "finalized": 3, "total": 10, "drafts": 1 }
```

#### `GET /api/portal/asns`
Query params (all optional):
| Param | Values | Meaning |
|-------|--------|---------|
| `tab` | `active` \| `history` \| `drafts` | filter by lifecycle bucket; omit = all |
| `search` | string | matches ASN no / PO / carrier / tracking / supplier name |

```json
{
  "count": 10,
  "items": [ { /* AsnOut, see below */ } ]
}
```

#### `POST /api/portal/asns`  → create (draft or submit)
Request:
```json
{
  "supplier_po_no": "PO-2026-0042",
  "crm_no": "CRM-991",
  "carrier_name": "Maersk",
  "tracking_no": "MAEU123456",
  "transport_mode": "SEA",
  "origin": "Nhava Sheva",
  "destination": "Hamburg",
  "dispatch_date": "2026-07-08T00:00:00",
  "eta": "2026-07-30T00:00:00",
  "remarks": "2 pallets",
  "items": [
    {
      "procurement_record_id": 5012,
      "material_name": "Hex Bolt M12",
      "material_code": "CRM-991",
      "po_qty": 5000,
      "qty_shipped": 3000,
      "uom": "NOS",
      "invoice_no": "INV-7781"
    }
  ],
  "submit": true
}
```
- `submit: false` → saved as **DRAFT**; `submit: true` → status **SUBMITTED**
  (and the buyer is notified).
- `transport_mode` must be one of `SEA, AIR, ROAD, RAIL` (or omitted).
- `supplier_po_no` must be a PO that belongs to this supplier, else `400`.

Response `201`: the created `AsnOut`.

#### `GET /api/portal/asns/{asn_id}` → one ASN (with items + events)

#### `PATCH /api/portal/asns/{asn_id}` → edit
Send only the fields you want to change (partial update). Same field names as
create, plus `alert`, `alert_reason`, and `submit`.
```json
{ "tracking_no": "MAEU999999", "eta": "2026-08-02T00:00:00" }
```
Response `200`: updated `AsnOut`.

#### `POST /api/portal/asns/{asn_id}/events` → advance shipment stage
Appends a tracking event and recomputes status/label/progress.
```json
{
  "stage": "IN_TRANSIT",
  "location": "Suez Canal",
  "note": "On schedule",
  "occurred_at": "2026-07-15T06:00:00",
  "alert": false,
  "alert_reason": null,
  "label": null
}
```
- `stage` must be a valid status (§5.3); unknown → `422`.
- Setting `stage: "DELIVERED"` marks the ASN delivered (notifies the buyer and
  counts the PO as completed).

Response `200`: updated `AsnOut`.

**`AsnOut` shape:**
```json
{
  "id": 120,
  "asn_no": "ASN-2026-0010",
  "supplier_id": 7,
  "supplier_name": "M/S SUPERB TOOLS",
  "supplier_po_no": "PO-2026-0042",
  "crm_no": "CRM-991",
  "carrier_name": "Maersk",
  "tracking_no": "MAEU123456",
  "transport_mode": "SEA",
  "origin": "Nhava Sheva",
  "destination": "Hamburg",
  "dispatch_date": "2026-07-08T00:00:00",
  "eta": "2026-07-30T00:00:00",
  "delivered_at": null,
  "status": "IN_TRANSIT",
  "status_label": "In Transit",
  "alert": false,
  "alert_reason": null,
  "progress_percent": 55,
  "remarks": "2 pallets",
  "created_by_email": "buyer.contact@supplier.com",
  "created_at": "2026-07-08T09:00:00",
  "updated_at": "2026-07-15T06:00:00",
  "items": [
    {
      "id": 1,
      "procurement_record_id": 5012,
      "material_name": "Hex Bolt M12",
      "material_code": "CRM-991",
      "po_qty": 5000,
      "qty_shipped": 3000,
      "uom": "NOS",
      "invoice_no": "INV-7781"
    }
  ],
  "events": [
    {
      "id": 9,
      "stage": "IN_TRANSIT",
      "status_label": "In Transit",
      "location": "Suez Canal",
      "note": "On schedule",
      "occurred_at": "2026-07-15T06:00:00",
      "created_by": "buyer.contact@supplier.com"
    }
  ]
}
```

### 4.7 Assistant (“Harmony Intelligent”) — optional

An AI assistant scoped to this supplier’s own POs/ASNs/messages.

#### `GET /api/portal/assistant/health`
```json
{ "enabled": true }
```
Hide the chat UI when `enabled` is false.

#### `POST /api/portal/assistant/chat`
Request (send the conversation so far):
```json
{
  "messages": [
    { "role": "user", "content": "Which of my POs are overdue?" }
  ]
}
```
Response `200`:
```json
{
  "reply": "PO-2026-0042 has 2 overdue materials...",
  "model": "claude-...",
  "tools_used": ["list_pos"]
}
```
Errors: `422` if `messages` is empty; `503` if the assistant is disabled; `502`
on an upstream failure.

---

## 5. Reference (enums)

### 5.1 Risk signal (`overall_signal`, `signal`)
`GREEN` → `YELLOW` → `RED` → `BLACK` (best → worst). `BLACK` = blocked/critical.

### 5.2 Commitment status (`supplier_status`)
`CONFIRMED` (default), `DELAYED`, `PARTIAL`, `DISPATCHED`, `ON_HOLD`, `CANCELLED`.

### 5.3 ASN lifecycle (`status` / `stage`)
| Status | Progress % | Default label | Dashboard bucket |
|--------|-----------:|---------------|------------------|
| `DRAFT` | 0 | Draft | drafts |
| `SUBMITTED` | 10 | Created | active |
| `DISPATCHED` | 25 | On Board / Departed | active |
| `IN_TRANSIT` | 55 | In Transit | active |
| `AT_CUSTOMS` | 70 | At Customs | pending |
| `INBOUND_HUB` | 85 | Inbound Hub | pending |
| `OUT_FOR_DELIVERY` | 95 | Arriving Soon | active |
| `DELIVERED` | 100 | Delivered | finalized |
| `CANCELLED` | 0 | Cancelled | — |

Summary card definitions:
- **active** = SUBMITTED / DISPATCHED / IN_TRANSIT / OUT_FOR_DELIVERY
- **pending** = AT_CUSTOMS / INBOUND_HUB
- **urgent** = `alert == true` and not delivered/cancelled
- **finalized** = recently DELIVERED
- **drafts** = DRAFT

### 5.4 Transport mode (`transport_mode`)
`SEA`, `AIR`, `ROAD`, `RAIL`.

---

## 6. Endpoint summary

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/auth/login` | Log in, get token |
| GET | `/api/auth/me` | Validate token / read profile |
| POST | `/api/auth/change-password` | First-login + change password |
| GET | `/api/portal/me` | Supplier profile (light) |
| GET | `/api/portal/summary` | Dashboard KPIs |
| GET | `/api/portal/pos` | List POs |
| GET | `/api/portal/pos/{po}/materials` | PO material lines + commitments |
| POST | `/api/portal/pos/{po}/commitments` | Submit/update commitment dates |
| GET | `/api/portal/pos/{po}/tasks` | Buyer tasks (read-only) |
| GET | `/api/portal/pos/{po}/messages` | Message thread |
| POST | `/api/portal/pos/{po}/messages` | Send message |
| GET | `/api/portal/asns/summary` | ASN cards |
| GET | `/api/portal/asns` | List ASNs (`tab`, `search`) |
| POST | `/api/portal/asns` | Create ASN (draft/submit) |
| GET | `/api/portal/asns/{id}` | ASN detail |
| PATCH | `/api/portal/asns/{id}` | Edit ASN |
| POST | `/api/portal/asns/{id}/events` | Advance shipment stage |
| GET | `/api/portal/assistant/health` | Assistant availability |
| POST | `/api/portal/assistant/chat` | Ask the assistant |

---

## 7. Android integration notes

### 7.1 Auth interceptor (OkHttp/Retrofit, Kotlin)
Store the token securely (EncryptedSharedPreferences / Keystore) and attach it to
every request:
```kotlin
class AuthInterceptor(private val tokenProvider: () -> String?) : Interceptor {
    override fun intercept(chain: Interceptor.Chain): Response {
        val req = chain.request().newBuilder().apply {
            tokenProvider()?.let { header("Authorization", "Bearer $it") }
        }.build()
        val res = chain.proceed(req)
        if (res.code == 401) {
            // token expired/invalid → clear it and route to the login screen
        }
        return res
    }
}
```

### 7.2 Retrofit service (excerpt)
```kotlin
interface PortalApi {
    @POST("api/auth/login")
    suspend fun login(@Body body: LoginRequest): LoginResponse

    @POST("api/auth/change-password")
    suspend fun changePassword(@Body body: ChangePasswordRequest): OkResponse

    @GET("api/portal/summary")
    suspend fun summary(): PortalSummary

    @GET("api/portal/pos")
    suspend fun pos(): PortalPoListResponse

    @GET("api/portal/pos/{po}/materials")
    suspend fun materials(@Path("po") po: String): List<PortalPoMaterial>

    @POST("api/portal/pos/{po}/commitments")
    suspend fun submitCommitments(
        @Path("po") po: String,
        @Body body: CommitmentSubmit
    ): List<PortalPoMaterial>

    @GET("api/portal/asns")
    suspend fun asns(
        @Query("tab") tab: String? = null,
        @Query("search") search: String? = null
    ): AsnListResponse

    @POST("api/portal/asns")
    suspend fun createAsn(@Body body: AsnCreate): AsnOut

    @POST("api/portal/asns/{id}/events")
    suspend fun addAsnEvent(@Path("id") id: Long, @Body body: AsnEventIn): AsnOut
}
```

### 7.3 Recommended app flow
1. **Login** → save `access_token` + `user`.
2. If `user.must_change_password == true` → force change-password screen →
   `POST /api/auth/change-password` → continue.
3. **Dashboard** → `GET /api/portal/summary`.
4. **PO list** → `GET /api/portal/pos` → tap → `GET …/materials` (+ `…/tasks`,
   `…/messages`).
5. **Commit** dates → `POST …/commitments`.
6. **Shipments** → `GET /api/portal/asns?tab=active` → create/advance ASNs.
7. On any `401`, clear the token and return to login.

### 7.4 Codegen shortcut
Because the backend is FastAPI, `{BASE_URL}/openapi.json` is a complete OpenAPI 3
spec. You can generate Kotlin models + a Retrofit client directly from it with
the OpenAPI Generator (`-g kotlin`), instead of hand-writing the DTOs.

---

## 8. CORS / network

- The backend allows the configured web origins via CORS, but **CORS does not
  affect native Android** (it only applies to browser requests). The app can call
  the API directly.
- Production is HTTPS. For local testing over plain HTTP you’ll need a network
  security config / `usesCleartextTraffic` for the dev host.

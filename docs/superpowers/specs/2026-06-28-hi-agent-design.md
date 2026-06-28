# HI Agent — Communication Hub Chat Assistant

**Date:** 2026-06-28
**Status:** Approved design (pending implementation plan)
**Author:** Brainstormed with Claude Code

## 1. Summary

Add a `/hi` chat command to the Communication Hub thread composer that activates the
**HI Agent** — an LLM-driven assistant that operates on the *current PO/supplier thread*.
The user types natural language after `/hi` (e.g. `/hi summarise this`,
`/hi send a summary to @anjali`, `/hi give followup to @pramod`). The agent interprets
intent, calls a bounded set of tools, and either answers inline or proposes an action the
user must confirm before anything leaves the system.

The agent is **dynamic**: it does whatever maps to its tools, and gracefully declines what
does not ("I can't do that, but I can summarise, draft, forward, or schedule — want one of
those?").

## 2. Core principle — the agent proposes, it never disposes

To structurally honor the two hard requirements — **no delete/edit access** and **confirm
before any email** — the agent's tools are limited to **read**, **create-draft**, and
**create-pending-subscription** operations. **No agent tool sends email or mutates/deletes
existing data.**

Every outward action becomes a `DRAFT` message or a `PENDING` subscription row that a human
confirms via a Confirm/Cancel button. Confirmation flips the row to `READY` / `ACTIVE`, and
delivery rides the **existing** `mail_send_worker`. This makes the safety boundary impossible
to bypass through prompt manipulation: there is simply no tool that delivers mail.

The one authorized exception is **automated dispatch** of already-confirmed standing
subscriptions (followups and scheduled summaries), performed by a background cron — not by
the interactive agent. Standing consent is captured once at subscription creation (itself
confirm-gated), and these subscriptions are restricted to internal recipients (see §8).

## 3. Scope & context

- **Entry point:** `/hi` is typed in the Communication Hub thread composer for a specific
  supplier/PO. "The conversation" is always that thread.
- **Thread context** is assembled from the existing merged thread builder
  (`GET /api/communication-hub/thread`), which already combines legacy `mail_history` and the
  new `CommunicationMessage` records plus PO context for a given supplier/PO.
- The agent always knows which supplier/PO it is acting on — the user never has to specify it.

## 4. Architecture & data flow

### Frontend
- In the thread composer (hub view and `frontend/app/eportal/communication/page.tsx`):
  when the composer text starts with `/hi `, route the submission to the agent endpoint
  instead of the normal reply endpoint.
- Render the agent's text reply, plus any **preview cards** for pending actions:
  - **Email draft card:** recipient, subject, body + Send / Cancel.
  - **Subscription card:** kind (followup / scheduled summary), recipient, schedule + Confirm / Cancel.
- Confirm posts to the confirm endpoint; Cancel discards the pending row.

### Backend endpoints (added to `app/routers/communication_hub.py`)
- `POST /api/communication-hub/agent`
  - Body: `{ message, supplier_id, procurement_record_id | supplier_po_no }`
  - Runs the agent on the current thread; returns `{ reply, pending_actions[] }`.
- `POST /api/communication-hub/agent/confirm`
  - Body: `{ action_type: "draft" | "subscription", id }`
  - Confirms a pending draft (→ `READY`, queue `mail_send_worker.send_message_now`) or a
    pending subscription (→ `ACTIVE`).

### Components (each isolated, single-purpose)
- `app/services/hi_agent_service.py` — **orchestrator.** Builds the system prompt
  (capabilities + graceful-decline rules), assembles thread context, calls
  `ai_service.chat_with_tools(messages, tools, executor, system, max_rounds)`, and returns
  `{ reply, pending_actions[] }`. Pending actions are the draft/subscription rows created
  during the turn that await confirmation.
- `app/services/hi_agent_tools.py` — **tool schemas + executor.** Each tool is a thin
  delegate to an existing service. No tool sends mail or edits/deletes anything.
- `app/models/agent_subscription.py` + `app/services/agent_subscription_service.py` —
  standing followups & scheduled summaries.
- `app/scheduler/jobs.py` — one new job `agent_dispatch_cron`.

## 5. Toolset (read / create-only)

| Tool | Purpose | Backed by |
|---|---|---|
| `read_thread` | Fetch the thread's messages + PO context | existing `/thread` builder |
| `summarize_thread` | Summary of this conversation | `ai_service.summarize_thread()` |
| `extract_action_items` | Pending questions, commitments, next actions | LLM over thread |
| `explain_signal` | Why this PO is GREEN/YELLOW/RED/BLACK, days late | PO record + thread |
| `resolve_recipient` | `@handle` → user/supplier candidate(s) + email (no send) | `user_service`, `supplier_email` |
| `draft_email` | Create a `DRAFT` `CommunicationMessage` + return preview | `communication_message_service` |
| `draft_reply` | Compose a reply DRAFT into the thread | `ai_service.suggest_customer_reply()` |
| `create_subscription` | Create a **PENDING** followup or scheduled summary | `agent_subscription_service` |
| `list_subscriptions` | List active followups/summaries on this thread | read-only |

**Dynamic behavior:** the LLM selects tools for whatever the user phrases. If no tool fits,
the system prompt instructs it to decline gracefully and offer its real capabilities. There
is no fixed command grammar — `/hi` is a natural-language entry point.

## 6. Command mapping (the five requested behaviors)

1. **Summarise the conversation** → `summarize_thread`. Read-only, answered inline.
2. **Send this to @user (one-time email)** → `resolve_recipient` + `draft_email` → preview
   card → user confirms → `READY` → sent via `mail_send_worker`. Suppliers allowed here
   (confirm-gated).
3. **Give followup to @user** → `create_subscription(kind=FOLLOWUP)` → confirm card →
   `ACTIVE`. Thereafter `agent_dispatch_cron` forwards each new message on the thread
   (in-app notification + one email per message) using a `last_forwarded_message_id`
   high-water mark so nothing double-sends. **Internal recipients only** (§8).
4. **Send summary to @user (+ schedule)** →
   - One-time: `summarize_thread` then `draft_email` (confirm-gated).
   - Recurring: `create_subscription(kind=SCHEDULED_SUMMARY, schedule=…)`; dispatched by
     `agent_dispatch_cron` when `next_run_at` is due. **Default cadence: daily 09:00**, with
     weekly and custom-cron options. **Internal recipients only** (§8).
5. **Extras (all included as read/draft tools):**
   - Extract action items / open questions (`extract_action_items`).
   - Draft a reply, no auto-send (`draft_reply`, confirm-gated).
   - Status / signal explainer (`explain_signal`).
   - List my subscriptions (`list_subscriptions`).

## 7. Subscription data model

Table `agent_subscription`:

| Column | Notes |
|---|---|
| `id` | PK |
| `kind` | `FOLLOWUP` \| `SCHEDULED_SUMMARY` |
| `supplier_id` | thread scope |
| `procurement_record_id` | thread scope (nullable) |
| `supplier_po_no` | thread scope (nullable) |
| `recipient_user_id` | internal user FK |
| `recipient_email` | resolved at creation |
| `recipient_label` | display name |
| `created_by_user_id` | who set it up |
| `status` | `PENDING` \| `ACTIVE` \| `PAUSED` \| `CANCELLED` |
| `last_forwarded_message_id` | high-water mark (FOLLOWUP) |
| `schedule` | cron/preset (SCHEDULED_SUMMARY) |
| `next_run_at` | next due time (SCHEDULED_SUMMARY) |
| `last_run_at` | last dispatch time |
| `created_at`, `updated_at` | timestamps |

The agent only **creates** (`PENDING`) and **lists** subscriptions. Pause / unsubscribe is a
later UI action, deliberately **not** an agent tool (honoring no-edit/no-delete). Confirmation
flips `PENDING` → `ACTIVE`.

## 8. Recipient policy

- **One-time sends** (`draft_email`) may target **internal users or suppliers**, always
  confirm-gated via a preview card.
- **Standing subscriptions** (`FOLLOWUP`, `SCHEDULED_SUMMARY`) are restricted to **internal
  recipients only**. Auto-emailing internal conversation to a supplier on a timer, with no
  per-message human check, is rarely intended and carries outsized blast radius. The agent
  declines supplier recipients for subscriptions and explains why.
- Internal `@handle` resolution uses `user_service` (username / full_name) → `User.email`.
  Supplier resolution (one-time only) uses `supplier_email` contacts.

## 9. Dispatch job

`agent_dispatch_cron` (default interval 5 min, configurable like the other engine jobs via
`engine_jobs`):

- **FOLLOWUP:** for each `ACTIVE` subscription, find thread messages with
  `id > last_forwarded_message_id`; for each, create an in-app notification and an OUTGOING
  forward email (via `communication_message_service` + `mail_send_worker`), then advance the
  high-water mark. One email per new message.
- **SCHEDULED_SUMMARY:** for each `ACTIVE` subscription where `next_run_at <= now`, build a
  thread summary, create the OUTGOING summary email + notification, set `last_run_at`, and
  advance `next_run_at` per the schedule.

Idempotent via the high-water mark and `next_run_at` advancement.

## 10. RBAC

- `/hi` is usable by staff (`user` and above) and by employee PO owners on their own
  threads, reusing the existing thread guards.
- Supplier portal accounts cannot drive the agent.

## 11. LLM integration

Reuses the existing `app/services/ai_service.py` (OpenAI-compatible client, NVIDIA NIM /
`meta/llama-3.3-70b-instruct` by default) and its `chat_with_tools()` executor pattern.
When `LLM_ENABLED` is false, the agent falls back to a deterministic minimal path
(summaries return a templated digest; intent that needs the LLM returns a clear "AI is
disabled" message) so the feature degrades gracefully and tests run without a live model.

## 12. Testing (pytest)

- Intent routing with a mocked LLM/executor (each of the five behaviors picks the right tool).
- `@handle` recipient resolution (internal user; supplier for one-time; supplier rejected for
  subscription).
- **Draft is created but nothing is sent until confirm** (assert no `READY`/sent before
  confirm endpoint is called).
- Subscription lifecycle: create `PENDING` → confirm `ACTIVE` → dispatch.
- High-water-mark no-double-send on FOLLOWUP.
- Due-summary scheduling advances `next_run_at`.
- Graceful decline for out-of-scope requests.
- LLM-disabled fallback path.

## 13. Out of scope (YAGNI / deferred)

- Pause / unsubscribe via the agent (UI action later).
- Suppliers as subscription recipients.
- Editing or deleting existing messages/POs/tasks through the agent.
- Multi-thread / cross-PO agent operation (entry point is the current thread only).

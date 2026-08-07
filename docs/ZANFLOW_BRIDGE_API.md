# The ZanFlow bridge

**ZanFlow Materials** is Zanvar's material-enquiry system: somebody needs a part
that is not in the ERP, raises it with a photo, and the enquiry is worked
through seven stages ending at MDN. When a material line there is assigned to a
person, that person needs to see it here — in the portal they already work in,
not in a second application they have to remember to open.

So an assignment there becomes a task here, and what happens to that task goes
back.

```
ZanFlow                                     this system

  assigns a material line   ──────────▶     POST /api/bridge/tasks    upsert
                                             X-Webhook-Secret

  the material line's page  ◀──────────      status · progress · comments
   X-Bridge-Secret                           (bridge_service.notify_zanflow)
```

## Where it lives

| | |
|---|---|
| Inbound router | `app/routers/bridge.py` — mounted open in `main.py`, guarded by `require_webhook_secret` |
| Both halves | `app/services/bridge_service.py` |
| Wire types | `app/schemas/bridge.py` |
| Outbound hooks | `routers/communication.py` → `update_task`, `add_task_comment` |
| Columns | `communication_tasks.external_system / external_ref / external_url` |
| Tests | `tests/test_bridge_service.py`, `tests/test_bridge_routes.py` |

Two hooks cover every surface, because the staff board, the employee portal and
the supplier portal all delegate their task PATCH and their comments to those
two functions in `communication.py`.

## Configuration

Inbound needs nothing new — it reuses `WEBHOOK_SECRET`, exactly as
`/api/webhooks/*` does, and fails closed when that is unset.

Outbound needs the ZanFlow address and the secret it will check:

```
ZANFLOW_API_BASE=https://harmony-task-manager.vercel.app
ZANFLOW_CALLBACK_SECRET=<must equal FOLLOWUP_CALLBACK_SECRET in ZanFlow's env>
ZANFLOW_TIMEOUT_SECONDS=10
```

Leave `ZANFLOW_API_BASE` empty and the callback is a silent no-op: tasks still
arrive, the mirror over there just stops updating.

No migration. `core/schema_evolve.py` adds the three columns on boot.

## The endpoints

### `POST /api/bridge/tasks`

Upsert on `(external_system, external_ref)` — one task per material line,
however many times ZanFlow pushes it. Answers `200` either way; `created` in
the body says which it was.

```json
{ "external_system": "zanflow", "external_ref": "MR-1042-M2",
  "title": "MR-1042-M2 · Bearing 6205 ZZ", "priority": "HIGH",
  "status": "IN_PROGRESS", "due_date": "2026-08-20T00:00:00",
  "assignee": { "followup_user_id": 5, "email": "…", "display_name": "Pramod Kale" },
  "assigned_by": "Ninad Pawar" }
```

```json
{ "task_id": 1, "created": true, "status": "IN_PROGRESS",
  "assigned_to_user_id": 5, "assigned_to": "Pramod Kale",
  "unmapped_assignee": false }
```

The assignee is resolved in three steps: the id ZanFlow cached, then the email,
then nothing. `unmapped_assignee: true` means the task was created and is
sitting on the staff board with a name on it but no owner — a normal outcome,
not a failure. Supplier accounts and deactivated accounts are never assignees.

`task_source` is always `INTERNAL`; the caller cannot set it. `status` seeds a
new task and is never written again — once it exists, whoever works it owns its
status.

### `GET /api/bridge/assignees[?email=]`

`task_assignment_service.list_assignees` plus each account's email, so ZanFlow's
admin screen can offer a mapping dropdown. Read-only.

### `GET /api/bridge/tasks/{external_ref}`

Current state for one external record, for reconciling without re-pushing.
`{"found": false}` when there is none.

### The callback out

Fired from `update_task` when `status` or `progress_percent` actually changed,
and from `add_task_comment` on every comment. Best effort by construction:
`safe_notify` never raises, so a ZanFlow outage cannot make a portal user's
status change fail. It carries current state rather than a delta, so the next
change re-sends everything and the mirror heals itself.

`actor_user_id` is in the body because ZanFlow's `zf_comments.author_id` is
`NOT NULL` — it lets a comment made here be attributed to the right person
there rather than arriving anonymous.

## What the bridge does not do

Watchers, attachments and reminders do not cross. Deleting a task here deletes
nothing there. And a status set here never moves a ZanFlow stage: those stages
are guarded by rules this system knows nothing about, so the mirror over there
is deliberately inert.

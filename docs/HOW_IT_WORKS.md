# How the Supplier Follow-up System Works (Plain English)

_Last updated: 2026-06-17_

This document explains the whole system in simple words — what it does, how a
mail travels through it, how follow-ups go out, and how the AI helps at each
step. No deep tech knowledge needed.

---

## 1. What is this system, in one line?

> It is a **control tower for purchase orders**. It watches your supplier
> mailbox, understands replies, chases late suppliers automatically, lets your
> team handle customer questions, and now has an **AI brain** that reads your
> data, drafts mails, scores risk, and answers questions.

---

## 2. The big picture

```
                         ┌──────────────────────────────┐
                         │        YOUR TEAM (browser)    │
                         │   Frontend on Vercel (Next.js)│
                         └───────────────┬───────────────┘
                                         │  (HTTPS / API calls)
                                         ▼
   ┌───────────────────────────────────────────────────────────────────┐
   │                  BACKEND on EC2  (FastAPI, always on)               │
   │                                                                     │
   │   Web API  ─────────────  Background Scheduler (runs on a timer)    │
   │   (handles clicks)        • fetch mailbox    • send mails           │
   │                           • generate follow-ups  • score risk       │
   │                           • index mails for AI memory               │
   │                                                                     │
   │   AI Brain (talks to NVIDIA llama model + embeddings)               │
   └───────────────────────────────┬───────────────────────────────────┘
                                    │
                                    ▼
                   ┌────────────────────────────────┐
                   │   DATABASE — Supabase Postgres  │
                   │   (orders, mails, users, +      │
                   │    pgvector "memory" for AI)    │
                   └────────────────────────────────┘

           ▲                                            ▲
           │ reads supplier replies (POP3/IMAP)         │ sends mails (SMTP)
           └──────────────  Mailbox: stores@hariomtech.in ─────────────┘
```

**Three moving parts:**
1. **Frontend (Vercel)** — the screens your team uses.
2. **Backend (EC2)** — the engine. It has a *web API* (responds to clicks) and a
   *scheduler* (does timed jobs on its own, even when nobody is logged in).
3. **Database (Supabase)** — where everything is stored.

---

## 3. The "traffic light" idea (signals)

Every order line gets a colour that shows how worried we should be:

| Signal | Meaning |
|--------|---------|
| 🟢 **GREEN** | On track, plenty of time. |
| 🟡 **YELLOW** | Getting close to the due date — keep an eye on it. |
| 🔴 **RED** | Late / overdue — needs chasing. |
| ⚫ **BLACK** | Critical — very late, escalate to managers. |

The system uses these colours everywhere to decide *who to chase* and *how
urgently*.

---

## 4. How a mail is READ (the inbox flow)

This is the heart of the system. Every few minutes the scheduler checks the
mailbox and processes new mail.

```
        Mailbox (stores@hariomtech.in)
                  │
                  ▼
   [1] Scheduler wakes up (every few minutes)
                  │
                  ▼
   [2] Connect + download NEW mails only (skips ones already seen)
                  │
                  ▼
   [3] Read each mail: who sent it? subject? body?
                  │
                  ▼
   [4] Try to understand it:
        • Is the sender a known supplier?
        • Does the subject/body mention a PO number?
        • What status did they report? (confirmed / delayed / dispatched …)
                  │
                  ▼
   [5] DECIDE where it belongs ───────────────┐
        │                                      │
        ▼                                      ▼
   KNOWN supplier OR matched a PO         UNKNOWN sender, no PO
        │                                      │
        ▼                                      ▼
   "Supplier reply"                       "Customer mail"
   → save to the order's thread           → save to Customer Inbox
   → update the order's status/date       → AI auto-triages it (see §7)
   → update material commitments          → routed to the right team
   → remember it in AI memory             → remembered in AI memory
```

**In simple words:**
- If a **supplier** replies about an order, the system files it under that
  order, updates the order's status and promised date automatically, and learns
  from it.
- If a **stranger/customer** writes in (a question, complaint, etc.), it goes to
  the **Customer Inbox** for a human to handle — and the AI immediately reads it
  and tags it (urgent? complaint? what to do?).

> Nothing is ever lost: even a mail we don't recognise lands in the Customer
> Inbox instead of disappearing.

---

## 5. How a FOLLOW-UP goes out (chasing suppliers)

The system chases suppliers **automatically** so your team doesn't have to
remember every due date.

```
   [1] Scheduler reviews all open purchase orders (grouped by supplier + PO)
                  │
                  ▼
   [2] For each PO: is it DUE for a follow-up?
        (based on its colour, the due date, and when we last chased)
                  │
                  ▼
   [3] If due → build the follow-up email
        • Normal POs → a clean template with a material table
        • 🔴 RED / ⚫ BLACK POs → the AI writes a firmer, smarter message
          (grounded in the real facts + how this supplier replied before)
                  │
                  ▼
   [4] Queue the email (status: READY)
                  │
                  ▼
   [5] Another scheduler job sends it over SMTP, marks it SENT
        (retries automatically if sending fails)
```

The email asks the supplier to reply **using a table** (one row per material).
When they reply, step §4 above reads that table and updates each material's
promised date and status — closing the loop.

**Safety:** some actions (like auto-reply acknowledgements) are saved as
**drafts** and wait for a manager to approve them on the **Approvals** page
before they are sent. Nothing risky goes out on its own.

---

## 6. The AI brain — what it does

There are **six** AI features. All of them are safe: if the AI is ever slow or
off, the system quietly falls back to templates and simple rules — it never
breaks.

### 6.1 The Assistant (a chatbot that can actually look things up)

Old chatbots only "talk". This one **reads your live data** before answering.

```
   You ask: "Which POs are most at risk right now?"
                  │
                  ▼
   AI thinks: "I should look this up" → calls a TOOL
                  │
                  ▼
   Tool runs a real database query → returns the actual POs
                  │
                  ▼
   AI writes the answer using those real numbers
   "SBT-2526-0091 (Superb Tools) is 58 days late, BLACK signal …"
```

The tools it can use:
- **get_overview** — overall counts by colour, open customer mails.
- **list_red_pos** — the most at-risk purchase orders.
- **get_po_status** — full detail of one PO.
- **search_supplier** — find a supplier and their order mix.
- **get_mail_thread** — the email history for a PO.
- **search_knowledge** — search the **memory** of past mails (see §6.5).

You see little chips under each answer showing which tools it used, so you can
trust where the numbers came from.

### 6.2 Auto-triage (sorting incoming customer mail)

When a customer mail arrives, the AI instantly tags it:
- **Category** (complaint / dispatch / finance / general …)
- **Urgency** (HIGH / MEDIUM / LOW)
- **Action** (reply / escalate / resolve / monitor)
- **One-line summary**

So your team sees, at a glance, *"this is a HIGH-urgency complaint, escalate"* —
without reading every mail first. Coloured badges show in the inbox.

### 6.3 Smart supplier follow-ups

For RED/BLACK (late) orders, the AI writes the chasing email instead of using a
plain template — firmer tone, the real delay facts, and even *how this supplier
responded to past chases*. Falls back to the template if anything goes wrong.

### 6.4 Delay-risk prediction

Every order gets a **risk score (0–100)** and a band (LOW / MEDIUM / HIGH),
re-calculated every hour. It looks at: the colour, how overdue it is, how many
times we've chased, whether there's a promised date, escalation level, etc.
This powers the **AI Insights → Delivery risk** table (most at-risk first), with
a plain-English reason for each ("6 days past due, 4 follow-ups sent").

> This is a **rule-based calculation**, not the LLM — so it's instant, free, and
> always available.

### 6.5 Memory (RAG) — the AI remembers your history

This is the part that makes the Assistant smart over time.

```
   Every customer mail + supplier reply
                  │
                  ▼
   Turned into a "fingerprint" of its meaning (an embedding, by NVIDIA)
                  │
                  ▼
   Stored in pgvector (a special memory table inside Supabase)
                  │
                  ▼
   Later, the Assistant can search this memory by MEANING, not keywords
   e.g. "how did we handle late steel deliveries before?" → finds real
        past threads even if they used different words.
```

So the Assistant (and the smart follow-ups) can pull up **precedent** — real
past cases — to give better answers and drafts.

### 6.6 Supplier scorecards

A weekly-style **report card** for each supplier: a grade **A–D** based on how
many of their orders go RED/BLACK, how often they're overdue, how many chases
they need, and how often they reply. Shown on **AI Insights → Supplier
scorecards** (worst performers first).

---

## 7. A full example, start to finish

Let's follow one real situation:

1. **A customer emails:** *"Where is my order? It's very late and the part is
   defective!"*
2. The scheduler **fetches** it. The sender isn't a known supplier and there's
   no PO match → it lands in the **Customer Inbox**.
3. The **AI triages** it instantly: `COMPLAINT · HIGH urgency · ESCALATE` with a
   one-line summary. It also **remembers** it in AI memory.
4. Your team sees the red **HIGH** badge, opens it, and clicks **Summarize** to
   get the gist, or **Triage** to re-run the tags.
5. They check the linked PO. Meanwhile that PO is **RED**, so the system has
   already been **auto-chasing the supplier** with AI-written follow-ups.
6. The supplier **replies** with a new promised date in the reply table. The
   scheduler reads it, **updates the order's commitment date** automatically,
   and remembers the reply.
7. A manager opens the **Assistant** and asks *"what's the latest on this
   supplier?"* — the AI looks up the live thread + memory and answers.
8. The team replies to the customer (a branded HTML mail), and the order's
   **risk score** drops at the next hourly re-scoring.

Every step is visible in the screens, and the AI quietly helps at each one.

---

## 8. Who can do what (roles)

| Role | Can do |
|------|--------|
| 👁 **Viewer** | Read everything. No changes. |
| ✍ **User** | Everything a viewer can, plus create/edit, reply, run AI triage/summary. |
| 🧑‍💼 **Manager** | Everything a user can, plus send/approve mails, change settings, rescore risk, backfill AI memory. |
| 🛡 **Admin** | Everything, plus manage users. |

---

## 9. Where the data lives

| Thing | Stored in |
|-------|-----------|
| Purchase orders / order lines | `procurement_records` |
| Supplier list | `supplier_master`, supplier emails | 
| All emails (in & out) | `communication_messages` |
| Customer inbox mails | `customer_mails` (incl. AI triage tags) |
| Supplier promised dates | `supplier_material_commitments` |
| Tasks | `communication_tasks` |
| Users / logins | `users` |
| AI memory (embeddings) | `knowledge_chunks` (pgvector) |
| Scheduler job history | `engine_jobs`, `engine_job_logs` |

---

## 10. The timed jobs (the scheduler)

These run on their own in the background. You can see and tune them in
**Settings → Cron jobs**.

| Job | What it does | Default every |
|-----|--------------|---------------|
| Mail Inbox Fetch | Read new supplier/customer mail | 5–10 min |
| PO Follow-up Generator | Build chasing mails for due POs | 5 min |
| Mail Send Worker | Send queued mails over SMTP | 5 min |
| Auto Reply Drafts | Draft acknowledgements (await approval) | 15 min |
| Status Change Scan | Housekeeping on status updates | 15 min |
| **Delay Risk Scorer** | Re-score every order's risk | 60 min |
| **Knowledge Indexer** | Embed new mail into AI memory | 30 min |

(The last two are the new AI jobs.)

---

## 11. Where it all runs (deployment)

| Piece | Runs on |
|-------|---------|
| Frontend | **Vercel** (auto-deploys when we push code) |
| Backend | **EC2** server `54.88.107.89:8000` (systemd keeps it always on) |
| Database | **Supabase** Postgres (via the connection pooler) |
| AI model | **NVIDIA** hosted `llama-3.3-70b` + `nv-embedqa-e5-v5` embeddings |
| Auto-deploy | **GitHub Actions** — push to `main` → backend redeploys itself |

**On/off switches** live in the backend's `.env` file. Today these are ON:
`LLM_ENABLED`, `AI_TRIAGE_ENABLED`, `AI_PO_FOLLOWUP_ENABLED`, `RAG_ENABLED`,
and the agentic assistant. The mail inbox/SMTP have their own toggles.

---

## 12. Mini-glossary

- **PO (Purchase Order):** an order placed on a supplier.
- **Signal:** the GREEN/YELLOW/RED/BLACK traffic light on an order.
- **Commitment:** the date a supplier *promised* to deliver.
- **Follow-up:** a chasing email we send the supplier.
- **Triage:** the AI sorting a mail by category/urgency/action.
- **Embedding:** a numeric "fingerprint" of a text's meaning, used for memory.
- **RAG / vector memory / pgvector:** the AI's searchable memory of past mails.
- **Agentic:** the AI can *use tools* (look things up) before answering.
- **Scheduler / cron job:** a task the backend runs automatically on a timer.
- **SMTP / IMAP / POP3:** the standard ways to send / read email.

---

### One-paragraph summary

The backend quietly reads the mailbox every few minutes, figures out whether
each mail is a supplier reply (file it, update the order) or a customer message
(send it to the inbox, AI-tag it), automatically chases late suppliers with
template or AI-written mails, and stores everything in Supabase. On top of that
sits an AI brain that tags incoming mail, scores delivery risk, grades
suppliers, remembers past conversations, and answers your team's questions by
looking up the real data live — all visible and controllable from the web app.

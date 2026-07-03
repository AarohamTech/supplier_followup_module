"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";
import { X, Sparkles, FileText, Loader2, Inbox } from "lucide-react";
import { api } from "@/lib/api";
import type {
  CommunicationTask,
  CommunicationTaskCreate,
  CustomerMail,
  CustomerMailListResponse,
  CustomerReply,
} from "@/lib/types";
import { MailQueue } from "./MailQueue";
import { ConversationPanel, type LocalReply } from "./ConversationPanel";
import {
  ProcurementContextPanel,
  type ProcurementContext,
} from "./ProcurementContextPanel";
import { TaskPanel } from "./TaskPanel";
import CustomerTaskModal from "./CustomerTaskModal";
import { useDebouncedValue, useRenderCount } from "./hooks";
import { QUEUE_TABS, formatDate } from "./shared";
import PageHeader from "@/components/layout/PageHeader";

type AgentAction = {
  type: "draft" | "subscription";
  message_id?: number;
  subscription_id?: number;
  recipient?: string;
  subject?: string;
  kind?: string;
  schedule?: string | null;
};

function fmtQty(value: number | null | undefined, uom?: string | null): string | null {
  if (value === null || value === undefined) return null;
  const n = Number(value);
  if (Number.isNaN(n)) return null;
  return `${n.toLocaleString()}${uom ? ` ${uom}` : ""}`;
}

function buildSuggestion(mail: CustomerMail | null, ctx: ProcurementContext | null): string {
  const name = mail?.from_name || mail?.customer_name || "there";
  const po = ctx?.supplierPo || mail?.linked_supplier_po_no;
  if (ctx && po && ctx.commitmentDate) {
    return (
      `Hi ${name},\n\nThank you for reaching out regarding ${po}. ` +
      `The current committed dispatch date for ${ctx.material || "your order"} is ` +
      `${formatDate(ctx.commitmentDate)} (status: ${ctx.status || "in progress"}). ` +
      `We will share tracking details as soon as it ships.\n\nBest regards,\nProcureDirect Team`
    );
  }
  return (
    `Hi ${name},\n\nThank you for your message. We are checking the latest status ` +
    `with our supplier and will get back to you with a firm update shortly.\n\n` +
    `Best regards,\nProcureDirect Team`
  );
}

export default function CustomerWorkspace() {
  useRenderCount("CustomerWorkspace");

  // ── Filters ────────────────────────────────────────────────────────────
  const [searchInput, setSearchInput] = useState("");
  const search = useDebouncedValue(searchInput, 350);
  const [activeTab, setActiveTab] = useState(QUEUE_TABS[0].key);
  // Customer vs non-customer scope. Customers are senders on a customer domain
  // (@zanvargroup.com); every other sender domain is "non-customer".
  const [mailScope, setMailScope] = useState<"customer" | "other">("customer");

  // ── Data ───────────────────────────────────────────────────────────────
  const [data, setData] = useState<CustomerMailListResponse | null>(null);
  const [loadingList, setLoadingList] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  const [selectedId, setSelectedId] = useState<number | null>(null);

  const [context, setContext] = useState<ProcurementContext | null>(null);
  const [loadingContext, setLoadingContext] = useState(false);

  const [tasks, setTasks] = useState<CommunicationTask[]>([]);
  const [loadingTasks, setLoadingTasks] = useState(false);
  const [taskReloadKey, setTaskReloadKey] = useState(0);

  // ── UI state ─────────────────────────────────────────────────────────────
  const [replies, setReplies] = useState<CustomerReply[]>([]);
  const [replyReloadKey, setReplyReloadKey] = useState(0);
  const [serverDraft, setServerDraft] = useState<{ subject: string; body: string } | null>(null);
  const [aiDraftLoading, setAiDraftLoading] = useState(false);
  const [seed, setSeed] = useState<{ text: string; nonce: number } | undefined>();
  const [sending, setSending] = useState(false);
  const [creating, setCreating] = useState(false);
  const [taskModalOpen, setTaskModalOpen] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  // ── /hi agent (Harmony Intelligence) on the selected customer thread ──────
  const [agentReply, setAgentReply] = useState<string | null>(null);
  const [agentActions, setAgentActions] = useState<AgentAction[]>([]);
  const [agentBusy, setAgentBusy] = useState(false);

  // ── Fetch list (debounced search + customer/non-customer scope) ───────────
  useEffect(() => {
    let cancelled = false;
    setLoadingList(true);
    api
      .listCustomerMails({ search: search || undefined, scope: mailScope, limit: 200 })
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch((err) => {
        if (!cancelled) setToast((err as Error).message);
      })
      .finally(() => {
        if (!cancelled) setLoadingList(false);
      });
    return () => {
      cancelled = true;
    };
  }, [search, mailScope, reloadKey]);

  // Scope filtering happens on the backend (customer domains vs the inverse).
  const items = useMemo(() => data?.items ?? [], [data]);

  // Auto-select the first mail; also re-point if the current selection has
  // dropped out of the list (e.g. after a filter/search or a status change).
  useEffect(() => {
    setSelectedId((prev) =>
      prev != null && items.some((m) => m.id === prev) ? prev : items[0]?.id ?? null,
    );
  }, [items]);

  const selected = useMemo(
    () => items.find((m) => m.id === selectedId) ?? null,
    [items, selectedId],
  );

  // ── Grouping + counts (single memoized pass) ─────────────────────────────
  const counts = useMemo(() => {
    const out: Record<string, number> = {};
    for (const tab of QUEUE_TABS) out[tab.key] = 0;
    for (const m of items) {
      for (const tab of QUEUE_TABS) if (tab.match(m)) out[tab.key] += 1;
    }
    return out;
  }, [items]);

  const filteredMails = useMemo(() => {
    const tab = QUEUE_TABS.find((t) => t.key === activeTab) ?? QUEUE_TABS[0];
    return items.filter(tab.match);
  }, [items, activeTab]);

  // ── Fetch procurement context (keyed on linked PO; ignores stale) ────────
  const linkedPo = selected?.linked_supplier_po_no ?? null;
  useEffect(() => {
    if (!linkedPo) {
      setContext(null);
      return;
    }
    let cancelled = false;
    setLoadingContext(true);
    // PO numbers (CRM PoNo) are recycled across suppliers, so a bare PO-number
    // lookup mixes suppliers. Fetch procurement first, derive the supplier that
    // owns this linked PO, then scope both the context records and commitments
    // to that supplier.
    api
      .listProcurement({ supplier_po_no: linkedPo, size: 50 })
      .then(async (proc) => {
        if (cancelled) return;
        const allRecords = proc.items ?? [];
        const supplierName = allRecords[0]?.supplier_name ?? undefined;
        const records = supplierName
          ? allRecords.filter((r) => r.supplier_name === supplierName)
          : allRecords;
        const commitments = await api.listCommitments({
          supplier_po_no: linkedPo,
          supplier_name: supplierName,
        });
        if (cancelled) return;
        const first = records[0];
        const commit = commitments[0];
        const ctx: ProcurementContext = {
          material: first?.material_name ?? null,
          customerPo: first?.crm_no ?? first?.po_no ?? null,
          supplierPo: linkedPo,
          balanceQty: fmtQty(first?.qty, first?.uom),
          stockAvailable: fmtQty(first?.stock, first?.uom),
          receivedQty: null,
          status: first?.po_status ?? first?.signal ?? null,
          commitmentDate: commit?.commitment_date ?? first?.commitment_date ?? null,
          risk: (first?.signal as string) ?? null,
          latestUpdate: commit?.supplier_remark ?? first?.last_supplier_reply ?? null,
          materials: records.slice(0, 5).map((r) => ({
            name: r.material_name,
            stock: fmtQty(r.stock) ?? "—",
            status: r.po_status ?? (r.signal as string) ?? "—",
          })),
        };
        setContext(ctx);
      })
      .catch(() => {
        if (!cancelled) setContext(null);
      })
      .finally(() => {
        if (!cancelled) setLoadingContext(false);
      });
    return () => {
      cancelled = true;
    };
  }, [linkedPo]);

  // ── Fetch the persisted replies (conversation) for the selected mail ─────
  useEffect(() => {
    if (selectedId == null) {
      setReplies([]);
      return;
    }
    let cancelled = false;
    api
      .getCustomerMailReplies(selectedId)
      .then((res) => {
        if (!cancelled) setReplies(res);
      })
      .catch(() => {
        if (!cancelled) setReplies([]);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedId, replyReloadKey]);

  // ── Fetch the server-side smart draft (Phase 2, from live order data) ────
  useEffect(() => {
    if (selectedId == null) {
      setServerDraft(null);
      return;
    }
    let cancelled = false;
    api
      .draftCustomerReply(selectedId)
      .then((d) => {
        if (!cancelled) setServerDraft({ subject: d.subject, body: d.body });
      })
      .catch(() => {
        if (!cancelled) setServerDraft(null);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedId]);

  // ── Fetch tasks for selected mail (lazy, ignores stale) ──────────────────
  useEffect(() => {
    if (selectedId == null) {
      setTasks([]);
      return;
    }
    let cancelled = false;
    setLoadingTasks(true);
    api
      .listUnifiedTasks({ customer_mail_id: selectedId, limit: 50 })
      .then((res) => {
        if (!cancelled) setTasks(res);
      })
      .catch(() => {
        if (!cancelled) setTasks([]);
      })
      .finally(() => {
        if (!cancelled) setLoadingTasks(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedId, taskReloadKey]);

  const clientSuggestion = useMemo(
    () => buildSuggestion(selected, context),
    [selected, context],
  );
  // Prefer the server's data-driven draft (Phase 2); fall back to the client one.
  const aiSuggestion = serverDraft?.body || clientSuggestion;

  // ── Stable handlers ──────────────────────────────────────────────────────
  const handleSelect = useCallback((id: number) => {
    setSelectedId(id);
    setDrawerOpen(false);
  }, []);

  const handleTabChange = useCallback((key: string) => setActiveTab(key), []);
  const handleSearchChange = useCallback((v: string) => setSearchInput(v), []);

  // Ask the HI agent (customer-thread context), surfacing any confirm-gated actions.
  const runAgent = useCallback(
    async (message: string) => {
      if (selectedId == null) return;
      setAgentBusy(true);
      setAgentReply(null);
      setAgentActions([]);
      try {
        const res = await api.hubAgent({ message, customer_mail_id: selectedId });
        setAgentReply(res.reply || "(no response)");
        setAgentActions(res.pending_actions ?? []);
      } catch (err) {
        setAgentReply((err as Error).message);
      } finally {
        setAgentBusy(false);
      }
    },
    [selectedId],
  );

  const confirmAgentAction = useCallback(async (action: AgentAction) => {
    try {
      if (action.type === "draft" && action.message_id != null) {
        await api.hubAgentConfirm({ action_type: "draft", id: action.message_id });
        setReplyReloadKey((k) => k + 1);
        setToast("Reply sent.");
      } else if (action.type === "subscription" && action.subscription_id != null) {
        await api.hubAgentConfirm({ action_type: "subscription", id: action.subscription_id });
        setToast("Subscription activated.");
      }
      setAgentActions((prev) => prev.filter((a) => a !== action));
    } catch (err) {
      setToast((err as Error).message);
    }
  }, []);

  const handleSend = useCallback(
    (text: string) => {
      if (selectedId == null) return;
      // "/hi ..." routes to the Harmony Intelligence agent instead of a reply.
      if (/^\/hi\b/i.test(text)) {
        void runAgent(text.replace(/^\/hi\b/i, "").trim() || "help");
        return;
      }
      const id = selectedId;
      setSending(true);
      api
        .replyToCustomerMail(id, text)
        .then((res) => {
          setReplyReloadKey((k) => k + 1); // reload the real persisted reply
          setData((prev) =>
            prev
              ? {
                  ...prev,
                  items: prev.items.map((m) =>
                    m.id === id ? { ...m, status: res.mail_status } : m,
                  ),
                }
              : prev,
          );
          setToast(res.queued ? "Reply queued for send." : "Reply sent.");
        })
        .catch((err) => setToast((err as Error).message))
        .finally(() => setSending(false));
    },
    [selectedId, runAgent],
  );

  const handleCreateTask = useCallback(() => {
    if (selectedId == null || !selected) return;
    setTaskModalOpen(true);
  }, [selectedId, selected]);

  const handleSaveTask = useCallback(
    (payload: CommunicationTaskCreate) => {
      setCreating(true);
      api
        .createTask(payload)
        .then(() => {
          setTaskModalOpen(false);
          setTaskReloadKey((k) => k + 1);
          setReloadKey((k) => k + 1); // refresh list so tab counts/buckets update
          setToast("Task created.");
        })
        .catch((err) => setToast((err as Error).message))
        .finally(() => setCreating(false));
    },
    [],
  );

  const handleQuickAction = useCallback(
    (kind: "stock" | "supplier" | "planning") => {
      if (selectedId == null) return;
      const titles: Record<typeof kind, string> = {
        stock: "Request stock check",
        supplier: "Request supplier update",
        planning: "Request planning confirmation",
      };
      setCreating(true);
      api
        .createTaskForCustomerMail(selectedId, { title: titles[kind], priority: "MEDIUM" })
        .then(() => {
          setTaskReloadKey((k) => k + 1);
          setReloadKey((k) => k + 1); // refresh list so tab counts/buckets update
          setToast(`${titles[kind]} created.`);
        })
        .catch((err) => setToast((err as Error).message))
        .finally(() => setCreating(false));
    },
    [selectedId],
  );

  const handleUseSuggestion = useCallback(() => {
    setSeed((prev) => ({ text: aiSuggestion, nonce: (prev?.nonce ?? 0) + 1 }));
    setDrawerOpen(false);
  }, [aiSuggestion]);

  // On-demand LLM draft (kept off the select path to avoid burning rate limits).
  const handleAiDraft = useCallback(() => {
    if (selectedId == null) return;
    setAiDraftLoading(true);
    api
      .draftCustomerReply(selectedId, true)
      .then((d) => {
        setServerDraft({ subject: d.subject, body: d.body });
        setSeed((prev) => ({ text: d.body, nonce: (prev?.nonce ?? 0) + 1 }));
        setToast(d.source === "ai" ? "HI draft ready." : "Harmony Intelligent was busy — used a data template.");
      })
      .catch((err) => setToast((err as Error).message))
      .finally(() => setAiDraftLoading(false));
  }, [selectedId]);

  // ── AI triage / summarize for the selected mail ──────────────────────────
  const [aiBusy, setAiBusy] = useState<null | "triage" | "summary">(null);

  const patchSelectedMail = useCallback(
    (patch: Partial<CustomerMail>) => {
      setData((prev) =>
        prev
          ? {
              ...prev,
              items: prev.items.map((m) => (m.id === selectedId ? { ...m, ...patch } : m)),
            }
          : prev,
      );
    },
    [selectedId],
  );

  const handleTriage = useCallback(() => {
    if (selectedId == null) return;
    setAiBusy("triage");
    api
      .triageCustomerMail(selectedId)
      .then((r) => {
        patchSelectedMail({
          ai_category: r.category,
          ai_urgency: r.urgency,
          ai_action: r.action,
          ai_summary: r.summary,
          ai_triaged_at: new Date().toISOString(),
        });
        setToast(`Triaged: ${r.urgency} · ${r.category} · ${r.action}`);
      })
      .catch((err) => setToast((err as Error).message))
      .finally(() => setAiBusy(null));
  }, [selectedId, patchSelectedMail]);

  const handleSummarize = useCallback(() => {
    if (selectedId == null) return;
    setAiBusy("summary");
    api
      .summarizeCustomerMail(selectedId)
      .then((r) => {
        patchSelectedMail({ ai_summary: r.summary });
        setToast("Summary ready.");
      })
      .catch((err) => setToast((err as Error).message))
      .finally(() => setAiBusy(null));
  }, [selectedId, patchSelectedMail]);

  const openContext = useCallback(() => setDrawerOpen(true), []);
  const closeContext = useCallback(() => setDrawerOpen(false), []);

  // Auto-dismiss toast.
  useEffect(() => {
    if (!toast) return;
    const id = setTimeout(() => setToast(null), 2500);
    return () => clearTimeout(id);
  }, [toast]);

  const selectedReplies: LocalReply[] = useMemo(
    () =>
      replies.map((r) => ({
        id: r.id,
        text: r.body ?? "",
        at: r.sent_at ?? r.created_at,
        status: r.status,
      })),
    [replies],
  );

  const rightPanel = (
    <div className="flex h-full min-h-0 flex-col overflow-y-auto">
      <ProcurementContextPanel
        context={context}
        loading={loadingContext}
        aiSuggestion={aiSuggestion}
        onUseSuggestion={handleUseSuggestion}
        onAiDraft={handleAiDraft}
        aiLoading={aiDraftLoading}
      />
      <TaskPanel
        tasks={tasks}
        loading={loadingTasks}
        creating={creating}
        onCreateTask={handleCreateTask}
        onQuickAction={handleQuickAction}
      />
    </div>
  );

  return (
    <div className="flex min-h-[calc(100dvh-7rem)] flex-col md:h-[calc(100dvh-7rem)] md:min-h-0">
      <PageHeader
        className="mb-3"
        title="Customer Response Workspace"
        description="Manage customer communication, internal coordination and response preparation."
        icon={Inbox}
        tone="red"
        actions={
          <>
          {/* Scope toggle: customer conversations vs all non-customer mail. */}
          <div className="inline-flex rounded-lg border border-brand-border bg-subtle p-0.5 text-xs font-semibold">
            <button
              type="button"
              onClick={() => setMailScope("customer")}
              className={`rounded-md px-3 py-1.5 transition ${
                mailScope === "customer" ? "bg-card text-signal-red shadow-sm" : "text-brand-muted hover:text-brand-dark"
              }`}
            >
              Customers
            </button>
            <button
              type="button"
              onClick={() => setMailScope("other")}
              title="All non-customer mail (supplier / other)"
              className={`rounded-md px-3 py-1.5 transition ${
                mailScope === "other" ? "bg-card text-signal-red shadow-sm" : "text-brand-muted hover:text-brand-dark"
              }`}
            >
              Non-customer
            </button>
          </div>
          {toast && (
            <span className="rounded-md bg-ink px-3 py-1.5 text-xs text-white">{toast}</span>
          )}
          {selected && (
            <>
              <button
                type="button"
                onClick={handleTriage}
                disabled={aiBusy !== null}
                className="btn-outline text-xs"
                title="Classify category / urgency / suggested action with Harmony Intelligent"
              >
                {aiBusy === "triage" ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Sparkles className="h-3.5 w-3.5" />
                )}
                Triage
              </button>
              <button
                type="button"
                onClick={handleSummarize}
                disabled={aiBusy !== null}
                className="btn-outline text-xs"
                title="Summarize this mail + its replies"
              >
                {aiBusy === "summary" ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <FileText className="h-3.5 w-3.5" />
                )}
                Summarize
              </button>
            </>
          )}
          </>
        }
      />

      {/* AI triage / summary banner for the selected mail */}
      {selected && (selected.ai_summary || selected.ai_urgency) && (
        <div className="mb-3 flex flex-wrap items-center gap-2 rounded-lg border border-brand-border bg-brand-surface px-3 py-2 text-xs">
          {selected.ai_urgency && (
            <span
              className={`rounded px-1.5 py-0.5 font-semibold ${
                selected.ai_urgency === "HIGH"
                  ? "bg-red-100 text-signal-red"
                  : selected.ai_urgency === "MEDIUM"
                    ? "bg-amber-100 text-amber-700"
                    : "bg-emerald-100 text-emerald-700"
              }`}
            >
              {selected.ai_urgency}
            </span>
          )}
          {selected.ai_category && (
            <span className="rounded bg-subtle px-1.5 py-0.5 text-brand-dark">{selected.ai_category}</span>
          )}
          {selected.ai_action && (
            <span className="rounded bg-red-50 px-1.5 py-0.5 text-signal-red">→ {selected.ai_action}</span>
          )}
          {selected.ai_summary && (
            <span className="min-w-0 flex-1 text-brand-muted">{selected.ai_summary}</span>
          )}
        </div>
      )}

      {/* Workspace grid */}
      <div className="flex min-h-0 flex-1 flex-col gap-3 md:flex-row">
        {/* Left queue */}
        <aside className="h-[22rem] max-h-[45vh] w-full shrink-0 overflow-hidden rounded-xl border border-brand-border bg-card shadow-sm md:h-auto md:max-h-none md:w-72 xl:w-80">
          <MailQueue
            tabs={QUEUE_TABS}
            activeTab={activeTab}
            counts={counts}
            onTabChange={handleTabChange}
            searchInput={searchInput}
            onSearchChange={handleSearchChange}
            mails={filteredMails}
            selectedId={selectedId}
            onSelect={handleSelect}
            loading={loadingList}
          />
        </aside>

        {/* Center conversation */}
        <section className="flex min-h-[32rem] min-w-0 flex-1 overflow-hidden rounded-xl border border-brand-border bg-card shadow-sm md:min-h-0">
          {selected ? (
            <div className="flex h-full min-h-0 w-full flex-col">
              {(agentBusy || agentReply) ? (
                <div className="m-3 mb-0 rounded-lg border border-signal-red/30 bg-red-50/60 p-3 text-xs">
                  <div className="mb-1 flex items-center justify-between">
                    <span className="inline-flex items-center gap-1 font-semibold text-signal-red">
                      <Sparkles className="h-3.5 w-3.5" /> Harmony Intelligence
                    </span>
                    <button
                      type="button"
                      onClick={() => { setAgentReply(null); setAgentActions([]); }}
                      className="rounded p-0.5 text-brand-muted hover:bg-card"
                      aria-label="Dismiss HI"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  </div>
                  {agentBusy ? (
                    <span className="inline-flex items-center gap-1 text-brand-muted">
                      <Loader2 className="h-3.5 w-3.5 animate-spin" /> Thinking…
                    </span>
                  ) : (
                    <p className="whitespace-pre-wrap leading-relaxed text-brand-dark">{agentReply}</p>
                  )}
                  {agentActions.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-2">
                      {agentActions.map((a, i) => (
                        <button
                          key={i}
                          type="button"
                          onClick={() => void confirmAgentAction(a)}
                          className="inline-flex items-center gap-1 rounded-md bg-signal-red px-2.5 py-1 text-[11px] font-semibold text-white hover:opacity-90"
                        >
                          {a.type === "draft"
                            ? `Send draft${a.recipient ? ` → ${a.recipient}` : ""}`
                            : `Activate ${a.kind || "subscription"}${a.recipient ? ` → ${a.recipient}` : ""}`}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              ) : (
                <div className="m-3 mb-0 shrink-0 rounded-md bg-subtle px-3 py-1.5 text-[11px] text-brand-muted">
                  Tip: type <span className="font-semibold text-signal-red">/hi</span> in the reply box to ask Harmony Intelligence — e.g. <em>/hi summarize</em>, <em>/hi draft a reply</em>, <em>/hi email @teammate</em>.
                </div>
              )}
              <ConversationPanel
                mail={selected}
                localReplies={selectedReplies}
                sending={sending}
                seed={seed}
                onSend={handleSend}
                onOpenContext={openContext}
              />
            </div>
          ) : (
            <div className="flex h-full w-full items-center justify-center text-sm text-brand-muted">
              {loadingList ? "Loading…" : "Select a mail to view the conversation."}
            </div>
          )}
        </section>

        {/* Right context stays a drawer until there is room for all three columns. */}
        <aside className="hidden w-80 shrink-0 overflow-hidden rounded-xl border border-brand-border bg-card shadow-sm 2xl:block">
          {rightPanel}
        </aside>
      </div>

      {/* Mobile / tablet drawer for context */}
      {drawerOpen && (
        <div className="fixed inset-0 z-40 2xl:hidden">
          <div
            className="absolute inset-0 bg-black/30"
            onClick={closeContext}
            aria-hidden
          />
          <div
            className="absolute right-0 top-0 flex h-full w-[90%] max-w-sm flex-col bg-card shadow-xl"
            role="dialog"
            aria-modal="true"
            aria-label="Procurement context"
          >
            <div className="flex items-center justify-between border-b border-brand-border px-4 py-3">
              <span className="text-sm font-semibold">Procurement Context</span>
              <button
                type="button"
                onClick={closeContext}
                aria-label="Close procurement context"
                className="rounded-md p-1 text-brand-muted hover:bg-subtle"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="min-h-0 flex-1">{rightPanel}</div>
          </div>
        </div>
      )}

      {/* Rich customer task creator (lazy: only mounted while open) */}
      {taskModalOpen && selected && (
        <CustomerTaskModal
          mail={selected}
          context={context}
          saving={creating}
          onCancel={() => setTaskModalOpen(false)}
          onSave={handleSaveTask}
        />
      )}
    </div>
  );
}

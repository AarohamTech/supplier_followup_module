"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { X } from "lucide-react";
import { api } from "@/lib/api";
import type {
  CommunicationTask,
  CommunicationTaskCreate,
  CustomerMail,
  CustomerMailListResponse,
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
  const [localReplies, setLocalReplies] = useState<Record<number, LocalReply[]>>({});
  const [seed, setSeed] = useState<{ text: string; nonce: number } | undefined>();
  const [sending, setSending] = useState(false);
  const [creating, setCreating] = useState(false);
  const [taskModalOpen, setTaskModalOpen] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const replyIdRef = useRef(0); // monotonic local-reply id (avoids Date.now() key collisions)

  // ── Fetch list (debounced search only; tabs group client-side) ───────────
  useEffect(() => {
    let cancelled = false;
    setLoadingList(true);
    api
      .listCustomerMails({ search: search || undefined, limit: 200 })
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
  }, [search, reloadKey]);

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
    Promise.all([
      api.listProcurement({ supplier_po_no: linkedPo, size: 50 }),
      api.listCommitments({ supplier_po_no: linkedPo }),
    ])
      .then(([proc, commitments]) => {
        if (cancelled) return;
        const records = proc.items ?? [];
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

  const aiSuggestion = useMemo(
    () => buildSuggestion(selected, context),
    [selected, context],
  );

  // ── Stable handlers ──────────────────────────────────────────────────────
  const handleSelect = useCallback((id: number) => {
    setSelectedId(id);
    setDrawerOpen(false);
  }, []);

  const handleTabChange = useCallback((key: string) => setActiveTab(key), []);
  const handleSearchChange = useCallback((v: string) => setSearchInput(v), []);

  const handleSend = useCallback(
    (text: string) => {
      if (selectedId == null) return;
      setSending(true);
      const reply: LocalReply = { id: (replyIdRef.current += 1), text, at: new Date().toISOString() };
      setLocalReplies((prev) => ({
        ...prev,
        [selectedId]: [...(prev[selectedId] ?? []), reply],
      }));
      api
        .assignCustomerMail(selectedId, { status: "IN_PROGRESS" })
        .then(() => {
          setData((prev) =>
            prev
              ? {
                  ...prev,
                  items: prev.items.map((m) =>
                    m.id === selectedId ? { ...m, status: "IN_PROGRESS" } : m,
                  ),
                }
              : prev,
          );
          setToast("Reply recorded.");
        })
        .catch((err) => setToast((err as Error).message))
        .finally(() => setSending(false));
    },
    [selectedId],
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
        .createTaskForCustomerMail(selectedId, { title: titles[kind], priority: "P2" })
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

  const openContext = useCallback(() => setDrawerOpen(true), []);
  const closeContext = useCallback(() => setDrawerOpen(false), []);

  // Auto-dismiss toast.
  useEffect(() => {
    if (!toast) return;
    const id = setTimeout(() => setToast(null), 2500);
    return () => clearTimeout(id);
  }, [toast]);

  const selectedReplies = selectedId != null ? localReplies[selectedId] ?? [] : [];

  const rightPanel = (
    <div className="flex h-full flex-col overflow-y-auto">
      <ProcurementContextPanel
        context={context}
        loading={loadingContext}
        aiSuggestion={aiSuggestion}
        onUseSuggestion={handleUseSuggestion}
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
    <div className="flex h-[calc(100vh-128px)] flex-col">
      {/* Header */}
      <div className="mb-3 flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-brand-dark">Customer Response Workspace</h1>
          <p className="text-xs text-brand-muted">
            Manage customer communication, internal coordination and response preparation.
          </p>
        </div>
        {toast && (
          <span className="rounded-md bg-brand-dark px-3 py-1.5 text-xs text-white">{toast}</span>
        )}
      </div>

      {/* Workspace grid */}
      <div className="flex min-h-0 flex-1 flex-col gap-3 md:flex-row">
        {/* Left queue */}
        <aside className="max-h-64 w-full shrink-0 overflow-hidden rounded-xl border border-brand-border bg-white md:max-h-none md:w-72">
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
        <section className="flex min-w-0 flex-1 overflow-hidden rounded-xl border border-brand-border bg-white">
          {selected ? (
            <div className="flex h-full w-full flex-col">
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

        {/* Right context (fixed on xl, drawer below) */}
        <aside className="hidden w-80 shrink-0 overflow-hidden rounded-xl border border-brand-border bg-white xl:block">
          {rightPanel}
        </aside>
      </div>

      {/* Mobile / tablet drawer for context */}
      {drawerOpen && (
        <div className="fixed inset-0 z-40 xl:hidden">
          <div
            className="absolute inset-0 bg-black/30"
            onClick={closeContext}
            aria-hidden
          />
          <div className="absolute right-0 top-0 flex h-full w-[90%] max-w-sm flex-col bg-white shadow-xl">
            <div className="flex items-center justify-between border-b border-brand-border px-4 py-3">
              <span className="text-sm font-semibold">Procurement Context</span>
              <button
                type="button"
                onClick={closeContext}
                className="rounded-md p-1 text-brand-muted hover:bg-gray-100"
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

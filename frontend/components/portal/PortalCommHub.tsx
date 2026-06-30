"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Inbox,
  Loader2,
  MessagesSquare,
  Package,
  RefreshCcw,
  Search,
  Send,
} from "lucide-react";

import { api } from "@/lib/api";
import type { PortalMessage, PortalTask } from "@/lib/types";

// ─── Normalized PO row shape (works for both EmployeePo and PortalPo) ────────
export interface CommHubPoRow {
  supplier_po_no: string;
  /** Counterparty label — supplier name (employee) or buyer/"Your buyer" (supplier). */
  counterparty: string;
  crm_no?: string | null;
  signal?: string | null;
  material_count?: number | null;
  unread_inbound?: number;
  escalated?: boolean;
}

export interface CommHubAdapter {
  listPos: () => Promise<CommHubPoRow[]>;
  listMessages: (supplierPoNo: string) => Promise<PortalMessage[]>;
  sendMessage: (supplierPoNo: string, body: string) => Promise<PortalMessage>;
  markRead: (supplierPoNo: string) => Promise<{ marked: number }>;
  /** Optional context-panel data. */
  listMaterials?: (supplierPoNo: string) => Promise<{ material_name: string; signal?: string | null; commitment_date?: string | null }[]>;
  listTasks?: (supplierPoNo: string) => Promise<PortalTask[]>;
}

const SIGNAL_DOT: Record<string, string> = {
  GREEN: "bg-emerald-500",
  YELLOW: "bg-amber-500",
  RED: "bg-signal-red",
  BLACK: "bg-ink",
};

const SIGNAL_CHIP: Record<string, string> = {
  GREEN: "bg-emerald-50 text-emerald-700",
  YELLOW: "bg-amber-50 text-amber-700",
  RED: "bg-red-50 text-signal-red",
  BLACK: "bg-ink text-white",
};

function fmtTime(value?: string | null) {
  if (!value) return "";
  const d = new Date(value);
  if (isNaN(d.getTime())) return "";
  return d.toLocaleString("en-IN", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}

function EmptyState({ children, icon }: { children: React.ReactNode; icon?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-2 px-4 py-10 text-center text-sm text-brand-muted">
      {icon}
      <div>{children}</div>
    </div>
  );
}

export default function PortalCommHub({
  adapter,
  mode,
}: {
  adapter: CommHubAdapter;
  mode: "employee" | "supplier";
}) {
  const [pos, setPos] = useState<CommHubPoRow[]>([]);
  const [active, setActive] = useState<string | null>(null);
  const [messages, setMessages] = useState<PortalMessage[]>([]);
  const [materials, setMaterials] = useState<{ material_name: string; signal?: string | null; commitment_date?: string | null }[]>([]);
  const [poTasks, setPoTasks] = useState<PortalTask[]>([]);
  const [loadingPos, setLoadingPos] = useState(true);
  const [loadingMsgs, setLoadingMsgs] = useState(false);
  const [search, setSearch] = useState("");
  const [composer, setComposer] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement | null>(null);

  const counterpartyLabel = mode === "employee" ? "Supplier" : "Buyer";

  const refreshPos = useCallback(async () => {
    const list = await adapter.listPos();
    setPos(list);
    return list;
  }, [adapter]);

  // Initial load.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const list = await refreshPos();
        if (cancelled) return;
        // Deep-link: ?po=… pre-selects that thread, else first unread/first.
        const wanted =
          typeof window !== "undefined" ? new URLSearchParams(window.location.search).get("po") : null;
        const target =
          (wanted && list.find((p) => p.supplier_po_no === wanted)) ||
          list.find((p) => (p.unread_inbound ?? 0) > 0) ||
          list[0];
        if (target) setActive(target.supplier_po_no);
      } catch (e) {
        if (!cancelled) setError((e as Error).message);
      } finally {
        if (!cancelled) setLoadingPos(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [refreshPos]);

  // Load a thread + context whenever the active PO changes, then mark read.
  useEffect(() => {
    if (!active) {
      setMessages([]);
      setMaterials([]);
      setPoTasks([]);
      return;
    }
    let cancelled = false;
    setLoadingMsgs(true);
    (async () => {
      try {
        const [msgs] = await Promise.all([
          adapter.listMessages(active),
          adapter.listMaterials?.(active).then((m) => !cancelled && setMaterials(m)).catch(() => setMaterials([])),
          adapter.listTasks?.(active).then((t) => !cancelled && setPoTasks(t)).catch(() => setPoTasks([])),
        ]);
        if (cancelled) return;
        setMessages(msgs);
        setError(null);
        // Clear the unread cue and refresh the PO list so the badge disappears.
        try {
          await adapter.markRead(active);
          if (!cancelled) await refreshPos();
        } catch {
          /* non-fatal */
        }
      } catch (e) {
        if (!cancelled) setError((e as Error).message);
      } finally {
        if (!cancelled) setLoadingMsgs(false);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, adapter]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [messages.length, active]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return [...pos]
      .filter((p) => !q || `${p.supplier_po_no} ${p.counterparty} ${p.crm_no ?? ""}`.toLowerCase().includes(q))
      .sort((a, b) => {
        // Unread float to the top.
        const au = (a.unread_inbound ?? 0) > 0 ? 1 : 0;
        const bu = (b.unread_inbound ?? 0) > 0 ? 1 : 0;
        if (au !== bu) return bu - au;
        return a.supplier_po_no.localeCompare(b.supplier_po_no);
      });
  }, [pos, search]);

  const activePo = pos.find((p) => p.supplier_po_no === active) ?? null;

  const send = async () => {
    const body = composer.trim();
    if (!body || !active || sending) return;
    setSending(true);
    try {
      const m = await adapter.sendMessage(active, body);
      setMessages((cur) => [...cur, m]);
      setComposer("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="-m-5 flex h-[calc(100vh-65px)] flex-col bg-brand-surface sm:-m-6 lg:-m-8">
      {/* Header */}
      <header className="flex flex-wrap items-center gap-3 border-b border-brand-border bg-card px-6 py-3">
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-red-50 text-signal-red">
          <MessagesSquare size={17} />
        </span>
        <div className="min-w-0">
          <h1 className="truncate text-base font-semibold text-brand-dark">Communication Hub</h1>
          <p className="hidden text-xs text-brand-muted sm:block">
            {mode === "employee"
              ? "Message suppliers on the purchase orders assigned to you."
              : "Message your buyer about any PO. Replies appear here live."}
          </p>
        </div>
        <div className="relative ml-auto w-full min-w-[200px] max-w-sm flex-1">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-brand-muted" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search PO or counterparty…"
            className="input h-9 pl-9"
          />
        </div>
        <button onClick={() => void refreshPos()} className="btn-outline h-9" disabled={loadingPos}>
          {loadingPos ? <Loader2 size={14} className="animate-spin" /> : <RefreshCcw size={14} />}
          <span className="hidden sm:inline">Refresh</span>
        </button>
      </header>

      {error && (
        <div className="mx-6 mt-3 rounded-md border border-red-100 bg-red-50 px-3 py-2 text-sm text-signal-red">
          {error}
        </div>
      )}

      {/* Workspace */}
      <div className="flex flex-1 gap-4 overflow-hidden p-4">
        {/* LEFT — PO list */}
        <aside className="flex w-[340px] min-w-[280px] shrink-0 flex-col overflow-hidden rounded-xl border border-brand-border bg-card shadow-sm">
          <div className="flex items-center justify-between px-4 py-2.5">
            <span className="text-xs font-semibold uppercase tracking-wide text-brand-muted">Purchase Orders</span>
            <span className="text-[11px] text-brand-muted">{filtered.length}</span>
          </div>
          <div className="flex-1 overflow-y-auto border-t border-brand-border">
            {loadingPos && pos.length === 0 ? (
              <EmptyState icon={<Loader2 className="animate-spin" size={18} />}>Loading…</EmptyState>
            ) : filtered.length === 0 ? (
              <EmptyState icon={<Inbox size={20} />}>No purchase orders found.</EmptyState>
            ) : (
              filtered.map((p) => (
                <PoRow
                  key={p.supplier_po_no}
                  p={p}
                  counterpartyLabel={counterpartyLabel}
                  active={p.supplier_po_no === active}
                  onClick={() => setActive(p.supplier_po_no)}
                />
              ))
            )}
          </div>
        </aside>

        {/* CENTER — conversation */}
        <main className="flex min-w-0 flex-1 flex-col overflow-hidden rounded-xl border border-brand-border bg-card shadow-sm">
          {activePo ? (
            <>
              <div className="flex items-center gap-2 border-b border-brand-border px-5 py-3">
                <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${SIGNAL_DOT[(activePo.signal || "").toUpperCase()] ?? "bg-subtle"}`} />
                <h2 className="truncate font-semibold text-brand-dark">
                  PO #{activePo.supplier_po_no}
                  <span className="ml-2 font-normal text-brand-muted">{activePo.counterparty}</span>
                </h2>
                <span className="ml-2 hidden text-xs text-brand-muted md:inline">
                  {messages.length} message{messages.length === 1 ? "" : "s"}
                </span>
              </div>

              <div className="flex-1 space-y-6 overflow-y-auto px-6 py-6 lg:px-10">
                {loadingMsgs ? (
                  <EmptyState icon={<Loader2 className="animate-spin" size={22} />}>Loading messages…</EmptyState>
                ) : messages.length === 0 ? (
                  <EmptyState icon={<MessagesSquare size={22} />}>
                    No messages yet. Start the conversation below.
                  </EmptyState>
                ) : (
                  messages.map((m) => <MessageBubble key={m.id} m={m} />)
                )}
                <div ref={endRef} />
              </div>

              {/* Composer */}
              <div className="border-t border-brand-border px-5 py-3">
                <div className="relative">
                  <textarea
                    value={composer}
                    onChange={(e) => setComposer(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey) {
                        e.preventDefault();
                        void send();
                      }
                    }}
                    placeholder="Type your message…  (Enter to send, Shift+Enter for a new line)"
                    className="h-24 w-full resize-none rounded-lg border border-brand-border bg-subtle p-3 pr-16 text-sm outline-none focus:border-signal-red/40 focus:bg-card"
                  />
                  <button
                    className="absolute bottom-3 right-3 rounded-md bg-signal-red p-2 text-white shadow-sm hover:opacity-90 disabled:opacity-50"
                    disabled={!composer.trim() || sending}
                    onClick={() => void send()}
                    title="Send message"
                  >
                    {sending ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
                  </button>
                </div>
              </div>
            </>
          ) : (
            <div className="grid flex-1 place-items-center text-brand-muted">
              <div className="text-center">
                <MessagesSquare size={34} className="mx-auto mb-2 opacity-40" />
                <p className="text-sm">Select a purchase order to view the conversation.</p>
              </div>
            </div>
          )}
        </main>

        {/* RIGHT — context panel */}
        <aside className="hidden w-[300px] shrink-0 flex-col overflow-hidden rounded-xl border border-brand-border bg-card shadow-sm lg:flex">
          <div className="border-b border-brand-border px-4 py-3">
            <div className="text-sm font-semibold text-brand-dark">Context</div>
            <div className="truncate text-[11px] text-brand-muted">
              {activePo ? `PO #${activePo.supplier_po_no}` : "No PO selected"}
            </div>
          </div>
          <div className="flex-1 space-y-4 overflow-y-auto p-4">
            {!activePo ? (
              <EmptyState icon={<Inbox size={18} />}>Select a PO to see its details.</EmptyState>
            ) : (
              <>
                {/* Materials */}
                <div>
                  <div className="mb-2 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-brand-muted">
                    <Package size={12} /> Materials ({materials.length || activePo.material_count || 0})
                  </div>
                  {materials.length === 0 ? (
                    <div className="text-xs text-brand-muted">No materials on this PO.</div>
                  ) : (
                    <div className="space-y-1.5">
                      {materials.map((m, i) => (
                        <div key={i} className="rounded-lg border border-brand-border p-2 text-xs">
                          <div className="flex items-center gap-1.5">
                            <span className={`h-2 w-2 shrink-0 rounded-full ${SIGNAL_DOT[(m.signal || "").toUpperCase()] ?? "bg-subtle"}`} />
                            <span className="truncate font-medium text-brand-dark" title={m.material_name}>{m.material_name}</span>
                          </div>
                          {m.commitment_date && (
                            <div className="mt-0.5 pl-3.5 text-brand-muted">Committed: {m.commitment_date}</div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Tasks */}
                {adapter.listTasks && (
                  <div>
                    <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-brand-muted">
                      Tasks ({poTasks.length})
                    </div>
                    {poTasks.length === 0 ? (
                      <div className="text-xs text-brand-muted">No tasks for this PO.</div>
                    ) : (
                      <div className="space-y-2">
                        {poTasks.map((t) => {
                          const sig = (t.signal || "").toUpperCase();
                          const done = (t.status || "").toUpperCase() === "DONE";
                          return (
                            <div key={t.id} className={`rounded-lg border border-brand-border bg-card p-2.5 text-xs ${done ? "opacity-60" : ""}`}>
                              <div className="flex items-start gap-2">
                                <span className={`mt-1 h-2 w-2 shrink-0 rounded-full ${SIGNAL_DOT[sig] ?? "bg-subtle"}`} />
                                <div className="min-w-0">
                                  <p className={`font-semibold leading-snug ${done ? "text-brand-muted line-through" : "text-brand-dark"}`}>{t.title}</p>
                                  {t.material_name && <p className="mt-0.5 truncate text-[10px] text-brand-muted">{t.material_name}</p>}
                                </div>
                              </div>
                              <div className="mt-1.5 flex items-center justify-between">
                                <span className={`rounded px-1.5 py-0.5 text-[9px] font-bold ${SIGNAL_CHIP[sig] ?? "bg-subtle text-brand-muted"}`}>
                                  {t.priority}
                                </span>
                                <span className="text-[10px] text-brand-muted">{t.status}</span>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                )}
              </>
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}

function PoRow({
  p,
  active,
  counterpartyLabel,
  onClick,
}: {
  p: CommHubPoRow;
  active: boolean;
  counterpartyLabel: string;
  onClick: () => void;
}) {
  const sig = (p.signal || "GREEN").toUpperCase();
  const unread = (p.unread_inbound ?? 0) > 0;
  return (
    <button
      onClick={onClick}
      className={`w-full border-b border-brand-border px-4 py-3 text-left transition hover:bg-subtle ${
        active
          ? "bg-red-50/50 ring-1 ring-inset ring-red-100"
          : unread
          ? "border-l-4 border-l-emerald-500 bg-emerald-50/40"
          : ""
      }`}
    >
      <div className="flex items-center gap-2">
        {unread && <span className="h-2 w-2 shrink-0 rounded-full bg-emerald-500" title="Unread replies" />}
        <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${SIGNAL_DOT[sig] ?? "bg-subtle"}`} />
        <span className={`flex-1 truncate text-sm text-brand-dark ${unread ? "font-bold" : "font-medium"}`}>
          #{p.supplier_po_no}
        </span>
        {unread && (
          <span className="rounded-full bg-emerald-500 px-1.5 py-0.5 text-[10px] font-bold text-white">
            {(p.unread_inbound ?? 0) > 99 ? "99+" : p.unread_inbound}
          </span>
        )}
        {p.escalated && (
          <span className="rounded bg-red-50 px-1.5 py-0.5 text-[10px] font-bold text-signal-red">Escalated</span>
        )}
      </div>
      <p className={`mt-1 truncate pl-4 text-xs ${unread ? "font-medium text-brand-dark/80" : "text-brand-muted"}`}>
        {counterpartyLabel}: {p.counterparty || "—"}
      </p>
    </button>
  );
}

function MessageBubble({ m }: { m: PortalMessage }) {
  // OUTGOING (mine) → right; INCOMING → left.
  const isMine = m.mine;
  return (
    <div className={`flex flex-col ${isMine ? "items-end" : "items-start"}`}>
      <div
        className={`max-w-[82%] rounded-2xl border p-4 shadow-sm ${
          isMine ? "border-amber-100 bg-amber-50" : "border-brand-border bg-card"
        }`}
      >
        {m.subject && (
          <div className="mb-1 truncate text-xs font-semibold text-brand-dark">{m.subject}</div>
        )}
        <p className="whitespace-pre-wrap break-words text-sm leading-relaxed text-brand-dark">{m.body}</p>
        <div className="mt-2 flex flex-wrap items-center gap-2 text-[10px] text-brand-muted">
          <span>{fmtTime(m.at)}</span>
          <span>·</span>
          <span>{m.author}</span>
        </div>
      </div>
    </div>
  );
}

"use client";

import { useCallback, useEffect, useState } from "react";
import {
  ShieldAlert,
  Loader2,
  RefreshCw,
  CheckCircle2,
  Clock,
  Bot,
  Mail,
  CornerDownRight,
  Sparkles,
  Send,
  X,
  Eye,
  ArrowUpRight,
  ArrowDownLeft,
  ThumbsUp,
  ThumbsDown,
  History as HistoryIcon,
} from "lucide-react";

import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth";
import { Logo } from "@/components/brand/Logo";
import { DataTable, type Column } from "@/components/ui/DataTable";
import { fmtDate } from "@/lib/format";
import type {
  BlackFollowup,
  BlackFollowupThreadItem,
  BlackFollowupCommandResult,
  FollowupAttempt,
} from "@/lib/types";

function fmt(at: string | null): string {
  if (!at) return "";
  try {
    return new Date(at).toLocaleString(undefined, {
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return at.slice(0, 16);
  }
}

function isAiOutgoing(t: BlackFollowupThreadItem): boolean {
  const mt = (t.mail_type || "").toUpperCase();
  return mt.startsWith("PO_") || mt.includes("AI") || mt.includes("ESCALAT") || mt.includes("FOLLOWUP");
}

export default function BlackFollowupsPage() {
  const [items, setItems] = useState<BlackFollowup[]>([]);
  const [chasing, setChasing] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedPo, setSelectedPo] = useState<string | null>(null);
  const [view, setView] = useState<"active" | "history">("active");
  const [history, setHistory] = useState<FollowupAttempt[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [selectedAttempt, setSelectedAttempt] = useState<FollowupAttempt | null>(null);

  const loadHistory = useCallback(() => {
    setHistoryLoading(true);
    setError(null);
    api
      .getFollowupHistory({ signal: "BLACK", limit: 200 })
      .then((r) => setHistory(r.items))
      .catch((e) => setError((e as Error).message))
      .finally(() => setHistoryLoading(false));
  }, []);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    api
      .getBlackFollowups(100)
      .then((r) => {
        setItems(r.items);
        setChasing(r.chasing);
      })
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (view === "history") loadHistory();
  }, [view, loadHistory]);

  const received = items.length - chasing;
  const selected = items.find((i) => i.supplier_po_no === selectedPo) ?? null;

  const columns: Column<BlackFollowup>[] = [
    {
      key: "po",
      header: "PO",
      sortValue: (r) => r.supplier_po_no,
      render: (r) => (
        <div>
          <div className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 shrink-0 rounded-full bg-gray-900" />
            <span className="font-semibold text-signal-red">{r.supplier_po_no}</span>
          </div>
          {r.escalation_levels?.length > 0 && (
            <span className="mt-0.5 inline-block rounded bg-gray-900 px-1.5 py-0.5 text-[10px] font-medium text-white">
              {r.escalation_levels.join(", ")}
            </span>
          )}
        </div>
      ),
    },
    {
      key: "supplier",
      header: "Supplier",
      sortValue: (r) => r.supplier_name ?? "",
      render: (r) => <span className="text-brand-dark">{r.supplier_name || "—"}</span>,
    },
    {
      key: "late",
      header: "Due / Late",
      sortValue: (r) => r.days_late ?? -99999,
      render: (r) => (
        <div>
          <div className="text-xs text-brand-muted">{r.earliest_due_date?.slice(0, 10) || "—"}</div>
          {r.days_late !== null && r.days_late > 0 && (
            <div className="text-xs font-semibold text-signal-red">{r.days_late}d late</div>
          )}
        </div>
      ),
    },
    {
      key: "commitment",
      header: "Commitment",
      sortValue: (r) => (r.commitment_captured ? 1 : 0),
      render: (r) => (
        <span className="inline-flex items-center gap-1">
          {r.commitment_captured ? (
            <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] font-semibold text-emerald-700">
              <CheckCircle2 className="h-3 w-3" /> Received
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 rounded-full bg-red-100 px-2 py-0.5 text-[11px] font-semibold text-signal-red">
              <Clock className="h-3 w-3" /> Chasing
            </span>
          )}
          <span className="text-[11px] text-brand-muted">
            {r.committed_count}/{r.material_count}
          </span>
        </span>
      ),
    },
    {
      key: "convo",
      header: "Conversation",
      sortValue: (r) => r.message_count,
      render: (r) => (
        <div className="flex items-center gap-2 text-[11px] text-brand-muted">
          <span className="inline-flex items-center gap-0.5 text-violet-600">
            <ArrowUpRight className="h-3 w-3" />
            {r.outgoing_count}
          </span>
          <span className="inline-flex items-center gap-0.5">
            <ArrowDownLeft className="h-3 w-3" />
            {r.incoming_count}
          </span>
        </div>
      ),
    },
    {
      key: "action",
      header: "",
      align: "right",
      render: (r) => (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            setSelectedPo(r.supplier_po_no);
          }}
          className="inline-flex items-center gap-1.5 rounded-md border border-brand-border px-2.5 py-1 text-xs font-medium text-brand-dark hover:bg-white"
        >
          <Eye className="h-3.5 w-3.5" /> View
        </button>
      ),
    },
  ];

  return (
    <div className="page-stack">
      {/* Header */}
      <div className="page-header">
        <div className="flex items-center gap-2">
          <span className="icon-tile bg-gray-900 text-white">
            <ShieldAlert size={16} />
          </span>
          <div>
            <h1 className="page-title">Black Follow-ups</h1>
            <p className="page-subtitle">
              How Harmony Intelligent is auto-chasing the most critical POs — it keeps following up until a
              commitment date is secured.
            </p>
          </div>
        </div>
        <div className="page-actions">
          <div className="inline-flex rounded-md border border-brand-border bg-white p-0.5">
            {(["active", "history"] as const).map((v) => (
              <button
                key={v}
                onClick={() => { setError(null); setView(v); }}
                className={cn(
                  "rounded px-3 py-1 text-xs font-medium",
                  view === v ? "bg-signal-red text-white" : "text-brand-muted hover:text-brand-dark",
                )}
              >
                {v === "active" ? "Active" : "History"}
              </button>
            ))}
          </div>
          <button
            onClick={view === "active" ? load : loadHistory}
            disabled={view === "active" ? loading : historyLoading}
            className="btn-outline"
          >
            {(view === "active" ? loading : historyLoading) ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <RefreshCw className="h-3.5 w-3.5" />
            )}
            Refresh
          </button>
        </div>
      </div>

      {error && <div className="rounded-md bg-red-50 px-3 py-2 text-xs text-signal-red">{error}</div>}

      {view === "active" ? (
        <>
          {/* Summary strip */}
          <div className="grid grid-cols-3 gap-3">
            <StatCard label="Critical POs" value={items.length} tone="bg-gray-900 text-white" />
            <StatCard label="AI still chasing" value={chasing} tone="bg-red-50 text-signal-red" />
            <StatCard label="Commitment received" value={received < 0 ? 0 : received} tone="bg-emerald-50 text-emerald-700" />
          </div>

          <DataTable
            columns={columns}
            rows={items}
            getRowId={(r) => r.supplier_po_no}
            onRowClick={(r) => setSelectedPo(r.supplier_po_no)}
            searchText={(r) => `${r.supplier_po_no} ${r.supplier_name ?? ""}`}
            searchPlaceholder="Search PO or supplier…"
            initialSort={{ key: "late", dir: "desc" }}
            pageSize={10}
            loading={loading}
            emptyMessage="No BLACK-signal POs right now. 🎉 Nothing critical to chase."
          />

          {selected && (
            <DetailDrawer item={selected} onClose={() => setSelectedPo(null)} onSent={load} />
          )}
        </>
      ) : (
        <FollowupHistoryTable items={history} loading={historyLoading} onOpen={setSelectedAttempt} />
      )}

      {selectedAttempt && (
        <AttemptDetailModal attempt={selectedAttempt} onClose={() => setSelectedAttempt(null)} />
      )}
    </div>
  );
}

function AttemptBadge({ outcome }: { outcome: string }) {
  const map: Record<string, string> = {
    QUEUED: "bg-blue-50 text-blue-600",
    SKIPPED: "bg-amber-50 text-amber-700",
    FAILED: "bg-red-50 text-signal-red",
  };
  return <span className={"badge " + (map[outcome] || "bg-gray-100 text-gray-600")}>{outcome}</span>;
}

function SendBadge({ status }: { status: string | null }) {
  if (!status) return <span className="text-xs text-brand-muted">—</span>;
  const up = status.toUpperCase();
  const cls = up === "SENT" ? "bg-emerald-50 text-emerald-700" : up === "FAILED" ? "bg-red-50 text-signal-red" : "bg-gray-100 text-gray-600";
  return <span className={"badge " + cls}>{up}</span>;
}

function recipientsLabel(a: FollowupAttempt): string {
  const to = a.to_emails || [];
  if (to.length === 0) return "—";
  return to.length === 1 ? to[0] : `${to[0]} +${to.length - 1}`;
}

function FollowupHistoryTable({
  items,
  loading,
  onOpen,
}: {
  items: FollowupAttempt[];
  loading: boolean;
  onOpen: (a: FollowupAttempt) => void;
}) {
  return (
    <div className="table-shell">
      <table className="min-w-full text-sm">
        <thead className="bg-gray-50">
          <tr>
            {["When", "PO", "Supplier", "Source", "Outcome", "Harmony Intelligent", "Send", "Sent to", "Detail"].map((h) => (
              <th key={h} className="px-3 py-3 text-left table-header whitespace-nowrap">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {loading && <tr><td colSpan={9} className="px-4 py-10 text-center text-brand-muted">Loading…</td></tr>}
          {!loading && items.length === 0 && (
            <tr><td colSpan={9} className="px-4 py-10 text-center text-brand-muted">No follow-up attempts recorded yet.</td></tr>
          )}
          {items.map((a) => (
            <tr
              key={a.id}
              onClick={() => onOpen(a)}
              className="cursor-pointer border-t border-brand-border align-top hover:bg-gray-50"
            >
              <td className="px-3 py-3 whitespace-nowrap text-xs">{fmtDate(a.created_at)}{a.created_at ? " " + new Date(a.created_at).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" }) : ""}</td>
              <td className="px-3 py-3 font-medium text-brand-dark">{a.supplier_po_no || "—"}</td>
              <td className="px-3 py-3 text-xs text-brand-muted">{a.supplier_name || "—"}</td>
              <td className="px-3 py-3 text-xs uppercase text-brand-muted">{a.source}</td>
              <td className="px-3 py-3"><AttemptBadge outcome={a.outcome} /></td>
              <td className="px-3 py-3">
                {a.ai_error ? (
                  <span className="badge bg-red-50 text-signal-red" title={a.ai_error}>HI error → template</span>
                ) : a.ai_used ? (
                  <span className="badge bg-violet-50 text-violet-700">HI written</span>
                ) : (
                  <span className="text-xs text-brand-muted">Template</span>
                )}
              </td>
              <td className="px-3 py-3"><SendBadge status={a.send_status} /></td>
              <td className="px-3 py-3 max-w-[180px] truncate text-xs text-brand-muted" title={(a.to_emails || []).join(", ")}>{recipientsLabel(a)}</td>
              <td className="px-3 py-3 max-w-[240px] truncate text-xs text-brand-muted">
                {a.send_error || a.ai_error || a.detail || "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[120px_1fr] gap-2 py-1.5">
      <div className="text-xs font-semibold uppercase tracking-wide text-brand-muted">{label}</div>
      <div className="text-sm text-brand-dark">{children}</div>
    </div>
  );
}

function AttemptDetailModal({ attempt: a, onClose }: { attempt: FollowupAttempt; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4" onClick={onClose}>
      <div className="w-full max-w-lg overflow-hidden rounded-lg bg-white shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-brand-border px-5 py-3">
          <div className="font-semibold text-brand-dark">Follow-up attempt · {a.supplier_po_no || "—"}</div>
          <button className="rounded p-1 hover:bg-gray-100" onClick={onClose} aria-label="Close"><X size={18} /></button>
        </div>
        <div className="max-h-[70vh] divide-y divide-brand-border overflow-y-auto px-5 py-2">
          <DRow label="When">{fmt(a.created_at)}</DRow>
          <DRow label="Supplier">{a.supplier_name || "—"}</DRow>
          <DRow label="Source"><span className="uppercase">{a.source}</span></DRow>
          <DRow label="Outcome"><AttemptBadge outcome={a.outcome} /></DRow>
          <DRow label="Harmony Intelligent">
            {a.ai_error ? (
              <span className="text-signal-red">Errored → fell back to template</span>
            ) : a.ai_used ? (
              <span className="text-violet-700">Written by Harmony Intelligent</span>
            ) : (
              "Template (no AI)"
            )}
          </DRow>
          {a.ai_error && <DRow label="AI error"><span className="text-signal-red">{a.ai_error}</span></DRow>}
          <DRow label="Send"><SendBadge status={a.send_status} />{a.sent_at ? <span className="ml-2 text-xs text-brand-muted">{fmt(a.sent_at)}</span> : null}</DRow>
          {a.send_error && <DRow label="Send error"><span className="text-signal-red">{a.send_error}</span></DRow>}
          <DRow label="Sent to">{a.to_emails?.length ? a.to_emails.join(", ") : "—"}</DRow>
          {a.cc_emails?.length ? <DRow label="CC">{a.cc_emails.join(", ")}</DRow> : null}
          <DRow label="Subject">{a.subject || "—"}</DRow>
          {a.detail && <DRow label="Detail">{a.detail}</DRow>}
        </div>
        <div className="border-t border-brand-border px-5 py-3 text-right">
          <button className="btn-ghost" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  );
}

function StatCard({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <div className="card p-3">
      <div className="text-[11px] font-medium uppercase tracking-wide text-brand-muted">{label}</div>
      <div className="mt-1">
        <span className={`inline-flex h-7 min-w-7 items-center justify-center rounded-md px-2 text-sm font-bold ${tone}`}>
          {value}
        </span>
      </div>
    </div>
  );
}

function DetailDrawer({
  item,
  onClose,
  onSent,
}: {
  item: BlackFollowup;
  onClose: () => void;
  onSent: () => void;
}) {
  const { hasRole } = useAuth();
  const isManager = hasRole("manager");
  const [shown, setShown] = useState(false);
  const [cmd, setCmd] = useState("");
  const [busy, setBusy] = useState<null | "draft" | "send">(null);
  const [preview, setPreview] = useState<BlackFollowupCommandResult | null>(null);
  const [view, setView] = useState<"html" | "text">("html");
  const [note, setNote] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<null | "up" | "down">(null);

  useEffect(() => {
    setShown(true);
  }, []);

  // Reset the command panel when switching to a different PO.
  useEffect(() => {
    setCmd("");
    setPreview(null);
    setNote(null);
  }, [item.supplier_po_no]);

  const close = () => {
    setShown(false);
    setTimeout(onClose, 200);
  };

  const draft = async () => {
    if (!cmd.trim() || busy) return;
    setBusy("draft");
    setNote(null);
    try {
      const r = await api.blackFollowupCommand(item.supplier_po_no, cmd.trim(), false);
      setPreview(r);
      setView("html");
      setFeedback(null);
    } catch (e) {
      setNote((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const rate = async (rating: "up" | "down") => {
    if (!preview) return;
    setFeedback(rating);
    try {
      await api.submitAiFeedback({
        feature: "po_followup_command",
        rating,
        instruction: cmd.trim(),
        ai_output: preview.body,
        context_ref: item.supplier_po_no,
      });
    } catch {
      /* feedback is best-effort; ignore */
    }
  };

  const send = async () => {
    if (!cmd.trim() || busy) return;
    setBusy("send");
    setNote(null);
    try {
      const r = await api.blackFollowupCommand(item.supplier_po_no, cmd.trim(), true);
      if (r.sent) {
        setNote("✓ Sent to supplier (formatted HTML).");
        setPreview(null);
        setCmd("");
        onSent();
      } else if (r.queued) {
        setNote("Queued — will send on the next cycle.");
        setPreview(null);
      } else {
        setNote(r.skipped_reason || "Could not send (check supplier email mapping).");
      }
    } catch (e) {
      setNote((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-stretch justify-center p-0 sm:items-center sm:p-4 md:p-6">
      {/* Backdrop */}
      <div
        onClick={close}
        className={`absolute inset-0 bg-black/40 transition-opacity duration-200 ${shown ? "opacity-100" : "opacity-0"}`}
      />
      {/* Panel — large, near full-screen modal */}
      <div
        className={`relative flex h-full w-full max-w-5xl flex-col overflow-hidden bg-white shadow-2xl transition-[transform,opacity] duration-200 ease-out sm:h-[92vh] sm:rounded-2xl ${
          shown ? "scale-100 opacity-100" : "scale-95 opacity-0"
        }`}
      >
        {/* Header */}
        <div className="flex items-start justify-between gap-3 border-b border-brand-border bg-brand-surface px-5 py-3.5">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="h-2.5 w-2.5 rounded-full bg-gray-900" />
              <span className="font-semibold text-signal-red">{item.supplier_po_no}</span>
              <span className="truncate text-sm text-brand-dark">{item.supplier_name || "Unknown supplier"}</span>
              {item.commitment_captured ? (
                <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] font-semibold text-emerald-700">
                  <CheckCircle2 className="h-3 w-3" /> Commitment received
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 rounded-full bg-red-100 px-2 py-0.5 text-[11px] font-semibold text-signal-red">
                  <Clock className="h-3 w-3" /> HI chasing for commitment
                </span>
              )}
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-brand-muted">
              <span>{item.committed_count}/{item.material_count} materials committed</span>
              {item.earliest_due_date && <span>due {item.earliest_due_date.slice(0, 10)}</span>}
              {item.days_late !== null && item.days_late > 0 && (
                <span className="font-semibold text-signal-red">{item.days_late}d late</span>
              )}
              <span className="inline-flex items-center gap-1 text-violet-600">
                <Bot className="h-3.5 w-3.5" /> {item.outgoing_count} sent
              </span>
              <span className="inline-flex items-center gap-1">
                <Mail className="h-3.5 w-3.5" /> {item.incoming_count} replies
              </span>
              {item.escalation_levels?.length > 0 && (
                <span className="rounded bg-gray-900 px-1.5 py-0.5 font-medium text-white">
                  {item.escalation_levels.join(", ")}
                </span>
              )}
            </div>
          </div>
          <button onClick={close} className="rounded-md p-1.5 text-brand-muted hover:bg-white" title="Close">
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Body (scrolls) — conversation + committed materials */}
        <div className="flex-1 space-y-4 overflow-y-auto bg-brand-surface/40 px-5 py-4">
          {/* Committed materials */}
          {item.committed_count > 0 && (
            <div className="rounded-xl border border-emerald-200 bg-emerald-50/60 p-3">
              <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-emerald-700">
                Committed materials
              </div>
              <div className="space-y-0.5">
                {item.commitments
                  .filter((c) => c.commitment_date)
                  .map((c, i) => (
                    <div key={i} className="flex items-center justify-between gap-2 text-[11px]">
                      <span className="truncate text-brand-dark">{c.material_name}</span>
                      <span className="shrink-0 text-emerald-700">
                        {c.supplier_status ? `${c.supplier_status} · ` : ""}
                        {c.commitment_date?.slice(0, 10)}
                      </span>
                    </div>
                  ))}
              </div>
            </div>
          )}

          {/* Conversation */}
          <div className="mx-auto max-w-3xl">
            <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-brand-muted">
              Conversation ({item.message_count})
            </div>
            <div className="space-y-2">
              {item.thread.length === 0 ? (
                <p className="text-xs text-brand-muted">No messages recorded yet.</p>
              ) : (
                item.thread.map((t) => <ThreadBubble key={t.id} t={t} />)
              )}
            </div>
          </div>
        </div>

        {/* Sticky footer — AI draft preview + command composer */}
        <div className="shrink-0 border-t border-brand-border bg-white">
          {busy === "draft" && !preview && (
            <div className="flex items-center justify-center gap-3 border-b border-violet-100 bg-violet-50/40 px-5 py-4">
              <span className="text-signal-red">
                <Logo size={28} animated />
              </span>
              <span className="text-xs font-medium tracking-wide text-violet-700">
                Harmony Intelligent is drafting the follow-up…
              </span>
            </div>
          )}
          {preview && (
            <div className="animate-slide-down max-h-[46vh] overflow-y-auto border-b border-violet-100 bg-violet-50/40 px-5 py-3">
              <div className="mx-auto max-w-3xl rounded-lg border border-violet-200 bg-white p-3">
                <div className="mb-1.5 flex flex-wrap items-center justify-between gap-2">
                  <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-violet-700">
                    <Bot className="h-3.5 w-3.5" /> HI draft{preview.source === "ai" ? "" : " (template)"} · sent as HTML
                  </span>
                  <div className="flex items-center gap-2">
                    <div className="flex overflow-hidden rounded-md border border-violet-200 text-[10px]">
                      <button
                        type="button"
                        onClick={() => setView("html")}
                        className={view === "html" ? "bg-violet-600 px-2 py-0.5 text-white" : "bg-white px-2 py-0.5 text-violet-700"}
                      >
                        Formatted
                      </button>
                      <button
                        type="button"
                        onClick={() => setView("text")}
                        className={view === "text" ? "bg-violet-600 px-2 py-0.5 text-white" : "bg-white px-2 py-0.5 text-violet-700"}
                      >
                        Text
                      </button>
                    </div>
                    <button type="button" onClick={() => setPreview(null)} className="text-[11px] text-brand-muted hover:underline">
                      Discard
                    </button>
                    {isManager && (
                      <button
                        type="button"
                        onClick={send}
                        disabled={busy !== null || !preview.mapping_active}
                        title={preview.mapping_active ? "Send to the supplier" : "No active supplier email mapping"}
                        className="inline-flex items-center gap-1.5 rounded-md bg-signal-red px-2.5 py-1 text-xs font-medium text-white hover:opacity-90 disabled:opacity-50"
                      >
                        {busy === "send" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3 w-3" />}
                        Send
                      </button>
                    )}
                  </div>
                </div>
                {preview.subject && <div className="mb-1.5 text-[11px] font-medium text-brand-dark">{preview.subject}</div>}
                {view === "html" && preview.body_html ? (
                  <iframe
                    title="Email preview"
                    sandbox=""
                    srcDoc={preview.body_html}
                    className="h-72 w-full rounded-md border border-violet-200 bg-white"
                  />
                ) : (
                  <p className="whitespace-pre-wrap text-xs leading-relaxed text-brand-dark">{preview.body}</p>
                )}
                {!preview.mapping_active && (
                  <p className="mt-1.5 text-[10px] text-signal-red">
                    No active supplier email mapping — add one in Email Master to enable sending.
                  </p>
                )}
                {/* Feedback — feeds the AI tuning dataset */}
                <div className="mt-2 flex items-center gap-2 border-t border-violet-100 pt-2 text-[11px] text-brand-muted">
                  <span>Helpful?</span>
                  <button
                    type="button"
                    onClick={() => rate("up")}
                    className={feedback === "up" ? "text-emerald-600" : "hover:text-emerald-600"}
                    title="Good draft"
                  >
                    <ThumbsUp className="h-3.5 w-3.5" />
                  </button>
                  <button
                    type="button"
                    onClick={() => rate("down")}
                    className={feedback === "down" ? "text-signal-red" : "hover:text-signal-red"}
                    title="Needs work"
                  >
                    <ThumbsDown className="h-3.5 w-3.5" />
                  </button>
                  {feedback && <span className="text-emerald-700">Thanks — logged for tuning.</span>}
                </div>
              </div>
            </div>
          )}

          {/* Composer */}
          <div className="mx-auto max-w-3xl px-5 py-3">
            <div className="mb-1.5 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-violet-700">
              <Sparkles className="h-3.5 w-3.5" /> Command Harmony Intelligent
            </div>
            <div className="flex flex-col gap-2 sm:flex-row">
              <input
                value={cmd}
                onChange={(e) => setCmd(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && draft()}
                placeholder='e.g. "be more aggressive and demand a date by Friday"'
                className="input flex-1"
              />
              <button
                type="button"
                onClick={draft}
                disabled={busy !== null || !cmd.trim()}
                className="inline-flex items-center justify-center gap-1.5 rounded-md border border-violet-300 bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-700 disabled:opacity-50"
              >
                {busy === "draft" ? <Logo size={16} animated /> : <Sparkles className="h-3.5 w-3.5" />}
                Draft
              </button>
            </div>
            {note && <p className="mt-2 text-xs font-medium text-emerald-700">{note}</p>}
          </div>
        </div>
      </div>
    </div>
  );
}

function ThreadBubble({ t }: { t: BlackFollowupThreadItem }) {
  const outgoing = t.direction === "OUTGOING";
  const ai = outgoing && isAiOutgoing(t);
  return (
    <div className={`flex ${outgoing ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[88%] rounded-xl border p-3 text-xs ${
          outgoing ? "border-violet-200 bg-violet-50/70" : "border-brand-border bg-white"
        }`}
      >
        <div className="mb-1 flex items-center gap-2">
          {outgoing ? (
            <span className="inline-flex items-center gap-1 font-semibold text-violet-700">
              <Bot className="h-3.5 w-3.5" /> {ai ? "AI follow-up" : "Sent"}
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 font-semibold text-brand-dark">
              <CornerDownRight className="h-3.5 w-3.5" /> Supplier reply
            </span>
          )}
          {t.status && <span className="rounded bg-gray-100 px-1.5 py-0.5 text-[10px] text-brand-muted">{t.status}</span>}
          {t.parsed_status && (
            <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-[10px] font-medium text-emerald-700">
              {t.parsed_status}
            </span>
          )}
          <span className="ml-auto text-[10px] text-brand-muted">{fmt(t.at)}</span>
        </div>
        {t.subject && <div className="mb-0.5 font-medium text-brand-dark">{t.subject}</div>}
        <p className="whitespace-pre-wrap leading-relaxed text-brand-dark">{t.snippet}</p>
      </div>
    </div>
  );
}

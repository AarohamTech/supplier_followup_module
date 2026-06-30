"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowLeft, MessageSquare, Send } from "lucide-react";

import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { fmtDate } from "@/lib/format";
import { signalBadge } from "@/lib/asn";
import type { PortalMessage, PortalPo } from "@/lib/types";

function timeLabel(at?: string | null): string {
  if (!at) return "";
  const d = new Date(at);
  if (isNaN(d.getTime())) return "";
  return `${fmtDate(at)} · ${d.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })}`;
}

/**
 * Container-filling chat pane for one PO: header + scrollable thread + composer.
 * Used as the right "reading pane" of the My POs split view (and as a mobile
 * overlay via `onBack`).
 */
export default function PoChatPanel({
  po,
  onBack,
  onSent,
}: {
  po: PortalPo | null;
  onBack?: () => void;
  onSent?: (po: PortalPo) => void;
}) {
  const [messages, setMessages] = useState<PortalMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const endRef = useRef<HTMLDivElement | null>(null);

  const poNo = po?.supplier_po_no;

  // Fetch the thread. `silent` polls in the background (no spinner) and only
  // updates state when the newest message changes — so live updates don't
  // disturb scrolling or re-render needlessly.
  const load = useCallback(
    async (silent: boolean) => {
      if (!poNo) {
        setMessages([]);
        return;
      }
      if (!silent) setLoading(true);
      try {
        const m = await api.portalPoMessages(poNo);
        setMessages((prev) =>
          prev.length === m.length && prev[prev.length - 1]?.id === m[m.length - 1]?.id ? prev : m,
        );
        setError(null);
      } catch (e) {
        if (!silent) setError((e as Error).message);
      } finally {
        if (!silent) setLoading(false);
      }
    },
    [poNo],
  );

  useEffect(() => {
    void load(false);
  }, [load]);

  // Live polling: pick up the buyer's replies without a manual refresh.
  useEffect(() => {
    if (!poNo) return;
    const t = setInterval(() => void load(true), 8000);
    return () => clearInterval(t);
  }, [poNo, load]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length]);

  if (!po) {
    return (
      <div className="flex h-full flex-col items-center justify-center text-center text-brand-muted">
        <div className="mb-3 flex h-14 w-14 items-center justify-center rounded-2xl bg-subtle">
          <MessageSquare size={22} />
        </div>
        <div className="font-medium text-brand-dark">Select a PO to read</div>
        <div className="text-xs">Choose a purchase order on the left to view its messages.</div>
      </div>
    );
  }

  const send = async () => {
    const text = draft.trim();
    if (!text) return;
    setSending(true);
    setError(null);
    try {
      const msg = await api.sendPortalPoMessage(po.supplier_po_no, text);
      setMessages((prev) => [...prev, msg]);
      setDraft("");
      onSent?.(po);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex items-center gap-2 border-b border-brand-border px-4 py-3">
        {onBack && (
          <button onClick={onBack} className="md:hidden p-1 rounded hover:bg-subtle" aria-label="Back">
            <ArrowLeft size={18} />
          </button>
        )}
        <div className="min-w-0">
          <div className="font-semibold text-brand-dark">PO {po.supplier_po_no}</div>
          <div className="flex items-center gap-2 text-xs text-brand-muted">
            <span>{po.material_count} material{po.material_count === 1 ? "" : "s"}</span>
            {po.overall_signal && <span className={"badge " + signalBadge(po.overall_signal)}>{po.overall_signal}</span>}
            {po.completed && <span className="badge badge-track">Completed</span>}
          </div>
        </div>
      </div>

      {/* Thread */}
      <div className="flex-1 space-y-3 overflow-y-auto bg-brand-surface px-4 py-4">
        {error && <div className="rounded-md bg-red-50 px-3 py-2 text-xs text-signal-red">{error}</div>}
        {loading && <div className="text-center text-sm text-brand-muted">Loading messages…</div>}
        {!loading && messages.length === 0 && !error && (
          <div className="empty-state">
            No messages yet for this PO. Send one below — your buyer sees it in their Communication Hub.
          </div>
        )}
        {messages.map((m) => (
          <div key={m.id} className={cn("flex", m.mine ? "justify-end" : "justify-start")}>
            <div
              className={cn(
                "max-w-[80%] rounded-lg px-3 py-2 text-sm shadow-sm",
                m.mine ? "bg-signal-red text-white" : "bg-card border border-brand-border text-brand-dark",
              )}
            >
              <div className={cn("mb-0.5 text-[10px] font-semibold", m.mine ? "text-white/80" : "text-brand-muted")}>
                {m.author}
              </div>
              {m.subject && (
                <div className={cn("mb-1 text-xs font-semibold", m.mine ? "text-white" : "text-brand-dark")}>
                  {m.subject}
                </div>
              )}
              <div className="whitespace-pre-wrap break-words">{m.body}</div>
              <div className={cn("mt-1 text-[10px]", m.mine ? "text-white/70" : "text-brand-muted")}>
                {timeLabel(m.at)}
              </div>
            </div>
          </div>
        ))}
        <div ref={endRef} />
      </div>

      {/* Composer */}
      <div className="border-t border-brand-border p-3">
        <div className="flex items-end gap-2">
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
                e.preventDefault();
                void send();
              }
            }}
            rows={2}
            placeholder="Write a message to your buyer…"
            className="input flex-1 resize-none"
          />
          <button className="btn-primary h-10 shrink-0" disabled={sending || !draft.trim()} onClick={send}>
            <Send size={14} /> {sending ? "Sending…" : "Send"}
          </button>
        </div>
        <div className="mt-1 text-[10px] text-brand-muted">Ctrl/⌘ + Enter to send. Your buyer is notified in their Communication Hub.</div>
      </div>
    </div>
  );
}

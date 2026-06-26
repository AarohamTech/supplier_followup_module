"use client";

import { useEffect, useState } from "react";
import { MessageSquare } from "lucide-react";

import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { PortalPo } from "@/lib/types";
import { fmtDate } from "@/lib/format";
import { signalBadge } from "@/lib/asn";
import PoChatPanel from "@/components/portal/PoChatPanel";

export default function CommunicationHubPage() {
  const [items, setItems] = useState<PortalPo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<PortalPo | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await api.portalPos();
        if (cancelled) return;
        setItems(res.items);
        // Deep-link: /portal/communication?po=SBT-... pre-selects that thread.
        const wanted =
          typeof window !== "undefined"
            ? new URLSearchParams(window.location.search).get("po")
            : null;
        if (wanted) setSelected(res.items.find((p) => p.supplier_po_no === wanted) ?? null);
      } catch (e) {
        if (!cancelled) setError((e as Error).message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const filtered = items.filter((p) =>
    !q.trim()
      ? true
      : `${p.supplier_po_no} ${p.crm_no ?? ""}`.toLowerCase().includes(q.trim().toLowerCase()),
  );

  const onSent = (po: PortalPo) =>
    setItems((prev) =>
      prev.map((p) =>
        p.supplier_po_no === po.supplier_po_no ? { ...p, message_count: p.message_count + 1 } : p,
      ),
    );

  return (
    <div className="flex h-[calc(100vh-7.25rem)] flex-col">
      <div className="page-header shrink-0">
        <div className="flex items-start gap-3">
          <div className="icon-tile bg-red-50 text-signal-red">
            <MessageSquare size={18} />
          </div>
          <div>
            <h1 className="page-title">Communication Hub</h1>
            <p className="page-subtitle">Message your buyer about any PO. Replies appear here live.</p>
          </div>
        </div>
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search PO / CRM…"
          className="input max-w-xs"
        />
      </div>

      {error && <div className="mt-3 shrink-0 rounded-md bg-red-50 px-3 py-2 text-xs text-signal-red">{error}</div>}

      <div className="mt-3 flex min-h-0 flex-1 gap-4">
        {/* Left: PO conversations */}
        <div className={cn("card flex w-full flex-col overflow-hidden md:w-[380px] md:shrink-0", selected && "hidden md:flex")}>
          <div className="shrink-0 border-b border-brand-border px-4 py-2 text-[11px] font-semibold uppercase tracking-wider text-brand-muted">
            {loading ? "Loading…" : `${filtered.length} conversation${filtered.length === 1 ? "" : "s"}`}
          </div>
          <ul className="flex-1 divide-y divide-brand-border overflow-y-auto">
            {!loading && filtered.length === 0 && (
              <li className="px-4 py-10 text-center text-sm text-brand-muted">No purchase orders found.</li>
            )}
            {filtered.map((p) => {
              const active = selected?.supplier_po_no === p.supplier_po_no;
              return (
                <li key={p.supplier_po_no}>
                  <button
                    onClick={() => setSelected(p)}
                    className={cn(
                      "flex w-full flex-col gap-1 px-4 py-3 text-left hover:bg-gray-50",
                      active && "bg-red-50 shadow-[inset_3px_0_0_#E11D2E]",
                    )}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-medium text-brand-dark">{p.supplier_po_no}</span>
                      <span className="inline-flex items-center gap-1 text-xs text-brand-muted">
                        <MessageSquare size={13} />
                        {p.message_count}
                      </span>
                    </div>
                    <div className="flex flex-wrap items-center gap-1.5 text-xs text-brand-muted">
                      {p.escalated && <span className="badge badge-critical">Escalated</span>}
                      {p.overall_signal && <span className={"badge " + signalBadge(p.overall_signal)}>{p.overall_signal}</span>}
                      <span>· Due {fmtDate(p.earliest_shipment_date)}</span>
                    </div>
                  </button>
                </li>
              );
            })}
          </ul>
        </div>

        {/* Right: chat */}
        <div className={cn("card flex-1 overflow-hidden", !selected && "hidden md:flex")}>
          <PoChatPanel po={selected} onBack={() => setSelected(null)} onSent={onSent} />
        </div>
      </div>
    </div>
  );
}

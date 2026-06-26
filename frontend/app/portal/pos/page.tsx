"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ChevronRight, MessageSquare } from "lucide-react";

import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { PortalPo } from "@/lib/types";
import { fmtDate } from "@/lib/format";
import { signalBadge } from "@/lib/asn";

export default function PortalPosPage() {
  const router = useRouter();
  const [items, setItems] = useState<PortalPo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await api.portalPos();
        if (!cancelled) setItems(res.items);
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

  const open = (po: string) => router.push(`/portal/pos/${encodeURIComponent(po)}`);

  return (
    <div className="page-stack">
      <div className="page-header">
        <div>
          <h1 className="page-title">My Purchase Orders</h1>
          <p className="page-subtitle">All your POs. Escalated orders are pinned to the top — click a row for details.</p>
        </div>
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search PO / CRM…"
          className="input max-w-xs"
        />
      </div>

      {error && <div className="rounded-md bg-red-50 px-3 py-2 text-xs text-signal-red">{error}</div>}

      <div className="table-shell">
        <table className="min-w-full text-sm">
          <thead className="bg-gray-50">
            <tr>
              {["PO Reference", "CRM No", "Materials", "Signal", "Earliest Due", "ASNs", "Messages", "Status", ""].map((h) => (
                <th key={h} className="px-4 py-3 text-left table-header whitespace-nowrap">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr><td colSpan={9} className="px-4 py-10 text-center text-brand-muted">Loading…</td></tr>
            )}
            {!loading && filtered.length === 0 && (
              <tr><td colSpan={9} className="px-4 py-10 text-center text-brand-muted">No purchase orders found.</td></tr>
            )}
            {filtered.map((p) => (
              <tr
                key={p.supplier_po_no}
                onClick={() => open(p.supplier_po_no)}
                className={cn(
                  "cursor-pointer border-t border-brand-border hover:bg-gray-50",
                  p.escalated && "bg-red-50/50",
                )}
              >
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-brand-dark">{p.supplier_po_no}</span>
                    {p.escalated && <span className="badge badge-critical">Escalated</span>}
                  </div>
                </td>
                <td className="px-4 py-3 text-xs text-brand-muted">{p.crm_no || "—"}</td>
                <td className="px-4 py-3">{p.material_count}</td>
                <td className="px-4 py-3">
                  {p.overall_signal ? <span className={"badge " + signalBadge(p.overall_signal)}>{p.overall_signal}</span> : "—"}
                </td>
                <td className="px-4 py-3 text-xs">{fmtDate(p.earliest_shipment_date)}</td>
                <td className="px-4 py-3">{p.asn_count}</td>
                <td className="px-4 py-3">
                  <span className="inline-flex items-center gap-1 text-brand-muted">
                    <MessageSquare size={13} /> {p.message_count}
                  </span>
                </td>
                <td className="px-4 py-3">
                  {p.completed ? (
                    <span className="badge badge-track">Completed</span>
                  ) : (
                    <span className="badge badge-due">Pending</span>
                  )}
                </td>
                <td className="px-4 py-3 text-right text-brand-muted">
                  <ChevronRight size={16} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

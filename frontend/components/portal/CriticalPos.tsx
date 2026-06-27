"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, ShieldAlert } from "lucide-react";

import { fmtDate } from "@/lib/format";
import type { PortalPo } from "@/lib/types";

/** Live HH/MM/SS overdue counter for one black PO. */
function Countdown({ due, now }: { due: number; now: number }) {
  const diff = due - now;
  const overdue = diff < 0;
  const abs = Math.abs(diff);
  const d = Math.floor(abs / 86_400_000);
  const h = Math.floor((abs % 86_400_000) / 3_600_000);
  const m = Math.floor((abs % 3_600_000) / 60_000);
  const s = Math.floor((abs % 60_000) / 1000);

  if (overdue) {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-md bg-signal-red px-2.5 py-1 font-mono text-sm font-bold text-white animate-pulse-ring">
        <AlertTriangle size={13} />
        Overdue {d}d {h}h {m}m {s}s
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 rounded-md bg-amber-100 px-2.5 py-1 font-mono text-sm font-bold text-amber-700">
      Due in {d}d {h}h {m}m
    </span>
  );
}

export default function CriticalPos({ pos }: { pos: PortalPo[] }) {
  const [now, setNow] = useState<number>(() => Date.now());

  // One ticking clock drives every row's countdown.
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  const black = pos
    // Black + still open (a delivered PO is no longer actionable).
    .filter((p) => (p.overall_signal || "").toUpperCase() === "BLACK" && !p.completed)
    .sort((a, b) => {
      // Most overdue first (earliest due date first).
      const da = a.earliest_shipment_date ? new Date(a.earliest_shipment_date).getTime() : Infinity;
      const db = b.earliest_shipment_date ? new Date(b.earliest_shipment_date).getTime() : Infinity;
      return da - db;
    });

  if (black.length === 0) {
    return (
      <div className="card p-4">
        <div className="flex items-center gap-3">
          <div className="icon-tile bg-emerald-50 text-emerald-600">
            <ShieldAlert size={16} />
          </div>
          <div>
            <div className="font-semibold text-brand-dark">No critical (Black) POs</div>
            <div className="text-xs text-brand-muted">You have no orders flagged Black right now.</div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="card overflow-hidden">
      <div className="flex items-center justify-between border-b border-brand-border bg-red-50/60 px-4 py-3">
        <div className="flex items-center gap-2">
          <ShieldAlert size={16} className="text-signal-red" />
          <span className="font-semibold text-brand-dark">Critical — Black POs</span>
          <span className="badge badge-critical">{black.length}</span>
        </div>
        <span className="text-[11px] uppercase tracking-wider text-brand-muted">Action required</span>
      </div>

      <ul className="divide-y divide-brand-border">
        {black.map((p) => {
          const dueMs = p.earliest_shipment_date ? new Date(p.earliest_shipment_date).getTime() : null;
          return (
            <li key={p.supplier_po_no} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
              <div className="min-w-0">
                <div className="font-medium text-brand-dark">{p.supplier_po_no}</div>
                <div className="text-xs text-brand-muted">
                  {p.material_count} material{p.material_count === 1 ? "" : "s"}
                  {p.crm_no ? ` · CRM ${p.crm_no}` : ""} · Due {fmtDate(p.earliest_shipment_date)}
                </div>
              </div>
              {dueMs !== null ? (
                <Countdown due={dueMs} now={now} />
              ) : (
                <span className="badge badge-critical">No due date</span>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

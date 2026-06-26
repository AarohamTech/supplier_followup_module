"use client";

import { AlertTriangle } from "lucide-react";

import { stageMeta } from "@/lib/asn";
import { fmtDate } from "@/lib/format";
import type { Asn } from "@/lib/types";

export default function AsnTable({
  items,
  loading,
  onOpen,
  showSupplier = false,
  emptyLabel = "No shipments here yet.",
}: {
  items: Asn[];
  loading?: boolean;
  onOpen: (asn: Asn) => void;
  showSupplier?: boolean;
  emptyLabel?: string;
}) {
  const cols = showSupplier
    ? ["ASN ID", "Supplier", "PO Reference", "Carrier / Tracking", "Progress", "Status"]
    : ["ASN ID", "PO Reference", "Carrier / Tracking", "Progress", "Status"];

  return (
    <div className="table-shell">
      <table className="min-w-full text-sm">
        <thead className="bg-gray-50">
          <tr>
            {cols.map((h) => (
              <th key={h} className="px-4 py-3 text-left table-header whitespace-nowrap">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {loading && (
            <tr><td colSpan={cols.length} className="px-4 py-10 text-center text-brand-muted">Loading…</td></tr>
          )}
          {!loading && items.length === 0 && (
            <tr><td colSpan={cols.length} className="px-4 py-10 text-center text-brand-muted">{emptyLabel}</td></tr>
          )}
          {items.map((a) => {
            const meta = stageMeta(a.status);
            return (
              <tr
                key={a.id}
                className="border-t border-brand-border hover:bg-gray-50 cursor-pointer"
                onClick={() => onOpen(a)}
              >
                <td className="px-4 py-3">
                  <div className="font-medium text-brand-dark">{a.asn_no}</div>
                  <div className="text-[11px] text-brand-muted">Created {fmtDate(a.created_at)}</div>
                </td>
                {showSupplier && <td className="px-4 py-3 text-xs">{a.supplier_name || "—"}</td>}
                <td className="px-4 py-3">
                  <span className="badge bg-gray-100 text-gray-700">{a.supplier_po_no}</span>
                </td>
                <td className="px-4 py-3">
                  <div className="text-sm">{a.carrier_name || "—"}</div>
                  <div className="text-[11px] text-brand-muted">{a.tracking_no ? `#${a.tracking_no}` : ""}</div>
                </td>
                <td className="px-4 py-3 min-w-[160px]">
                  <div className="mb-1 flex items-center justify-between text-[11px]">
                    <span className="text-brand-muted">{meta.label}</span>
                    <span className="text-brand-muted">{a.progress_percent}%</span>
                  </div>
                  <div className="h-1.5 w-full overflow-hidden rounded-full bg-gray-100">
                    <div className={"h-full rounded-full " + meta.bar} style={{ width: `${a.progress_percent}%` }} />
                  </div>
                </td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-1.5">
                    <span className={"badge " + meta.badge}>{a.status_label || meta.label}</span>
                    {a.alert && <AlertTriangle size={14} className="text-signal-red" aria-label="Delayed / alert" />}
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

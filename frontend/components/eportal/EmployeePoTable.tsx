"use client";

import { Fragment, useState } from "react";
import { ChevronDown, ChevronRight, Loader2 } from "lucide-react";

import { api } from "@/lib/api";
import { overdueDays } from "@/lib/format";
import type { EmployeePo, EmployeePoMaterial } from "@/lib/types";

const SIGNAL_CLASS: Record<string, string> = {
  GREEN: "bg-emerald-50 text-emerald-700 ring-emerald-100",
  YELLOW: "bg-amber-50 text-amber-700 ring-amber-100",
  RED: "bg-red-50 text-signal-red ring-red-100",
  BLACK: "bg-ink text-white ring-gray-700",
};

function SignalChip({ signal }: { signal?: string | null }) {
  const s = (signal || "").toUpperCase();
  const cls = SIGNAL_CLASS[s] || "bg-subtle text-brand-muted ring-gray-200";
  return (
    <span className={`inline-flex rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase ring-1 ring-inset ${cls}`}>
      {s || "—"}
    </span>
  );
}

function fmtDate(d?: string | null) {
  if (!d) return "—";
  const dt = new Date(d);
  return isNaN(dt.getTime()) ? "—" : dt.toLocaleDateString();
}

// PO numbers are recycled across suppliers, so a bare PO number is not a unique
// key — scope every row/cache entry by (supplier, PO).
function poKey(p: EmployeePo): string {
  return `${(p.supplier_name || "").toUpperCase()}|${p.supplier_po_no}`;
}

export default function EmployeePoTable({ pos }: { pos: EmployeePo[] }) {
  const [open, setOpen] = useState<string | null>(null);
  const [materials, setMaterials] = useState<Record<string, EmployeePoMaterial[]>>({});
  const [loading, setLoading] = useState<string | null>(null);

  const toggle = async (p: EmployeePo) => {
    const key = poKey(p);
    if (open === key) {
      setOpen(null);
      return;
    }
    setOpen(key);
    if (!materials[key]) {
      setLoading(key);
      try {
        const m = await api.eportalPoMaterials(p.supplier_po_no, p.supplier_name || undefined);
        setMaterials((cur) => ({ ...cur, [key]: m }));
      } catch {
        /* ignore */
      } finally {
        setLoading(null);
      }
    }
  };

  if (!pos.length) {
    return <div className="card p-6 text-center text-sm text-brand-muted">No purchase orders assigned to you yet.</div>;
  }

  return (
    <div className="card overflow-x-auto">
      <table className="w-full min-w-[720px] text-sm">
        <thead className="bg-subtle text-left text-[11px] uppercase tracking-wider text-brand-muted">
          <tr>
            <th className="w-8 px-3 py-2" />
            <th className="px-3 py-2">Signal</th>
            <th className="px-3 py-2">PO No</th>
            <th className="px-3 py-2">Vendor</th>
            <th className="px-3 py-2">Materials</th>
            <th className="px-3 py-2">Earliest Ship</th>
            <th className="px-3 py-2">Status</th>
          </tr>
        </thead>
        <tbody>
          {pos.map((p) => {
            const key = poKey(p);
            const isOpen = open === key;
            const mats = materials[key];
            return (
              <Fragment key={key}>
                <tr
                  className="cursor-pointer border-t border-brand-border hover:bg-subtle"
                  onClick={() => toggle(p)}
                >
                  <td className="px-3 py-2 text-brand-muted">
                    {isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                  </td>
                  <td className="px-3 py-2"><SignalChip signal={p.overall_signal} /></td>
                  <td className="px-3 py-2 font-medium text-brand-dark">
                    {p.supplier_po_no}
                    {p.escalated && (
                      <span className="ml-2 rounded bg-red-50 px-1.5 py-0.5 text-[10px] font-semibold text-signal-red">
                        ESCALATED
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-brand-dark">{p.supplier_name || "—"}</td>
                  <td className="px-3 py-2">{p.material_count}</td>
                  <td className="px-3 py-2">{fmtDate(p.earliest_shipment_date)}</td>
                  <td className="px-3 py-2">{p.po_status || "—"}</td>
                </tr>
                {isOpen && (
                  <tr className="bg-subtle/60">
                    <td colSpan={7} className="px-3 py-3">
                      {loading === key ? (
                        <div className="flex items-center gap-2 text-xs text-brand-muted">
                          <Loader2 size={14} className="animate-spin" /> Loading materials…
                        </div>
                      ) : mats && mats.length ? (
                        <table className="w-full text-xs">
                          <thead className="text-left text-[10px] uppercase text-brand-muted">
                            <tr>
                              <th className="px-2 py-1">Material</th>
                              <th className="px-2 py-1">UoM</th>
                              <th className="px-2 py-1">Qty</th>
                              <th className="px-2 py-1">Signal</th>
                              <th className="px-2 py-1">Ship Date</th>
                              <th className="px-2 py-1">Overdue</th>
                              <th className="px-2 py-1">Commitment</th>
                            </tr>
                          </thead>
                          <tbody>
                            {mats.map((m) => (
                              <tr key={m.procurement_record_id} className="border-t border-brand-border/60">
                                <td className="px-2 py-1 text-brand-dark">{m.material_name}</td>
                                <td className="px-2 py-1">{m.uom || "—"}</td>
                                <td className="px-2 py-1">{m.qty ?? "—"}</td>
                                <td className="px-2 py-1"><SignalChip signal={m.signal} /></td>
                                <td className="px-2 py-1">{fmtDate(m.shipment_date)}</td>
                                <td className="px-2 py-1">
                                  {overdueDays(m.shipment_date) > 0 ? (
                                    <span className="font-semibold text-signal-red">{overdueDays(m.shipment_date)}d</span>
                                  ) : (
                                    <span className="text-brand-muted">—</span>
                                  )}
                                </td>
                                <td className="px-2 py-1">{fmtDate(m.commitment_date)}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      ) : (
                        <div className="text-xs text-brand-muted">No materials.</div>
                      )}
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

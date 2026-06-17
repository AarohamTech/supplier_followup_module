"use client";

import { useMemo, useState, Fragment } from "react";
import { useStore } from "@/lib/store";
import { fmtDate, fmtNum, signalClass } from "@/lib/format";
import { ChevronDown, ChevronRight, Mail, Sparkles, Loader2 } from "lucide-react";
import type { ProcurementRecord } from "@/lib/types";

const groupHeaders = [
  "",
  "PO",
  "Supplier",
  "Materials",
  "Signal",
  "First ship",
  "Mails",
  "AI",
  "Action",
];

const materialHeaders = [
  "CRM",
  "Material",
  "Shipment",
  "Signal",
  "Qty",
  "Supplier reply",
  "Commitment",
  "Status",
];

const SIGNAL_RANK: Record<string, number> = { GREEN: 1, YELLOW: 2, RED: 3, BLACK: 4 };

interface PoGroup {
  key: string;
  supplier_name: string;
  supplier_po_no: string;
  overall_signal: string;
  earliest_shipment_date?: string | null;
  records: ProcurementRecord[];
  ai_required: boolean;
}

function groupByPo(records: ProcurementRecord[]): PoGroup[] {
  const buckets = new Map<string, PoGroup>();
  for (const rec of records) {
    const supplier = (rec.supplier_name || "-").trim();
    const po = (rec.supplier_po_no || "-").trim();
    const key = `${supplier.toUpperCase()}|${po}`;
    let group = buckets.get(key);
    if (!group) {
      group = {
        key,
        supplier_name: supplier,
        supplier_po_no: po,
        overall_signal: "GREEN",
        earliest_shipment_date: null,
        records: [],
        ai_required: false,
      };
      buckets.set(key, group);
    }
    group.records.push(rec);
    const sig = (rec.signal || "GREEN").toUpperCase();
    if ((SIGNAL_RANK[sig] ?? 1) > (SIGNAL_RANK[group.overall_signal] ?? 1)) {
      group.overall_signal = sig;
    }
    if (rec.ai_required) group.ai_required = true;
    if (rec.shipment_date) {
      if (!group.earliest_shipment_date || rec.shipment_date < group.earliest_shipment_date) {
        group.earliest_shipment_date = rec.shipment_date;
      }
    }
  }
  return Array.from(buckets.values()).sort((a, b) => {
    const ra = SIGNAL_RANK[a.overall_signal] ?? 1;
    const rb = SIGNAL_RANK[b.overall_signal] ?? 1;
    if (rb !== ra) return rb - ra;
    return (a.earliest_shipment_date || "").localeCompare(b.earliest_shipment_date || "");
  });
}

export default function PoTable() {
  const list = useStore((s) => s.list);
  const loading = useStore((s) => s.loading);
  const error = useStore((s) => s.error);
  const filters = useStore((s) => s.filters);
  const setFilters = useStore((s) => s.setFilters);
  const selectPoGroup = useStore((s) => s.selectPoGroup);

  const rows = list?.items ?? [];
  const total = list?.total ?? 0;
  const size = filters.size ?? 25;
  const page = filters.page ?? 1;
  const pages = Math.max(1, Math.ceil(total / size));

  const groups = useMemo(() => groupByPo(rows), [rows]);

  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const toggle = (key: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  return (
    <div className="card overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-brand-border px-4 py-3">
        <div>
          <div className="text-sm font-bold text-brand-dark">PO follow-up list</div>
          <div className="text-xs text-brand-muted">Grouped by supplier and purchase order</div>
        </div>
        <div className="text-xs font-semibold text-brand-muted">
          {loading ? (
            <span className="inline-flex items-center gap-1">
              <Loader2 size={12} className="animate-spin" /> Loading...
            </span>
          ) : (
            `${groups.length} PO groups | ${total} materials`
          )}
        </div>
      </div>

      {error && (
        <div className="border-b border-red-100 bg-red-50 px-4 py-2 text-xs text-signal-red">{error}</div>
      )}

      <div className="overflow-x-auto">
        <table className="data-table min-w-full text-sm">
          <thead>
            <tr>
              {groupHeaders.map((h, i) => (
                <th key={i} className="table-header whitespace-nowrap border-b border-brand-border px-3 py-2.5 text-left">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {groups.length === 0 && !loading && (
              <tr>
                <td colSpan={groupHeaders.length} className="px-4 py-12 text-center text-sm text-brand-muted">
                  No records match the current filters.
                </td>
              </tr>
            )}

            {groups.map((g) => {
              const sig = g.overall_signal;
              const isOpen = expanded.has(g.key);
              const followups = g.records.reduce((acc, r) => acc + (r.followup_count || 0), 0);

              return (
                <Fragment key={g.key}>
                  <tr
                    className="cursor-pointer border-t border-brand-border bg-white/80"
                    onClick={() => toggle(g.key)}
                  >
                    <td className="w-8 px-3 py-3 text-brand-muted">
                      {isOpen ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                    </td>
                    <td className="whitespace-nowrap px-3 py-3 font-bold text-brand-dark">{g.supplier_po_no}</td>
                    <td className="max-w-[280px] px-3 py-3">
                      <div className="truncate font-semibold" title={g.supplier_name}>
                        {g.supplier_name}
                      </div>
                    </td>
                    <td className="whitespace-nowrap px-3 py-3">
                      <span className="chip px-2 py-0.5">{g.records.length} material(s)</span>
                    </td>
                    <td className="px-3 py-3">
                      <span
                        className={
                          "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-bold ring-1 " +
                          (signalClass[sig] ?? "")
                        }
                      >
                        {sig}
                      </span>
                    </td>
                    <td className="whitespace-nowrap px-3 py-3 text-brand-muted">
                      {fmtDate(g.earliest_shipment_date ?? undefined)}
                    </td>
                    <td className="px-3 py-3 text-xs font-semibold text-brand-muted">{followups}</td>
                    <td className="px-3 py-3">
                      {g.ai_required ? (
                        <span className="inline-flex items-center gap-1 rounded-full bg-violet-50 px-2 py-0.5 text-xs font-bold text-violet-700">
                          <Sparkles size={12} /> Required
                        </span>
                      ) : (
                        <span className="text-xs text-brand-muted">-</span>
                      )}
                    </td>
                    <td className="px-3 py-3">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          selectPoGroup({
                            supplier_name: g.supplier_name,
                            supplier_po_no: g.supplier_po_no,
                          });
                        }}
                        className="inline-flex items-center gap-1.5 rounded-md bg-signal-red px-2.5 py-1.5 text-xs font-bold text-white shadow-sm hover:bg-red-700"
                      >
                        <Mail size={12} /> PO Mail
                      </button>
                    </td>
                  </tr>

                  {isOpen && (
                    <tr className="bg-brand-surface/70">
                      <td colSpan={groupHeaders.length} className="px-3 py-3">
                        <div className="overflow-hidden rounded-lg border border-brand-border bg-white">
                          <div className="overflow-x-auto">
                            <table className="data-table min-w-full text-xs">
                              <thead>
                                <tr>
                                  {materialHeaders.map((h) => (
                                    <th
                                      key={h}
                                      className="whitespace-nowrap border-b border-brand-border px-2.5 py-2 text-left font-bold text-brand-muted"
                                    >
                                      {h}
                                    </th>
                                  ))}
                                </tr>
                              </thead>
                              <tbody>
                                {g.records.map((r) => {
                                  const rsig = (r.signal || "").toUpperCase();
                                  return (
                                    <tr key={r.id} className="border-t border-brand-border">
                                      <td className="whitespace-nowrap px-2.5 py-2 font-mono">{r.crm_no}</td>
                                      <td className="max-w-[320px] px-2.5 py-2">
                                        <div className="truncate font-semibold" title={r.material_name}>
                                          {r.material_name}
                                        </div>
                                      </td>
                                      <td className="whitespace-nowrap px-2.5 py-2">{fmtDate(r.shipment_date)}</td>
                                      <td className="px-2.5 py-2">
                                        <span
                                          className={
                                            "inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] font-bold ring-1 " +
                                            (signalClass[rsig] ?? "")
                                          }
                                        >
                                          {rsig || "-"}
                                        </span>
                                      </td>
                                      <td className="whitespace-nowrap px-2.5 py-2">
                                        {fmtNum(r.qty)} {r.uom}
                                      </td>
                                      <td className="max-w-[240px] px-2.5 py-2">
                                        <div className="line-clamp-2 text-brand-muted">
                                          {r.last_supplier_reply ?? "-"}
                                        </div>
                                      </td>
                                      <td className="whitespace-nowrap px-2.5 py-2">{fmtDate(r.commitment_date)}</td>
                                      <td className="whitespace-nowrap px-2.5 py-2">
                                        <div className="font-semibold">{r.po_status ?? "-"}</div>
                                        <div className="text-brand-muted">
                                          {r.followup_status ?? "-"} {r.escalation_level ? `| ${r.escalation_level}` : ""}
                                        </div>
                                      </td>
                                    </tr>
                                  );
                                })}
                              </tbody>
                            </table>
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-brand-border px-4 py-3">
        <span className="text-xs text-brand-muted">
          Showing {rows.length === 0 ? 0 : (page - 1) * size + 1}-{(page - 1) * size + rows.length} of {total} materials
        </span>
        <div className="flex items-center gap-1">
          <button
            disabled={page <= 1}
            onClick={() => setFilters({ page: page - 1 })}
            className="btn-ghost min-h-8 px-2.5 py-1 text-sm disabled:opacity-40"
          >
            Prev
          </button>
          <span className="px-2 text-sm font-semibold text-brand-muted">Page {page} / {pages}</span>
          <button
            disabled={page >= pages}
            onClick={() => setFilters({ page: page + 1 })}
            className="btn-ghost min-h-8 px-2.5 py-1 text-sm disabled:opacity-40"
          >
            Next
          </button>
        </div>
      </div>
    </div>
  );
}

"use client";
import { useMemo, useState, Fragment } from "react";
import { useStore } from "@/lib/store";
import { fmtDate, fmtNum, signalClass, overdueDays } from "@/lib/format";
import { ChevronDown, ChevronRight, Mail, Sparkles, Loader2 } from "lucide-react";
import type { ProcurementRecord } from "@/lib/types";

const baseGroupHeaders = [
  "",
  "Supplier PO No.",
  "Supplier Name",
  "Materials",
  "Overall Signal",
  "Earliest Shipment",
  "Follow-ups",
  "HI Required",
];

const materialHeaders = [
  "CRM No.",
  "Material Name",
  "Shipment Date",
  "Overdue",
  "Signal",
  "PO Status",
  "Qty",
  "Supplier Recent Reply",
  "Last Commitment Date",
  "Follow-up Status",
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
    const supplier = (rec.supplier_name || "—").trim();
    const po = (rec.supplier_po_no || "—").trim();
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

  // Employee scope is read-only: the "PO Mail" manual-queue action opens a modal
  // backed by staff-only endpoints (/api/mail-drafts/generate-po), so hide it.
  const scope = useStore((s) => s.scope);
  const showActions = scope !== "employee";
  const groupHeaders = showActions ? [...baseGroupHeaders, "Action"] : baseGroupHeaders;

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
      <div className="px-4 py-3 border-b border-brand-border flex items-center justify-between">
        <div className="text-sm font-semibold">PO Follow-up List (grouped by Supplier + PO)</div>
        <div className="text-xs text-brand-muted">
          {loading ? (
            <span className="inline-flex items-center gap-1">
              <Loader2 size={12} className="animate-spin" /> Loading...
            </span>
          ) : (
            `${groups.length} PO group(s) · ${total} material row(s)`
          )}
        </div>
      </div>
      {error && (
        <div className="px-4 py-2 text-xs text-signal-red bg-red-50 border-b border-red-100">{error}</div>
      )}
      <div className="overflow-x-auto">
        <table className="min-w-full text-sm border-collapse">
          <thead className="bg-subtle">
            <tr>
              {groupHeaders.map((h, i) => (
                <th key={i} className="text-left px-3 py-2.5 table-header whitespace-nowrap border-b border-brand-border">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {groups.length === 0 && !loading && (
              <tr>
                <td colSpan={groupHeaders.length} className="px-4 py-10 text-center text-brand-muted">
                  No records match the current filters.
                </td>
              </tr>
            )}
            {groups.map((g) => {
              const sig = g.overall_signal;
              const isOpen = expanded.has(g.key);
              return (
                <Fragment key={g.key}>
                  <tr
                    className="border-t border-brand-border bg-card hover:bg-blue-50/40 cursor-pointer"
                    onClick={() => toggle(g.key)}
                  >
                    <td className="px-3 py-2.5 w-8">
                      {isOpen ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                    </td>
                    <td className="px-3 py-2.5 whitespace-nowrap font-semibold">{g.supplier_po_no}</td>
                    <td className="px-3 py-2.5 max-w-[260px]">
                      <div className="font-medium truncate" title={g.supplier_name}>
                        {g.supplier_name}
                      </div>
                    </td>
                    <td className="px-3 py-2.5 whitespace-nowrap">
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-subtle text-brand-dark text-xs font-semibold">
                        {g.records.length} material(s)
                      </span>
                    </td>
                    <td className="px-3 py-2.5">
                      <span
                        className={
                          "inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-xs font-semibold ring-1 " +
                          (signalClass[sig] ?? "")
                        }
                      >
                        {sig}
                      </span>
                    </td>
                    <td className="px-3 py-2.5 whitespace-nowrap">
                      {fmtDate(g.earliest_shipment_date ?? undefined)}
                    </td>
                    <td className="px-3 py-2.5 text-xs text-brand-muted">
                      {g.records.reduce((acc, r) => acc + (r.followup_count || 0), 0)} sent
                    </td>
                    <td className="px-3 py-2.5">
                      {g.ai_required ? (
                        <span className="inline-flex items-center gap-1 text-purple-700 bg-purple-50 px-1.5 py-0.5 rounded text-xs font-semibold">
                          <Sparkles size={12} /> AI
                        </span>
                      ) : (
                        <span className="text-brand-muted text-xs">NO</span>
                      )}
                    </td>
                    {showActions && (
                      <td className="px-3 py-2.5">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            selectPoGroup({
                              supplier_name: g.supplier_name,
                              supplier_po_no: g.supplier_po_no,
                            });
                          }}
                          className="inline-flex items-center gap-1 px-2 py-1 rounded bg-signal-red text-white text-xs font-medium hover:opacity-90"
                        >
                          <Mail size={12} /> PO Mail
                        </button>
                      </td>
                    )}
                  </tr>
                  {isOpen && (
                    <tr className="bg-subtle/60">
                      <td colSpan={groupHeaders.length} className="px-3 py-3">
                        <div className="overflow-x-auto">
                          <table className="min-w-full text-xs border border-brand-border bg-card">
                            <thead className="bg-subtle">
                              <tr>
                                {materialHeaders.map((h, i) => (
                                  <th
                                    key={i}
                                    className="text-left px-2 py-1.5 font-semibold text-brand-dark border-b border-brand-border whitespace-nowrap"
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
                                  <tr key={r.id} className="border-t border-brand-border hover:bg-blue-50/50">
                                    <td className="px-2 py-1.5 whitespace-nowrap font-mono">{r.crm_no}</td>
                                    <td className="px-2 py-1.5 max-w-[280px] truncate" title={r.material_name}>
                                      {r.material_name}
                                    </td>
                                    <td className="px-2 py-1.5 whitespace-nowrap">{fmtDate(r.shipment_date)}</td>
                                    <td className="px-2 py-1.5 whitespace-nowrap">
                                      {overdueDays(r.shipment_date) > 0 ? (
                                        <span className="font-semibold text-signal-red">
                                          {overdueDays(r.shipment_date)}d
                                        </span>
                                      ) : (
                                        <span className="text-brand-muted">—</span>
                                      )}
                                    </td>
                                    <td className="px-2 py-1.5">
                                      <span
                                        className={
                                          "inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold ring-1 " +
                                          (signalClass[rsig] ?? "")
                                        }
                                      >
                                        {rsig || "-"}
                                      </span>
                                    </td>
                                    <td className="px-2 py-1.5 whitespace-nowrap">{r.po_status ?? "-"}</td>
                                    <td className="px-2 py-1.5 whitespace-nowrap">
                                      {fmtNum(r.qty)} {r.uom}
                                    </td>
                                    <td className="px-2 py-1.5 max-w-[200px]">
                                      <div className="line-clamp-2 text-brand-muted">
                                        {r.last_supplier_reply ?? "-"}
                                      </div>
                                    </td>
                                    <td className="px-2 py-1.5 whitespace-nowrap">{fmtDate(r.commitment_date)}</td>
                                    <td className="px-2 py-1.5 whitespace-nowrap">
                                      <div className="font-medium">{r.followup_status}</div>
                                      <div className="text-brand-muted">{r.escalation_level}</div>
                                    </td>
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
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
      <div className="flex items-center justify-between px-4 py-3 border-t border-brand-border">
        <span className="text-xs text-brand-muted">
          Showing {rows.length === 0 ? 0 : (page - 1) * size + 1}-{(page - 1) * size + rows.length} of {total} material rows
        </span>
        <div className="flex items-center gap-1">
          <button
            disabled={page <= 1}
            onClick={() => setFilters({ page: page - 1 })}
            className="px-2.5 py-1 rounded text-sm hover:bg-subtle disabled:opacity-40"
          >
            Prev
          </button>
          <span className="px-2 text-sm">Page {page} / {pages}</span>
          <button
            disabled={page >= pages}
            onClick={() => setFilters({ page: page + 1 })}
            className="px-2.5 py-1 rounded text-sm hover:bg-subtle disabled:opacity-40"
          >
            Next
          </button>
        </div>
      </div>
    </div>
  );
}

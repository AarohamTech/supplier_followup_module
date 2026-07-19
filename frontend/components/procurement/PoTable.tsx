"use client";
import { useEffect, useMemo, useState, Fragment, type ReactNode } from "react";
import { useStore } from "@/lib/store";
import { fmtDate, fmtNum, signalClass, overdueDays } from "@/lib/format";
import { ChevronDown, ChevronRight, Mail, Sparkles, Loader2, SlidersHorizontal } from "lucide-react";
import type { ProcurementRecord } from "@/lib/types";
import PoPdfButton from "@/components/po/PoPdfButton";

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

// Detail (per-material) columns. `on` marks the default-visible set — the full
// list the user asked for; CRM No. / PO Status / Follow-up are opt-in extras.
// Visibility is user-toggleable and persisted to localStorage.
interface DetailColumn {
  key: string;
  label: string;
  on: boolean;
  render: (r: ProcurementRecord) => ReactNode;
}

const DETAIL_COLUMNS: DetailColumn[] = [
  { key: "customer", label: "Customer", on: true,
    render: (r) => <span className="max-w-[180px] truncate inline-block align-bottom" title={r.customer_name ?? ""}>{r.customer_name ?? "—"}</span> },
  { key: "customer_po", label: "Customer PO", on: true,
    render: (r) => <span className="font-mono">{r.po_no ?? "—"}</span> },
  { key: "po_date", label: "PO Date", on: true, render: (r) => fmtDate(r.po_date) },
  { key: "material", label: "Material Name", on: true,
    render: (r) => <span className="max-w-[280px] truncate inline-block align-bottom" title={r.material_name}>{r.material_name}</span> },
  { key: "signal", label: "Signal", on: true, render: (r) => <SignalBadge signal={r.signal} /> },
  { key: "qty", label: "Qty", on: true, render: (r) => <>{fmtNum(r.qty)} {r.uom}</> },
  { key: "supplier_po", label: "Supplier PO", on: true,
    render: (r) => (
      <span className="inline-flex items-center gap-1">
        <span className="font-mono">{r.supplier_po_no}</span>
        <ScopedPoPdfButton trnNo={r.po_trn_no} fileLabel={r.po_short_ref || r.supplier_po_no} />
      </span>
    ) },
  { key: "supplier_po_date", label: "Supplier PO Date", on: true, render: (r) => fmtDate(r.supplier_date) },
  { key: "stock", label: "Stock", on: true, render: (r) => fmtNum(r.stock) },
  { key: "ship_date", label: "Ship Date", on: true, render: (r) => fmtDate(r.shipment_date) },
  { key: "overdue", label: "Overdue", on: true,
    render: (r) => overdueDays(r.shipment_date) > 0
      ? <span className="font-semibold text-signal-red">{overdueDays(r.shipment_date)}d</span>
      : <span className="text-brand-muted">—</span> },
  { key: "commitment", label: "Commitment", on: true, render: (r) => fmtDate(r.commitment_date) },
  { key: "remark", label: "Supplier Remark", on: true,
    render: (r) => <span className="line-clamp-2 max-w-[220px] text-brand-muted">{r.last_supplier_reply ?? "—"}</span> },
  // ── opt-in extras: every remaining field the API returns ────────────────────
  { key: "crm", label: "CRM No.", on: false, render: (r) => <span className="font-mono">{r.crm_no}</span> },
  { key: "po_ref", label: "PO Ref (doc no.)", on: false,
    render: (r) => <span className="font-mono">{r.po_short_ref ?? "—"}</span> },
  { key: "po_status", label: "PO Status", on: false, render: (r) => r.po_status ?? "—" },
  { key: "uom", label: "UoM", on: false, render: (r) => r.uom ?? "—" },
  { key: "rate", label: "Rate", on: false, render: (r) => fmtNum(r.rate) },
  { key: "lead_time", label: "Lead Time", on: false,
    render: (r) => (r.lead_time != null ? `${r.lead_time}d` : "—") },
  { key: "confirmed_qty", label: "Confirmed Qty", on: false, render: (r) => fmtNum(r.quantity) },
  { key: "adv_status", label: "Adv Status", on: false, render: (r) => r.adv_status ?? "—" },
  { key: "ordered_qty", label: "Ordered Qty", on: false, render: (r) => fmtNum(r.po_qty) },
  { key: "grn_qty", label: "Recd (GRN)", on: false, render: (r) => fmtNum(r.grn_qty) },
  { key: "pending_qty", label: "Pending Qty", on: false, render: (r) => fmtNum(r.pending_qty) },
  { key: "receipt", label: "Receipt", on: false, render: (r) => <ReceiptBadge status={r.receipt_status} /> },
  { key: "followup", label: "Follow-up", on: false,
    render: (r) => (<><div className="font-medium">{r.followup_status}</div><div className="text-brand-muted">{r.escalation_level}</div></>) },
  { key: "mail_status", label: "Mail Status", on: false, render: (r) => r.mail_status ?? "—" },
  { key: "followup_count", label: "Follow-ups Sent", on: false, render: (r) => r.followup_count ?? 0 },
  { key: "last_followup", label: "Last Follow-up", on: false, render: (r) => fmtDate(r.last_followup_date) },
  { key: "next_followup", label: "Next Follow-up", on: false, render: (r) => fmtDate(r.next_followup_date) },
  { key: "delay_reason", label: "Delay Reason", on: false,
    render: (r) => <span className="line-clamp-2 max-w-[220px] text-brand-muted">{r.delay_reason ?? "—"}</span> },
  { key: "po_remark", label: "PO Remark", on: false,
    render: (r) => <span className="line-clamp-2 max-w-[220px] text-brand-muted">{r.po_remark ?? "—"}</span> },
  { key: "updated", label: "Last Updated", on: false, render: (r) => fmtDate(r.updated_at) },
];

const COLS_STORAGE_KEY = "po-detail-cols";

function SignalBadge({ signal }: { signal?: string | null }) {
  const s = (signal || "").toUpperCase();
  return (
    <span className={"inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold ring-1 " + (signalClass[s] ?? "")}>
      {s || "-"}
    </span>
  );
}

// Receipt progress (GRN quantities from the CRM): green when fully received.
function ReceiptBadge({ status }: { status?: string | null }) {
  const s = (status || "").toUpperCase();
  if (!s) return <span className="text-brand-muted">—</span>;
  const cls =
    s === "COMPLETED"
      ? "bg-emerald-50 text-emerald-700 ring-emerald-100"
      : s === "PARTIAL"
        ? "bg-blue-50 text-blue-700 ring-blue-100"
        : "bg-subtle text-brand-muted ring-gray-200";
  const label = s === "COMPLETED" ? "Received" : s === "PARTIAL" ? "Partly recd" : "Awaiting";
  return (
    <span className={`inline-flex rounded-full px-1.5 py-0.5 text-[10px] font-semibold uppercase ring-1 ring-inset ${cls}`}>
      {label}
    </span>
  );
}

// The PO PDF proxy differs by user type; the store scope knows which one we are.
function ScopedPoPdfButton({ trnNo, fileLabel }: { trnNo?: string | null; fileLabel: string }) {
  const scope = useStore((s) => s.scope);
  return (
    <PoPdfButton
      trnNo={trnNo}
      fileLabel={fileLabel}
      endpoint={scope === "employee" ? "/api/eportal/po-pdf" : "/api/procurement/po-pdf"}
    />
  );
}

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

  // Detail column visibility (persisted). Default = every column's `on` flag.
  const [visibleCols, setVisibleCols] = useState<Set<string>>(
    () => new Set(DETAIL_COLUMNS.filter((c) => c.on).map((c) => c.key)),
  );
  const [colMenuOpen, setColMenuOpen] = useState(false);
  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(COLS_STORAGE_KEY);
      if (saved) setVisibleCols(new Set(JSON.parse(saved) as string[]));
    } catch {
      /* ignore */
    }
  }, []);
  const toggleCol = (key: string) =>
    setVisibleCols((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      try {
        window.localStorage.setItem(COLS_STORAGE_KEY, JSON.stringify([...next]));
      } catch {
        /* ignore */
      }
      return next;
    });
  const activeCols = useMemo(
    () => DETAIL_COLUMNS.filter((c) => visibleCols.has(c.key)),
    [visibleCols],
  );

  return (
    <div className="card overflow-hidden">
      <div className="px-4 py-3 border-b border-brand-border flex items-center justify-between gap-2">
        <div className="text-sm font-semibold">PO Follow-up List (grouped by Supplier + PO)</div>
        <div className="flex items-center gap-3">
          <div className="text-xs text-brand-muted">
            {loading ? (
              <span className="inline-flex items-center gap-1">
                <Loader2 size={12} className="animate-spin" /> Loading...
              </span>
            ) : (
              `${groups.length} PO group(s) · ${total} material row(s)`
            )}
          </div>
          <div className="relative">
            <button
              onClick={() => setColMenuOpen((v) => !v)}
              className="inline-flex items-center gap-1.5 rounded-md border border-brand-border px-2.5 py-1 text-xs font-medium text-brand-dark hover:bg-subtle"
              title="Show / hide detail columns"
            >
              <SlidersHorizontal size={13} /> Columns
            </button>
            {colMenuOpen && (
              <>
                <div className="fixed inset-0 z-10" onClick={() => setColMenuOpen(false)} aria-hidden />
                <div className="absolute right-0 z-20 mt-1 w-56 rounded-md border border-brand-border bg-card p-2 shadow-lg">
                  <div className="mb-1 px-1 text-[10px] font-semibold uppercase tracking-wider text-brand-muted">
                    Detail columns
                  </div>
                  <div className="max-h-72 overflow-y-auto">
                    {DETAIL_COLUMNS.map((c) => (
                      <label
                        key={c.key}
                        className="flex cursor-pointer items-center gap-2 rounded px-1.5 py-1 text-xs hover:bg-subtle"
                      >
                        <input
                          type="checkbox"
                          checked={visibleCols.has(c.key)}
                          onChange={() => toggleCol(c.key)}
                          className="accent-signal-red"
                        />
                        {c.label}
                      </label>
                    ))}
                  </div>
                </div>
              </>
            )}
          </div>
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
                                {activeCols.map((c) => (
                                  <th
                                    key={c.key}
                                    className="text-left px-2 py-1.5 font-semibold text-brand-dark border-b border-brand-border whitespace-nowrap"
                                  >
                                    {c.label}
                                  </th>
                                ))}
                              </tr>
                            </thead>
                            <tbody>
                              {g.records.map((r) => (
                                <tr key={r.id} className="border-t border-brand-border hover:bg-blue-50/50">
                                  {activeCols.map((c) => (
                                    <td key={c.key} className="px-2 py-1.5 align-top">
                                      {c.render(r)}
                                    </td>
                                  ))}
                                </tr>
                              ))}
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

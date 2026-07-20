"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Ban, ClipboardList, Columns3, Loader2 } from "lucide-react";

import { api } from "@/lib/api";
import type { OrderLine } from "@/lib/types";
import Pager from "@/components/ui/Pager";

const SIZE = 50;
// v2: Rate became default-visible (client: "we not showing rates anywhere").
const COLS_KEY = "eportal.orders.visibleCols.v2";

const SIGNAL_CLASS: Record<string, string> = {
  GREEN: "bg-emerald-50 text-emerald-700 ring-emerald-100",
  YELLOW: "bg-amber-50 text-amber-700 ring-amber-100",
  RED: "bg-red-50 text-signal-red ring-red-100",
  BLACK: "bg-ink text-white ring-gray-700",
};

function SignalChip({ signal }: { signal?: string | null }) {
  const s = (signal || "").toUpperCase();
  if (!s) return <span className="text-brand-muted">—</span>;
  const cls = SIGNAL_CLASS[s] || "bg-subtle text-brand-muted ring-gray-200";
  return (
    <span className={`inline-flex rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase ring-1 ring-inset ${cls}`}>
      {s}
    </span>
  );
}

function ReceiptChip({ status }: { status?: string | null }) {
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

function fmtDate(d?: string | null) {
  if (!d) return "—";
  const dt = new Date(d);
  return isNaN(dt.getTime()) ? "—" : dt.toLocaleDateString();
}

// Same column registry as the admin Orders page, minus Owner (it's always you).
// No PO-PDF download here — the official PO document is admin/supplier-only.
const COLUMNS: { key: string; label: string; on: boolean }[] = [
  { key: "customer", label: "Customer", on: true },
  { key: "customer_po", label: "Customer PO", on: true },
  { key: "material", label: "Material", on: true },
  { key: "qty", label: "Qty", on: true },
  { key: "vendor_po", label: "Vendor PO No.", on: true },
  { key: "po_date", label: "PO Date", on: true },
  { key: "vendor", label: "Vendor", on: true },
  { key: "stock", label: "Stock", on: true },
  { key: "signal", label: "Signal", on: true },
  { key: "status", label: "Status", on: true },
  { key: "ship_date", label: "Ship Date", on: true },
  { key: "commitment", label: "Commitment", on: true },
  { key: "remark", label: "Customer Remark", on: true },
  { key: "supplier_remark", label: "Supplier Remark", on: true },
  { key: "crm", label: "CRM No.", on: false },
  { key: "rate", label: "Rate", on: true },
  { key: "lead_time", label: "Lead Time", on: false },
  { key: "ordered_qty", label: "Ordered Qty", on: false },
  { key: "grn_qty", label: "Recd (GRN)", on: false },
  { key: "pending_qty", label: "Pending Qty", on: false },
  { key: "receipt", label: "Receipt", on: false },
  { key: "escalation", label: "Escalation", on: false },
];

const SIGNALS = ["", "GREEN", "YELLOW", "RED", "BLACK"];
const STATUSES = ["", "APPROVED", "NOT APPROVED", "NOT GENERATED"];

/** Employee "My Orders" — the admin Orders experience, server-scoped to the
 *  logged-in employee's own PO lines. */
export default function EmployeeOrdersPage() {
  const [rows, setRows] = useState<OrderLine[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [signal, setSignal] = useState("");
  const [poStatus, setPoStatus] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [includeClosed, setIncludeClosed] = useState(false);

  const [visibleCols, setVisibleCols] = useState<Set<string>>(
    () => new Set(COLUMNS.filter((c) => c.on).map((c) => c.key)),
  );
  const [colMenuOpen, setColMenuOpen] = useState(false);
  const colMenuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(COLS_KEY);
      if (saved) setVisibleCols(new Set(JSON.parse(saved) as string[]));
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (colMenuRef.current && !colMenuRef.current.contains(e.target as Node)) setColMenuOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  function toggleCol(key: string) {
    setVisibleCols((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      try { window.localStorage.setItem(COLS_KEY, JSON.stringify(Array.from(next))); } catch { /* ignore */ }
      return next;
    });
  }
  const show = (key: string) => visibleCols.has(key);

  const [confirmLine, setConfirmLine] = useState<OrderLine | null>(null);
  const [remark, setRemark] = useState("");
  const [requesting, setRequesting] = useState(false);
  const [cancelError, setCancelError] = useState<string | null>(null);
  const [cancelOverride, setCancelOverride] = useState<Record<number, string>>({});

  useEffect(() => {
    const t = setTimeout(() => { setDebounced(search.trim()); setPage(1); }, 300);
    return () => clearTimeout(t);
  }, [search]);

  useEffect(() => setPage(1), [signal, poStatus, dateFrom, dateTo, includeClosed]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.eportalOrders({
        search: debounced || undefined,
        signal: signal || undefined,
        po_status: poStatus || undefined,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
        include_closed: includeClosed || undefined,
        page,
        size: SIZE,
      });
      setRows(r.items);
      setTotal(r.total);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [debounced, signal, poStatus, dateFrom, dateTo, includeClosed, page]);

  useEffect(() => { void load(); }, [load]);

  async function confirmCancel() {
    if (!confirmLine) return;
    setRequesting(true);
    setCancelError(null);
    try {
      await api.eportalOrderLineCancel(confirmLine.procurement_record_id, remark.trim());
      setCancelOverride((cur) => ({ ...cur, [confirmLine.procurement_record_id]: "PENDING" }));
      setConfirmLine(null);
      setRemark("");
    } catch (e) {
      setCancelError((e as Error).message);
    } finally {
      setRequesting(false);
    }
  }

  const cancelStatusOf = (r: OrderLine) =>
    (cancelOverride[r.procurement_record_id] ?? r.cancellation_status ?? "").toUpperCase();

  const visibleCount = COLUMNS.filter((c) => show(c.key)).length + 1; // + Cancel

  return (
    <div className="page-stack">
      <div className="page-header">
        <div>
          <h1 className="page-title">My Orders</h1>
          <p className="page-subtitle">Every PO line assigned to you, material-wise — live from the CRM.</p>
        </div>
        <span className="grid h-9 w-9 place-items-center rounded-lg bg-red-50 text-signal-red"><ClipboardList size={17} /></span>
      </div>
      {error && <div className="card p-3 text-xs text-signal-red">{error}</div>}

      <div className="card flex flex-wrap items-center gap-2 p-3">
        <input
          className="border border-brand-border rounded px-3 py-2 text-sm w-full max-w-xs"
          placeholder="Search PO / vendor / material / customer / CRM…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <select className="border border-brand-border rounded px-2 py-2 text-sm bg-card" value={signal} onChange={(e) => setSignal(e.target.value)}>
          {SIGNALS.map((s) => <option key={s} value={s}>{s || "All signals"}</option>)}
        </select>
        <select className="border border-brand-border rounded px-2 py-2 text-sm bg-card" value={poStatus} onChange={(e) => setPoStatus(e.target.value)}>
          {STATUSES.map((s) => <option key={s} value={s}>{s || "All statuses"}</option>)}
        </select>
        <label className="flex items-center gap-1 text-xs text-brand-muted">
          Ship from
          <input type="date" className="border border-brand-border rounded px-2 py-1.5 text-sm" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
        </label>
        <label className="flex items-center gap-1 text-xs text-brand-muted">
          to
          <input type="date" className="border border-brand-border rounded px-2 py-1.5 text-sm" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
        </label>
        <label className="flex items-center gap-1.5 text-xs text-brand-muted">
          <input type="checkbox" checked={includeClosed} onChange={(e) => setIncludeClosed(e.target.checked)} />
          Include closed
        </label>

        <div className="relative ml-auto" ref={colMenuRef}>
          <button type="button" onClick={() => setColMenuOpen((v) => !v)} className="btn-outline text-xs inline-flex items-center gap-1">
            <Columns3 size={13} /> Columns
          </button>
          {colMenuOpen && (
            <div className="absolute right-0 z-40 mt-1 w-48 rounded-md border border-brand-border bg-card p-2 shadow-xl">
              {COLUMNS.map((c) => (
                <label key={c.key} className="flex items-center gap-2 rounded px-2 py-1 text-xs hover:bg-subtle cursor-pointer">
                  <input type="checkbox" checked={show(c.key)} onChange={() => toggleCol(c.key)} />
                  {c.label}
                </label>
              ))}
            </div>
          )}
        </div>
      </div>

      {loading ? (
        <div className="card p-6 text-center text-sm text-brand-muted">
          <Loader2 className="inline animate-spin" size={16} /> Loading…
        </div>
      ) : (
        <>
          <div className="card overflow-x-auto">
            <table className="w-full min-w-[1080px] text-xs">
              <thead className="bg-subtle text-left text-[10px] uppercase tracking-wider text-brand-muted">
                <tr>
                  {show("customer") && <th className="px-3 py-2">Customer</th>}
                  {show("customer_po") && <th className="px-3 py-2">Customer PO</th>}
                  {show("material") && <th className="px-3 py-2">Material</th>}
                  {show("qty") && <th className="px-3 py-2 text-right">Qty</th>}
                  {show("vendor_po") && <th className="px-3 py-2">Vendor PO No.</th>}
                  {show("po_date") && <th className="px-3 py-2 text-right">PO Date</th>}
                  {show("vendor") && <th className="px-3 py-2">Vendor</th>}
                  {show("stock") && <th className="px-3 py-2 text-right">Stock</th>}
                  {show("signal") && <th className="px-3 py-2">Signal</th>}
                  {show("status") && <th className="px-3 py-2">Status</th>}
                  {show("ship_date") && <th className="px-3 py-2 text-right">Ship Date</th>}
                  {show("commitment") && <th className="px-3 py-2 text-right">Commitment</th>}
                  {show("remark") && <th className="px-3 py-2">Customer Remark</th>}
                  {show("supplier_remark") && <th className="px-3 py-2">Supplier Remark</th>}
                  {show("crm") && <th className="px-3 py-2">CRM No.</th>}
                  {show("rate") && <th className="px-3 py-2 text-right">Rate</th>}
                  {show("lead_time") && <th className="px-3 py-2 text-right">Lead Time</th>}
                  {show("ordered_qty") && <th className="px-3 py-2 text-right">Ordered Qty</th>}
                  {show("grn_qty") && <th className="px-3 py-2 text-right">Recd (GRN)</th>}
                  {show("pending_qty") && <th className="px-3 py-2 text-right">Pending Qty</th>}
                  {show("receipt") && <th className="px-3 py-2">Receipt</th>}
                  {show("escalation") && <th className="px-3 py-2">Escalation</th>}
                  <th className="px-3 py-2 text-right">Cancel</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-brand-border">
                {rows.length === 0 && (
                  <tr><td colSpan={visibleCount} className="px-4 py-8 text-center text-brand-muted">No order lines found.</td></tr>
                )}
                {rows.map((r) => (
                  <tr key={r.procurement_record_id} className={`hover:bg-subtle/50 ${r.closed ? "opacity-60" : ""}`}>
                    {show("customer") && (
                      <td className="max-w-[170px] px-3 py-2">
                        {r.customer_name ? (
                          <div className="truncate text-brand-dark" title={r.customer_name}>{r.customer_name}</div>
                        ) : (
                          <span className="inline-flex rounded bg-violet-50 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-violet-700 ring-1 ring-inset ring-violet-100">
                            Direct PO
                          </span>
                        )}
                      </td>
                    )}
                    {show("customer_po") && (
                      <td className="max-w-[140px] px-3 py-2">
                        <div className="truncate" title={r.customer_po_no || undefined}>{r.customer_po_no || "—"}</div>
                        {r.customer_po_date && <div className="text-[10px] text-brand-muted">{fmtDate(r.customer_po_date)}</div>}
                      </td>
                    )}
                    {show("material") && (
                      <td className="max-w-[240px] px-3 py-2">
                        <div className="truncate text-brand-dark" title={r.material_name}>{r.material_name}</div>
                      </td>
                    )}
                    {show("qty") && (
                      <td className="px-3 py-2 text-right tabular-nums">
                        {r.qty != null ? `${r.qty.toLocaleString()}${r.uom ? ` ${r.uom}` : ""}` : "—"}
                      </td>
                    )}
                    {show("vendor_po") && (
                      <td className="px-3 py-2 whitespace-nowrap">
                        <span className="font-medium text-brand-dark">{r.po_short_ref || r.supplier_po_no}</span>
                        {r.po_short_ref && <div className="text-[10px] text-brand-muted">#{r.supplier_po_no}</div>}
                      </td>
                    )}
                    {show("po_date") && <td className="px-3 py-2 text-right">{fmtDate(r.supplier_date)}</td>}
                    {show("vendor") && (
                      <td className="max-w-[170px] px-3 py-2">
                        <div className="truncate text-brand-dark" title={r.supplier_name || undefined}>{r.supplier_name || "—"}</div>
                      </td>
                    )}
                    {show("stock") && <td className="px-3 py-2 text-right tabular-nums">{r.stock != null ? r.stock.toLocaleString() : "—"}</td>}
                    {show("signal") && <td className="px-3 py-2"><SignalChip signal={r.signal} /></td>}
                    {show("status") && (
                      <td className="px-3 py-2 whitespace-nowrap">
                        {r.po_status || "—"}
                        {r.closed && (
                          <span className="ml-1.5 inline-flex rounded bg-subtle px-1.5 py-0.5 text-[10px] font-semibold uppercase text-brand-muted ring-1 ring-inset ring-gray-200">Closed</span>
                        )}
                      </td>
                    )}
                    {show("ship_date") && <td className="px-3 py-2 text-right">{fmtDate(r.shipment_date)}</td>}
                    {show("commitment") && <td className="px-3 py-2 text-right">{fmtDate(r.commitment_date)}</td>}
                    {show("remark") && (
                      <td className="max-w-[180px] px-3 py-2">
                        <div className="truncate" title={r.po_remark || undefined}>{r.po_remark || "—"}</div>
                      </td>
                    )}
                    {show("supplier_remark") && (
                      <td className="max-w-[180px] px-3 py-2">
                        <div className="truncate" title={r.last_supplier_reply || undefined}>{r.last_supplier_reply || "—"}</div>
                      </td>
                    )}
                    {show("crm") && <td className="px-3 py-2 whitespace-nowrap font-mono">{r.crm_no || "—"}</td>}
                    {show("rate") && <td className="px-3 py-2 text-right tabular-nums">{r.rate != null ? r.rate.toLocaleString() : "—"}</td>}
                    {show("lead_time") && <td className="px-3 py-2 text-right tabular-nums">{r.lead_time != null ? `${r.lead_time}d` : "—"}</td>}
                    {show("ordered_qty") && <td className="px-3 py-2 text-right tabular-nums">{r.po_qty != null ? r.po_qty.toLocaleString() : "—"}</td>}
                    {show("grn_qty") && <td className="px-3 py-2 text-right tabular-nums">{r.grn_qty != null ? r.grn_qty.toLocaleString() : "—"}</td>}
                    {show("pending_qty") && <td className="px-3 py-2 text-right tabular-nums">{r.pending_qty != null ? r.pending_qty.toLocaleString() : "—"}</td>}
                    {show("receipt") && <td className="px-3 py-2"><ReceiptChip status={r.receipt_status} /></td>}
                    {show("escalation") && <td className="px-3 py-2 whitespace-nowrap">{r.escalation_level || "—"}</td>}
                    <td className="px-3 py-2 text-right">
                      {r.closed ? (
                        <span className="text-brand-muted">—</span>
                      ) : cancelStatusOf(r) === "CANCELLED" ? (
                        <span className="inline-flex rounded-full bg-red-50 px-2 py-0.5 text-[10px] font-semibold uppercase text-signal-red ring-1 ring-inset ring-red-100">Cancelled</span>
                      ) : cancelStatusOf(r) === "PENDING" ? (
                        <span className="inline-flex rounded-full bg-amber-50 px-2 py-0.5 text-[10px] font-semibold uppercase text-amber-700 ring-1 ring-inset ring-amber-100">Pending cancellation</span>
                      ) : (
                        <button
                          type="button"
                          onClick={() => { setConfirmLine(r); setRemark(""); setCancelError(null); }}
                          className="inline-flex items-center gap-1 rounded-md border border-brand-border px-2 py-1 text-[11px] font-medium text-signal-red hover:bg-red-50"
                        >
                          <Ban size={12} /> Cancel
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pager page={page} size={SIZE} total={total} onPage={setPage} unit="lines" />
        </>
      )}

      {confirmLine && (
        <div className="fixed inset-0 z-50 bg-black/40 grid place-items-center p-4" onClick={() => !requesting && setConfirmLine(null)}>
          <div className="bg-card rounded-lg shadow-xl w-full max-w-sm" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
            <div className="border-b border-brand-border px-5 py-3 font-semibold text-sm">Cancel material</div>
            <div className="px-5 py-4 space-y-2 text-sm">
              <p>
                Request cancellation for <span className="font-semibold">{confirmLine.material_name}</span> on PO{" "}
                <span className="font-semibold">{confirmLine.po_short_ref || confirmLine.supplier_po_no}</span>
                {confirmLine.supplier_name ? <> ({confirmLine.supplier_name})</> : null}?
              </p>
              <p className="text-xs text-brand-muted">
                Only this material line is marked <span className="font-medium">Pending cancellation</span> until the ERP confirms.
              </p>
              <label className="block text-sm">
                <span className="text-xs text-brand-muted">Remark (reason — sent to the ERP)</span>
                <textarea
                  className="mt-1 w-full rounded-md border border-brand-border px-3 py-2 text-sm outline-none focus:border-signal-red"
                  rows={3}
                  maxLength={500}
                  value={remark}
                  onChange={(e) => setRemark(e.target.value)}
                  placeholder="e.g. Material no longer required / duplicate order"
                />
              </label>
              {cancelError && <p className="text-xs text-signal-red">{cancelError}</p>}
            </div>
            <div className="border-t border-brand-border px-5 py-3 flex items-center justify-end gap-2">
              <button type="button" disabled={requesting} onClick={() => setConfirmLine(null)} className="btn-outline text-xs">Back</button>
              <button
                type="button"
                disabled={requesting}
                onClick={confirmCancel}
                className="inline-flex items-center gap-1 rounded-md bg-signal-red px-3 py-1.5 text-xs font-semibold text-white hover:opacity-90 disabled:opacity-60"
              >
                {requesting ? <Loader2 size={13} className="animate-spin" /> : <Ban size={13} />}
                {requesting ? "Requesting…" : "Yes, request cancellation"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

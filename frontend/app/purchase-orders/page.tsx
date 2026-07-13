"use client";

import { useCallback, useEffect, useState } from "react";
import { Ban, ClipboardList, Loader2 } from "lucide-react";

import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { OrderLine } from "@/lib/types";
import PageHeader from "@/components/layout/PageHeader";
import Pager from "@/components/ui/Pager";

const SIZE = 50;

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

function fmtDate(d?: string | null) {
  if (!d) return "—";
  const dt = new Date(d);
  return isNaN(dt.getTime()) ? "—" : dt.toLocaleDateString();
}

export default function OrdersPage() {
  const { hasRole } = useAuth();
  const isAdmin = hasRole("admin");

  const [rows, setRows] = useState<OrderLine[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [owners, setOwners] = useState<{ emp_code: string; name: string }[]>([]);
  const [owner, setOwner] = useState("");
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Cancel dialog state (material-wise, with remark).
  const [confirmLine, setConfirmLine] = useState<OrderLine | null>(null);
  const [remark, setRemark] = useState("");
  const [requesting, setRequesting] = useState(false);
  const [cancelError, setCancelError] = useState<string | null>(null);
  const [cancelOverride, setCancelOverride] = useState<Record<number, string>>({});

  useEffect(() => {
    if (isAdmin) {
      api.poViewLineOwners().then((r) => setOwners(r.owners)).catch(() => {});
    }
  }, [isAdmin]);

  useEffect(() => {
    const t = setTimeout(() => {
      setDebounced(search.trim());
      setPage(1);
    }, 300);
    return () => clearTimeout(t);
  }, [search]);

  useEffect(() => setPage(1), [owner]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.poViewLines({
        search: debounced || undefined,
        owner: owner || undefined,
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
  }, [debounced, owner, page]);

  useEffect(() => {
    if (isAdmin) void load();
    else setLoading(false);
  }, [isAdmin, load]);

  async function confirmCancel() {
    if (!confirmLine) return;
    setRequesting(true);
    setCancelError(null);
    try {
      await api.poViewLineCancel(confirmLine.procurement_record_id, remark.trim());
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

  if (!isAdmin) {
    return (
      <div className="page-stack">
        <PageHeader title="Orders" description="All purchase order lines." icon={ClipboardList} />
        <div className="card p-4 text-sm text-brand-muted">This page is available to administrators only.</div>
      </div>
    );
  }

  return (
    <div className="page-stack">
      <PageHeader
        title="Orders"
        description="Every PO line, material-wise — customer, quantities and per-material cancellation."
        icon={ClipboardList}
      />
      {error && <div className="card p-3 text-xs text-signal-red">{error}</div>}

      <div className="card flex flex-wrap items-center gap-3 p-3">
        <input
          className="border border-brand-border rounded px-3 py-2 text-sm w-full max-w-sm"
          placeholder="Search PO / vendor / material / customer / CRM…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <select
          className="border border-brand-border rounded px-2 py-2 text-sm bg-card"
          value={owner}
          onChange={(e) => setOwner(e.target.value)}
        >
          <option value="">All users</option>
          {owners.map((o) => (
            <option key={o.emp_code} value={o.emp_code}>{o.name}</option>
          ))}
        </select>
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
                  <th className="px-3 py-2">PO No.</th>
                  <th className="px-3 py-2">Vendor</th>
                  <th className="px-3 py-2">Customer</th>
                  <th className="px-3 py-2">Customer PO</th>
                  <th className="px-3 py-2">Material</th>
                  <th className="px-3 py-2 text-right">Qty</th>
                  <th className="px-3 py-2 text-right">Stock</th>
                  <th className="px-3 py-2">Signal</th>
                  <th className="px-3 py-2">Status</th>
                  <th className="px-3 py-2 text-right">PO date</th>
                  <th className="px-3 py-2 text-right">Ship date</th>
                  <th className="px-3 py-2">Owner</th>
                  <th className="px-3 py-2 text-right">Cancel</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-brand-border">
                {rows.length === 0 && (
                  <tr><td colSpan={13} className="px-4 py-8 text-center text-brand-muted">No order lines found.</td></tr>
                )}
                {rows.map((r) => (
                  <tr key={r.procurement_record_id} className="hover:bg-subtle/50">
                    <td className="px-3 py-2 whitespace-nowrap">
                      <div className="font-medium text-brand-dark">{r.po_short_ref || r.supplier_po_no}</div>
                      {r.po_short_ref && <div className="text-[10px] text-brand-muted">#{r.supplier_po_no}</div>}
                    </td>
                    <td className="max-w-[170px] px-3 py-2">
                      <div className="truncate text-brand-dark" title={r.supplier_name || undefined}>{r.supplier_name || "—"}</div>
                    </td>
                    <td className="max-w-[170px] px-3 py-2">
                      {r.customer_name ? (
                        <div className="truncate text-brand-dark" title={r.customer_name}>{r.customer_name}</div>
                      ) : (
                        <span className="inline-flex rounded bg-violet-50 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-violet-700 ring-1 ring-inset ring-violet-100">
                          Direct PO
                        </span>
                      )}
                    </td>
                    <td className="max-w-[140px] px-3 py-2">
                      <div className="truncate" title={r.customer_po_no || undefined}>{r.customer_po_no || "—"}</div>
                      {r.customer_po_date && <div className="text-[10px] text-brand-muted">{fmtDate(r.customer_po_date)}</div>}
                    </td>
                    <td className="max-w-[240px] px-3 py-2">
                      <div className="truncate text-brand-dark" title={r.material_name}>{r.material_name}</div>
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">
                      {r.qty != null ? `${r.qty.toLocaleString()}${r.uom ? ` ${r.uom}` : ""}` : "—"}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">{r.stock != null ? r.stock.toLocaleString() : "—"}</td>
                    <td className="px-3 py-2"><SignalChip signal={r.signal} /></td>
                    <td className="px-3 py-2">{r.po_status || "—"}</td>
                    <td className="px-3 py-2 text-right">{fmtDate(r.supplier_date)}</td>
                    <td className="px-3 py-2 text-right">{fmtDate(r.shipment_date)}</td>
                    <td className="px-3 py-2 whitespace-nowrap">{r.owner_emp_code || "—"}</td>
                    <td className="px-3 py-2 text-right">
                      {cancelStatusOf(r) === "CANCELLED" ? (
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

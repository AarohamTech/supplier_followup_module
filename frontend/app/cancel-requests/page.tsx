"use client";

import { useEffect, useMemo, useState } from "react";
import { Ban, Loader2 } from "lucide-react";

import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { PoCancelRequestRow } from "@/lib/types";
import PageHeader from "@/components/layout/PageHeader";
import { ExportButton } from "@/components/reports/WorkloadShared";

const STATUS_TABS = ["", "PENDING", "CANCELLED"];

function fmtDateTime(d?: string | null) {
  if (!d) return "—";
  const dt = new Date(d);
  return isNaN(dt.getTime()) ? "—" : dt.toLocaleString();
}

/** Admin-only register of every PO cancellation request, with reason + export. */
export default function CancelRequestsPage() {
  const { hasRole } = useAuth();
  const isAdmin = hasRole("admin");
  const [rows, setRows] = useState<PoCancelRequestRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState("");
  const [search, setSearch] = useState("");

  useEffect(() => {
    if (!isAdmin) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    api
      .poViewCancelRequests()
      .then((r) => !cancelled && setRows(r.items))
      .catch((e) => !cancelled && setError((e as Error).message))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [isAdmin]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return rows.filter((r) => {
      if (status && (r.cancellation_status || "").toUpperCase() !== status) return false;
      if (!q) return true;
      return `${r.supplier_po_no ?? ""} ${r.po_short_ref ?? ""} ${r.supplier_name ?? ""} ${r.material_name} ${r.customer_name ?? ""} ${r.cancel_requested_by ?? ""}`
        .toLowerCase()
        .includes(q);
    });
  }, [rows, status, search]);

  if (!isAdmin) {
    return (
      <div className="page-stack">
        <PageHeader title="Cancel Requests" description="PO cancellation requests." icon={Ban} />
        <div className="card p-4 text-sm text-brand-muted">This page is available to administrators only.</div>
      </div>
    );
  }

  return (
    <div className="page-stack">
      <PageHeader
        title="Cancel Requests"
        description="Every PO cancellation request — who raised it, why, and whether the ERP confirmed it."
        icon={Ban}
        tone="red"
        actions={
          <ExportButton
            url={api.poViewCancelRequestsExportUrl()}
            filename={`po-cancel-requests-${new Date().toISOString().slice(0, 10)}.xlsx`}
          />
        }
      />

      {error && <div className="card p-3 text-xs text-signal-red">{error}</div>}

      <div className="card flex flex-wrap items-center gap-2 p-3">
        <input
          className="border border-brand-border rounded px-3 py-2 text-sm w-full max-w-xs"
          placeholder="Search PO / supplier / material / requester…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <div className="flex items-center gap-1.5">
          {STATUS_TABS.map((s) => (
            <button
              key={s || "ALL"}
              onClick={() => setStatus(s)}
              className={`rounded-full border px-3 py-1 text-xs font-semibold transition ${
                status === s
                  ? "border-signal-red bg-red-50 text-signal-red"
                  : "border-brand-border text-brand-muted hover:bg-subtle"
              }`}
            >
              {s === "" ? "All" : s === "PENDING" ? "Pending" : "Cancelled"}
            </button>
          ))}
        </div>
        <span className="ml-auto text-xs text-brand-muted">
          {filtered.length} request{filtered.length === 1 ? "" : "s"}
        </span>
      </div>

      {loading ? (
        <div className="card p-6 text-center text-sm text-brand-muted">
          <Loader2 className="inline animate-spin" size={16} /> Loading…
        </div>
      ) : (
        <div className="card overflow-x-auto">
          <table className="w-full min-w-[960px] text-xs">
            <thead className="bg-subtle text-left text-[10px] uppercase tracking-wider text-brand-muted">
              <tr>
                <th className="px-3 py-2">PO No</th>
                <th className="px-3 py-2">Supplier</th>
                <th className="px-3 py-2">Material</th>
                <th className="px-3 py-2 text-right">Qty</th>
                <th className="px-3 py-2">Customer</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2">Requested by</th>
                <th className="px-3 py-2">Requested at</th>
                <th className="px-3 py-2">Reason</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-brand-border">
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={9} className="px-4 py-8 text-center text-brand-muted">
                    No cancellation requests{status ? ` with status ${status}` : ""}.
                  </td>
                </tr>
              )}
              {filtered.map((r) => (
                <tr key={r.procurement_record_id} className={`hover:bg-subtle/50 ${r.closed ? "opacity-60" : ""}`}>
                  <td className="px-3 py-2 whitespace-nowrap">
                    <span className="font-medium text-brand-dark">{r.po_short_ref || r.supplier_po_no || "—"}</span>
                    {r.po_short_ref && <div className="text-[10px] text-brand-muted">#{r.supplier_po_no}</div>}
                  </td>
                  <td className="max-w-[170px] px-3 py-2">
                    <div className="truncate" title={r.supplier_name || undefined}>{r.supplier_name || "—"}</div>
                  </td>
                  <td className="max-w-[220px] px-3 py-2">
                    <div className="truncate text-brand-dark" title={r.material_name}>{r.material_name}</div>
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    {r.qty != null ? `${r.qty.toLocaleString()}${r.uom ? ` ${r.uom}` : ""}` : "—"}
                  </td>
                  <td className="max-w-[170px] px-3 py-2">
                    <div className="truncate" title={r.customer_name || undefined}>{r.customer_name || "—"}</div>
                  </td>
                  <td className="px-3 py-2">
                    {(r.cancellation_status || "").toUpperCase() === "CANCELLED" ? (
                      <span className="inline-flex rounded-full bg-red-50 px-2 py-0.5 text-[10px] font-semibold uppercase text-signal-red ring-1 ring-inset ring-red-100">Cancelled</span>
                    ) : (
                      <span className="inline-flex rounded-full bg-amber-50 px-2 py-0.5 text-[10px] font-semibold uppercase text-amber-700 ring-1 ring-inset ring-amber-100">Pending</span>
                    )}
                  </td>
                  <td className="px-3 py-2 whitespace-nowrap">{r.cancel_requested_by || "—"}</td>
                  <td className="px-3 py-2 whitespace-nowrap">{fmtDateTime(r.cancel_requested_at)}</td>
                  <td className="max-w-[240px] px-3 py-2">
                    <div className="truncate" title={r.cancel_remark || undefined}>{r.cancel_remark || "—"}</div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

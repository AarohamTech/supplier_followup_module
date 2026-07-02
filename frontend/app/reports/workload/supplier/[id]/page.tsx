"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, Factory, Loader2, ShieldCheck } from "lucide-react";

import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDate } from "@/lib/format";
import type { WorkloadSupplierDetail } from "@/lib/types";
import SignalDonut from "@/components/dashboard/SignalDonut";
import PageHeader from "@/components/layout/PageHeader";
import {
  BreakdownChips,
  ExportButton,
  OpenTaskTable,
  PendingPoTable,
  ThroughputChart,
  Tile,
  signalChip,
} from "@/components/reports/WorkloadShared";

export default function WorkloadSupplierDetailPage() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const supplierId = Number(Array.isArray(params.id) ? params.id[0] : params.id);
  const { hasRole } = useAuth();
  const [data, setData] = useState<WorkloadSupplierDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  const isAdmin = hasRole("admin");

  useEffect(() => {
    if (!isAdmin || !Number.isFinite(supplierId)) return;
    let cancelled = false;
    api
      .workloadSupplierDetail(supplierId)
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch((e) => {
        if (!cancelled) setError((e as Error).message);
      });
    return () => {
      cancelled = true;
    };
  }, [isAdmin, supplierId]);

  if (!isAdmin) {
    return (
      <div className="empty-state">
        <ShieldCheck className="mx-auto mb-2 h-6 w-6 text-brand-muted" />
        You need the <strong>admin</strong> role to view this report.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <button onClick={() => router.push("/reports/workload")} className="btn-ghost w-fit px-0 hover:bg-transparent">
        <ArrowLeft size={15} /> Back to workload report
      </button>

      {error && (
        <div role="alert" className="rounded-md border border-red-100 bg-red-50 px-3 py-2 text-xs text-signal-red">
          {error}
        </div>
      )}

      {!data && !error && (
        <div className="empty-state">
          <Loader2 className="mx-auto mb-2 h-5 w-5 animate-spin text-brand-muted" /> Loading report…
        </div>
      )}

      {data && (
        <>
          <PageHeader
            title={data.supplier.supplier_name}
            description={`Supplier report · ${data.pos.total} PO lines · ${data.mails.incoming} mails in / ${data.mails.outgoing} out${
              data.mails.response_rate != null ? ` · reply rate ${data.mails.response_rate}` : ""
            }`}
            icon={Factory}
            tone="red"
            actions={
              <>
                {data.worst_signal && (
                  <span className={`badge ${signalChip(data.worst_signal)}`}>{data.worst_signal}</span>
                )}
                <ExportButton
                  url={api.workloadSupplierExportUrl(data.supplier.supplier_id)}
                  filename={`workload-${data.supplier.supplier_name.replace(/\s+/g, "-")}.xlsx`}
                  label="Export this report"
                />
              </>
            }
          />

          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 xl:grid-cols-8">
            <Tile label="Pending POs" value={data.pos.pending} />
            <Tile label="Overdue POs" value={data.pos.overdue} accent />
            <Tile label="Avg follow-ups" value={data.pos.avg_followups} />
            <Tile label="Open tasks" value={data.tasks.open} />
            <Tile label="Open escalations" value={data.tasks.escalations} accent />
            <Tile label="Unread mail" value={data.mails.unread} />
            <Tile label="ASNs in transit" value={data.asns.filter((a) => !["DELIVERED", "CANCELLED", "DRAFT"].includes(a.status)).length} />
            <Tile label="Delivered ASNs" value={data.asns.filter((a) => a.status === "DELIVERED").length} />
          </div>

          <div className="grid gap-3 lg:grid-cols-2">
            <SignalDonut
              title="PO signal mix"
              green={data.pos.green}
              yellow={data.pos.yellow}
              red={data.pos.red}
              black={data.pos.black}
            />
            <ThroughputChart data={data.throughput} />
          </div>

          <div className="grid gap-3 lg:grid-cols-2">
            <BreakdownChips title="Tasks by status" data={data.by_status} />
            <BreakdownChips title="Tasks by priority" data={data.by_priority} />
          </div>

          {/* Shipments */}
          <section className="card overflow-hidden">
            <div className="border-b border-brand-border px-4 py-3">
              <h2 className="text-sm font-semibold text-brand-dark">Shipments ({data.asns.length})</h2>
              <p className="text-xs text-brand-muted">ASNs submitted by this supplier — newest first.</p>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-brand-border bg-subtle/60 text-left text-[10px] uppercase tracking-wider text-brand-muted">
                    <th className="px-4 py-2 font-semibold">ASN / PO</th>
                    <th className="px-3 py-2 font-semibold">Status</th>
                    <th className="px-3 py-2 font-semibold">Progress</th>
                    <th className="px-3 py-2 font-semibold">Carrier / Tracking</th>
                    <th className="px-4 py-2 text-right font-semibold">ETA</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-brand-border">
                  {data.asns.map((a) => (
                    <tr key={a.id} className="hover:bg-subtle/50">
                      <td className="px-4 py-2">
                        <div className="font-medium text-brand-dark">{a.asn_no}</div>
                        {a.supplier_po_no && <div className="text-[10px] text-brand-muted">PO {a.supplier_po_no}</div>}
                      </td>
                      <td className="px-3 py-2">
                        <span className="text-brand-dark">{a.status_label || a.status}</span>
                        {a.alert && <span className="ml-1.5 badge bg-red-50 text-signal-red">Alert</span>}
                      </td>
                      <td className="px-3 py-2">
                        <div className="flex items-center gap-2">
                          <span className="relative h-1.5 w-24 overflow-hidden rounded-full bg-subtle">
                            <span
                              className="absolute inset-y-0 left-0 rounded-full bg-emerald-500"
                              style={{ width: `${a.progress_percent}%` }}
                            />
                          </span>
                          <span className="tabular-nums text-brand-muted">{a.progress_percent}%</span>
                        </div>
                      </td>
                      <td className="px-3 py-2">
                        <div className="text-brand-dark">{a.carrier_name || "—"}</div>
                        {a.tracking_no && <div className="text-[10px] text-brand-muted">{a.tracking_no}</div>}
                      </td>
                      <td className="px-4 py-2 text-right text-brand-dark">{a.eta ? fmtDate(a.eta) : "—"}</td>
                    </tr>
                  ))}
                  {data.asns.length === 0 && (
                    <tr>
                      <td colSpan={5} className="px-4 py-8 text-center text-brand-muted">No shipments yet.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>

          <PendingPoTable rows={data.pending_pos} />
          <OpenTaskTable rows={data.open_tasks} />
        </>
      )}
    </div>
  );
}

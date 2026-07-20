"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, Building2, Loader2, ShieldCheck } from "lucide-react";

import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { WorkloadCustomerDetail } from "@/lib/types";
import SignalDonut from "@/components/dashboard/SignalDonut";
import PageHeader from "@/components/layout/PageHeader";
import { ExportButton, PendingPoTable, Tile, signalChip } from "@/components/reports/WorkloadShared";

const SIGNALS = ["", "GREEN", "YELLOW", "RED", "BLACK"];

/**
 * Per-customer workload drill-down: every PO line behind the counts on the
 * "By customer" tab. `?name=…&signal=RED` deep-links straight to that
 * customer's red POs (the count cells on the tab link here). Query params are
 * read client-side (no useSearchParams → no Suspense requirement).
 */
export default function WorkloadCustomerDetailPage() {
  const router = useRouter();
  const { hasRole } = useAuth();
  const isAdmin = hasRole("admin");

  const [name, setName] = useState<string | null>(null);
  const [signal, setSignal] = useState("");
  const [data, setData] = useState<WorkloadCustomerDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    setName(q.get("name") || "");
    setSignal((q.get("signal") || "").toUpperCase());
  }, []);

  const load = useCallback(async (customer: string, sig: string) => {
    setLoading(true);
    try {
      setData(await api.workloadCustomerDetail(customer, sig || undefined));
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!isAdmin || name === null) return;
    if (!name) {
      setError("No customer selected.");
      setLoading(false);
      return;
    }
    void load(name, signal);
  }, [isAdmin, name, signal, load]);

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

      {loading && !data && (
        <div className="empty-state">
          <Loader2 className="mx-auto mb-2 h-5 w-5 animate-spin text-brand-muted" /> Loading report…
        </div>
      )}

      {data && (
        <>
          <PageHeader
            title={data.customer_name}
            description={`${data.suppliers} supplier(s) · ${data.pos.total} PO lines from the CRM feed`}
            icon={Building2}
            tone="red"
            actions={
              <ExportButton
                url={api.workloadCustomerExportUrl(data.customer_name, signal || undefined)}
                filename={`workload-${data.customer_name.replace(/\s+/g, "-")}${signal ? `-${signal.toLowerCase()}` : ""}.xlsx`}
                label="Export this report"
              />
            }
          />

          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6">
            <Tile label="PO lines" value={data.pos.total} />
            <Tile label="Pending POs" value={data.pos.pending} />
            <Tile label="Green" value={data.pos.green} />
            <Tile label="Yellow" value={data.pos.yellow} />
            <Tile label="Red" value={data.pos.red} accent />
            <Tile label="Black" value={data.pos.black} accent />
          </div>

          <div className="grid gap-3 lg:grid-cols-2">
            <SignalDonut
              title="PO signal mix"
              green={data.pos.green}
              yellow={data.pos.yellow}
              red={data.pos.red}
              black={data.pos.black}
            />
            <div className="card p-4">
              <div className="mb-3 text-sm font-semibold">Filter the PO list by signal</div>
              <div className="flex flex-wrap gap-1.5">
                {SIGNALS.map((s) => (
                  <button
                    key={s || "ALL"}
                    onClick={() => setSignal(s)}
                    className={`rounded-full border px-3 py-1 text-xs font-semibold transition ${
                      signal === s
                        ? "border-signal-red bg-red-50 text-signal-red"
                        : "border-brand-border text-brand-muted hover:bg-subtle"
                    }`}
                  >
                    {s ? <span className={`badge ${signalChip(s)}`}>{s}</span> : "All signals"}
                  </button>
                ))}
              </div>
              <p className="mt-3 text-xs text-brand-muted">
                {signal
                  ? `Showing only ${signal} PO lines — the export follows this filter.`
                  : "Showing every pending PO line for this customer."}
              </p>
            </div>
          </div>

          <PendingPoTable rows={data.pending_pos} showSupplier />
        </>
      )}
    </div>
  );
}

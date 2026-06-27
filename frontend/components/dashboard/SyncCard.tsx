"use client";
import { useState } from "react";
import { Database, Loader2, RefreshCw } from "lucide-react";
import api from "@/lib/api";
import { useStore } from "@/lib/store";
import { useAuth } from "@/lib/auth";

type CrmResult = { ok?: boolean; status?: string; result?: Record<string, unknown> } | null;

function summaryText(r: CrmResult): string {
  if (!r) return "Idle — POs sync automatically from the CRM";
  const res = (r.result || r) as Record<string, unknown>;
  if (r.status === "DISABLED" || res?.status === "DISABLED") {
    return "CRM ingestion is disabled (set CRM_INGEST_ENABLED)";
  }
  const num = (k: string) => Number(res?.[k] ?? 0);
  return `${num("created")} created, ${num("updated")} updated, ${num("skipped")} skipped, ${num("errors")} errors`;
}

export default function SyncCard() {
  const { hasRole } = useAuth();
  const refresh = useStore((s) => s.refresh);
  const loadSuppliers = useStore((s) => s.loadSuppliers);
  const kpis = useStore((s) => s.kpis);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<CrmResult>(null);
  const [error, setError] = useState<string | null>(null);

  // CRM intake is an admin-only control.
  if (!hasRole("admin")) return null;

  const sync = async () => {
    setBusy(true);
    setError(null);
    try {
      const r = await api.crmSyncNow();
      setResult(r);
      await refresh();
      await loadSuppliers();
    } catch (e: any) {
      setError(e.message ?? "Sync failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <div className="h-8 w-8 rounded-md bg-emerald-50 grid place-content-center">
            <Database size={16} className="text-emerald-600" />
          </div>
          <div>
            <div className="text-sm font-medium">Live CRM Intake</div>
            <div className="text-[11px] text-brand-muted">Auto-synced from the CRM</div>
          </div>
        </div>
        <span className="chip text-emerald-600 border-emerald-100 bg-emerald-50">CRM Sync</span>
      </div>

      <div className="mt-3 text-xs text-brand-muted">Records in DB</div>
      <div className="text-2xl font-semibold">{kpis?.total_records ?? "-"}</div>

      <div className="mt-2 text-xs text-brand-muted">Last sync</div>
      <div className={error ? "text-sm text-signal-red" : "text-sm"}>{error ?? summaryText(result)}</div>

      <button
        onClick={sync}
        disabled={busy}
        className="mt-3 w-full bg-emerald-50 text-emerald-700 text-sm font-medium py-2 rounded-md flex items-center justify-center gap-2 hover:bg-emerald-100 disabled:opacity-50"
      >
        {busy ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
        Sync from CRM now
      </button>
    </div>
  );
}

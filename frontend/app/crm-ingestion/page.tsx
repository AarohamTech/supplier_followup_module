"use client";

import { useCallback, useEffect, useState } from "react";
import { Database, Loader2, RefreshCw } from "lucide-react";

import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { CrmIngestLog } from "@/lib/types";

function fmt(d?: string | null) {
  if (!d) return "—";
  const x = new Date(d);
  return isNaN(x.getTime()) ? "—" : x.toLocaleString();
}

const STATUS_CLASS: Record<string, string> = {
  OK: "bg-emerald-50 text-emerald-700",
  ERROR: "bg-red-50 text-signal-red",
  DISABLED: "bg-gray-100 text-gray-500",
};

export default function CrmIngestionPage() {
  const { hasRole } = useAuth();
  const isAdmin = hasRole("admin");
  const [logs, setLogs] = useState<CrmIngestLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setLogs(await api.crmIngestionLogs(100));
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!isAdmin) return;
    void load();
    const t = setInterval(load, 15000); // live refresh while open
    return () => clearInterval(t);
  }, [isAdmin, load]);

  if (!isAdmin) {
    return (
      <div className="page-stack">
        <div className="card p-6 text-sm text-brand-muted">CRM ingestion history is available to admins only.</div>
      </div>
    );
  }

  const syncNow = async () => {
    setBusy(true);
    try {
      await api.crmSyncNow();
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const last = logs[0];
  const totalAdded = logs.reduce((a, l) => a + (l.created || 0), 0);
  const totalChanged = logs.reduce((a, l) => a + (l.updated || 0), 0);

  return (
    <div className="page-stack">
      <div className="page-header">
        <div>
          <h1 className="page-title">CRM Ingestion</h1>
          <p className="page-subtitle">Live purchase-order fetch history from the Hariom CRM (admin only).</p>
        </div>
        <button onClick={syncNow} disabled={busy} className="btn-primary">
          {busy ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />} Sync now
        </button>
      </div>

      {error && <div className="rounded-md bg-red-50 px-3 py-2 text-xs text-signal-red">{error}</div>}

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <div className="card p-4">
          <div className="text-xs text-brand-muted">Last fetch</div>
          <div className="text-sm font-semibold">{last ? fmt(last.ran_at) : "—"}</div>
        </div>
        <div className="card p-4">
          <div className="text-xs text-brand-muted">Last status</div>
          <div className="text-sm font-semibold">{last?.status ?? "—"}</div>
        </div>
        <div className="card p-4">
          <div className="text-xs text-brand-muted">Added (last {logs.length})</div>
          <div className="text-2xl font-semibold text-emerald-600">{totalAdded}</div>
        </div>
        <div className="card p-4">
          <div className="text-xs text-brand-muted">Changed (last {logs.length})</div>
          <div className="text-2xl font-semibold text-blue-600">{totalChanged}</div>
        </div>
      </div>

      <div className="card overflow-x-auto">
        <table className="w-full min-w-[820px] text-sm">
          <thead className="bg-slate-50 text-left text-[11px] uppercase tracking-wider text-brand-muted">
            <tr>
              <th className="px-3 py-2">Time</th>
              <th className="px-3 py-2">Trigger</th>
              <th className="px-3 py-2">Status</th>
              <th className="px-3 py-2">Fetched</th>
              <th className="px-3 py-2">Generated</th>
              <th className="px-3 py-2">Added</th>
              <th className="px-3 py-2">Changed</th>
              <th className="px-3 py-2">Skipped</th>
              <th className="px-3 py-2">Errors</th>
              <th className="px-3 py-2">Took</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={10} className="px-3 py-6 text-center text-brand-muted">
                  <Loader2 size={16} className="mx-auto animate-spin" />
                </td>
              </tr>
            ) : logs.length === 0 ? (
              <tr>
                <td colSpan={10} className="px-3 py-6 text-center text-brand-muted">
                  <Database size={16} className="mx-auto mb-1 opacity-50" />
                  No fetches yet — they appear here automatically every few minutes.
                </td>
              </tr>
            ) : (
              logs.map((l) => (
                <tr key={l.id} className="border-t border-brand-border">
                  <td className="whitespace-nowrap px-3 py-2">{fmt(l.ran_at)}</td>
                  <td className="px-3 py-2">{l.trigger}</td>
                  <td className="px-3 py-2">
                    <span className={`inline-flex rounded-full px-2 py-0.5 text-[10px] font-semibold ${STATUS_CLASS[l.status] || "bg-gray-100 text-gray-600"}`}>
                      {l.status}
                    </span>
                  </td>
                  <td className="px-3 py-2">{l.fetched}</td>
                  <td className="px-3 py-2">{l.generated}</td>
                  <td className="px-3 py-2 font-medium text-emerald-700">{l.created}</td>
                  <td className="px-3 py-2 font-medium text-blue-700">{l.updated}</td>
                  <td className="px-3 py-2">{l.skipped}</td>
                  <td className="px-3 py-2">{l.errors ? <span className="text-signal-red">{l.errors}</span> : 0}</td>
                  <td className="px-3 py-2 text-xs text-brand-muted">{l.duration_ms != null ? `${(l.duration_ms / 1000).toFixed(1)}s` : "—"}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {last?.status === "ERROR" && last?.message && (
        <div className="rounded-md bg-red-50 px-3 py-2 text-xs text-signal-red">Last error: {last.message}</div>
      )}
    </div>
  );
}

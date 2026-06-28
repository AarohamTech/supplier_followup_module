"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { getToken } from "@/lib/auth-token";
import type { TaskAnalytics } from "@/lib/types";

export default function TaskAnalyticsPage() {
  const [data, setData] = useState<TaskAnalytics | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);

  useEffect(() => {
    api.taskAnalytics().then(setData).catch((e) => setErr((e as Error).message));
  }, []);

  const download = async () => {
    setDownloading(true);
    try {
      const token = getToken();
      const res = await fetch(api.taskAnalyticsExportUrl(), {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error(`Export failed: ${res.status} ${res.statusText}`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "task-analytics.xlsx";
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setDownloading(false);
    }
  };

  if (err) return <div className="p-6 text-signal-red">{err}</div>;
  if (!data) return <div className="p-6 text-brand-muted">Loading…</div>;

  const Stat = ({ label, value }: { label: string; value: number | string }) => (
    <div className="rounded-lg border border-brand-border p-4">
      <div className="text-2xl font-semibold text-brand-dark">{value}</div>
      <div className="text-xs text-brand-muted">{label}</div>
    </div>
  );

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-brand-dark">Task Analytics</h1>
        <button
          className="btn-primary"
          onClick={download}
          disabled={downloading}
        >
          {downloading ? "Exporting…" : "Export Excel"}
        </button>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
        <Stat label="Total" value={data.totals.total} />
        <Stat label="Open" value={data.totals.open} />
        <Stat label="Overdue" value={data.totals.overdue} />
        <Stat label="Done" value={data.totals.done} />
        <Stat label="Avg cycle (h)" value={data.avg_cycle_hours ?? "—"} />
      </div>

      <section>
        <h2 className="mb-2 text-sm font-semibold text-brand-dark">Workload by assignee</h2>
        <div className="overflow-x-auto rounded-lg border border-brand-border">
          <table className="min-w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs text-brand-muted">
              <tr>
                <th className="p-2">Assignee</th>
                <th className="p-2">Open</th>
                <th className="p-2">Overdue</th>
                <th className="p-2">Done</th>
              </tr>
            </thead>
            <tbody>
              {data.by_assignee.map((r) => (
                <tr key={r.user_id} className="border-t border-brand-border">
                  <td className="p-2">{r.name}</td>
                  <td className="p-2">{r.open}</td>
                  <td className="p-2 text-signal-red">{r.overdue}</td>
                  <td className="p-2">{r.done}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <div className="grid gap-6 sm:grid-cols-3">
        {(["by_status", "by_priority", "by_source"] as const).map((key) => (
          <section key={key}>
            <h2 className="mb-2 text-sm font-semibold capitalize text-brand-dark">
              {key.replace("by_", "By ")}
            </h2>
            <div className="space-y-1">
              {Object.entries(data[key]).map(([k, v]) => (
                <div key={k} className="flex justify-between text-sm">
                  <span className="text-brand-muted">{k}</span>
                  <span className="font-medium text-brand-dark">{v}</span>
                </div>
              ))}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}

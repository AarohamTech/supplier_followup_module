"use client";

import { useEffect, useState } from "react";
import { Loader2, PieChart } from "lucide-react";

import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDate } from "@/lib/format";
import type { WorkloadUserDetail } from "@/lib/types";
import SignalDonut from "@/components/dashboard/SignalDonut";
import PageHeader from "@/components/layout/PageHeader";
import {
  BreakdownChips,
  ExportButton,
  OpenTaskTable,
  PendingPoTable,
  ThroughputChart,
  Tile,
} from "@/components/reports/WorkloadShared";

/** Employee "My Workload" — the admin per-user workload report, always scoped
 *  to the logged-in employee (server-side). */
export default function EmployeeWorkloadPage() {
  const { user } = useAuth();
  const [data, setData] = useState<WorkloadUserDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .eportalWorkload()
      .then((d) => !cancelled && setData(d))
      .catch((e) => !cancelled && setError((e as Error).message));
    return () => {
      cancelled = true;
    };
  }, []);

  const name = user?.full_name || user?.username || "My workload";

  return (
    <div className="space-y-4">
      {error && (
        <div role="alert" className="rounded-md border border-red-100 bg-red-50 px-3 py-2 text-xs text-signal-red">
          {error}
        </div>
      )}

      {!data && !error && (
        <div className="empty-state">
          <Loader2 className="mx-auto mb-2 h-5 w-5 animate-spin text-brand-muted" /> Building your report…
        </div>
      )}

      {data && (
        <>
          <PageHeader
            title={`Workload — ${name}`}
            description={[
              data.user.emp_code ? `desk ${data.user.emp_code}` : null,
              data.user.last_login_at ? `last login ${fmtDate(data.user.last_login_at)}` : null,
            ]
              .filter(Boolean)
              .join(" · ") || "Your POs, tasks and throughput."}
            icon={PieChart}
            tone="red"
            actions={
              <ExportButton
                url={api.eportalWorkloadExportUrl()}
                filename={`my-workload-${new Date().toISOString().slice(0, 10)}.xlsx`}
                label="Export my report"
              />
            }
          />

          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 xl:grid-cols-8">
            <Tile label="Pending POs" value={data.pos.pending} />
            <Tile label="Overdue POs" value={data.pos.overdue} accent />
            <Tile label="Red / Black POs" value={data.pos.red + data.pos.black} accent />
            <Tile label="Open tasks" value={data.tasks.open} />
            <Tile label="Overdue tasks" value={data.tasks.overdue} accent />
            <Tile label="Due today" value={data.tasks.due_today} />
            <Tile label="Done (all time)" value={data.tasks.done} />
            <Tile label="Avg cycle (h)" value={data.avg_cycle_hours ?? "—"} />
          </div>

          <div className="grid gap-3 lg:grid-cols-2">
            <SignalDonut
              title="My PO signal mix"
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

          <PendingPoTable rows={data.pending_pos} showSupplier />
          <OpenTaskTable rows={data.open_tasks} />
        </>
      )}
    </div>
  );
}

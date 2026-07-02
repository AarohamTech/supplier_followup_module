"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, Loader2, ShieldCheck, UserRound } from "lucide-react";

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

export default function WorkloadUserDetailPage() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const userId = Number(Array.isArray(params.id) ? params.id[0] : params.id);
  const { hasRole } = useAuth();
  const [data, setData] = useState<WorkloadUserDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  const isAdmin = hasRole("admin");

  useEffect(() => {
    if (!isAdmin || !Number.isFinite(userId)) return;
    let cancelled = false;
    api
      .workloadUserDetail(userId)
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch((e) => {
        if (!cancelled) setError((e as Error).message);
      });
    return () => {
      cancelled = true;
    };
  }, [isAdmin, userId]);

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
            title={data.user.name}
            description={[
              data.user.role,
              data.user.emp_code ? `desk ${data.user.emp_code}` : null,
              data.user.email,
              data.user.last_login_at ? `last login ${fmtDate(data.user.last_login_at)}` : "never logged in",
            ]
              .filter(Boolean)
              .join(" · ")}
            icon={UserRound}
            tone="red"
            actions={
              <ExportButton
                url={api.workloadUserExportUrl(data.user.user_id)}
                filename={`workload-${(data.user.name || "user").replace(/\s+/g, "-")}.xlsx`}
                label="Export this report"
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
              title="Owned PO signal mix"
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

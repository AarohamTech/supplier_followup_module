"use client";
import Link from "next/link";
import { ListChecks } from "lucide-react";
import type { PortalTaskDashboard } from "@/lib/types";

/** Compact tasks-overview card. Works for any role — feed it the role's
 * tasks-dashboard payload and the href to that role's task list. */
export default function TasksSummaryCard({
  data,
  href,
}: {
  data: PortalTaskDashboard | null;
  href: string;
}) {
  const stats: { label: string; value: number; strong?: boolean }[] = [
    { label: "To do", value: data?.todo ?? 0 },
    { label: "Waiting", value: data?.waiting ?? 0 },
    { label: "In progress", value: data?.in_progress ?? 0 },
    { label: "Overdue", value: data?.overdue ?? 0, strong: true },
    { label: "Critical", value: data?.critical ?? 0, strong: true },
    { label: "Done", value: data?.done ?? 0 },
  ];
  return (
    <div className="card p-4">
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <ListChecks size={14} className="text-signal-red" />
          <div className="font-semibold text-sm">Tasks</div>
        </div>
        <Link href={href} className="text-xs font-medium text-signal-red hover:underline">
          Open →
        </Link>
      </div>
      <div className="grid grid-cols-3 gap-3">
        {stats.map((s) => (
          <div key={s.label}>
            <div
              className={
                "text-xl font-semibold tracking-tight " +
                (s.strong && s.value ? "text-signal-red" : "text-brand-dark")
              }
            >
              {s.value}
            </div>
            <div className="text-[10px] uppercase tracking-wider text-brand-muted">{s.label}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

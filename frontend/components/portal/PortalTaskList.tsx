"use client";

import { useState } from "react";

import type { PortalTask } from "@/lib/types";

const STATUSES = [
  "BACKLOG",
  "TODO",
  "IN_PROGRESS",
  "WAITING_SUPPLIER",
  "WAITING_CUSTOMER",
  "BLOCKED",
  "DONE",
] as const;

const STATUS_LABEL: Record<string, string> = {
  BACKLOG: "Backlog",
  TODO: "To do",
  IN_PROGRESS: "In progress",
  WAITING_SUPPLIER: "Waiting supplier",
  WAITING_CUSTOMER: "Waiting customer",
  BLOCKED: "Blocked",
  DONE: "Done",
};

const SIGNAL_CHIP: Record<string, string> = {
  GREEN: "bg-emerald-50 text-emerald-700",
  YELLOW: "bg-amber-50 text-amber-700",
  RED: "bg-red-50 text-signal-red",
  BLACK: "bg-gray-800 text-white",
};

function fmtDate(v?: string | null): string {
  if (!v) return "—";
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString(undefined, { day: "2-digit", month: "short" });
}

/**
 * Scoped task list for the portals. Read-only by default; when `onUpdate` is
 * supplied (employee portal) each row exposes status + progress controls.
 */
export default function PortalTaskList({
  tasks,
  onUpdate,
}: {
  tasks: PortalTask[];
  onUpdate?: (id: number, patch: { status?: string; progress_percent?: number }) => Promise<void>;
}) {
  const [busyId, setBusyId] = useState<number | null>(null);
  const editable = typeof onUpdate === "function";

  const run = async (id: number, patch: { status?: string; progress_percent?: number }) => {
    if (!onUpdate) return;
    setBusyId(id);
    try {
      await onUpdate(id, patch);
    } finally {
      setBusyId(null);
    }
  };

  if (tasks.length === 0) {
    return (
      <div className="rounded-md border border-brand-border bg-white px-4 py-10 text-center text-sm text-brand-muted">
        No tasks for you right now.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-brand-border bg-white">
      <table className="min-w-full text-sm">
        <thead className="bg-slate-50 text-left text-[11px] uppercase tracking-wide text-brand-muted">
          <tr>
            <th className="px-3 py-2 font-semibold">Task</th>
            <th className="px-3 py-2 font-semibold">Priority</th>
            <th className="px-3 py-2 font-semibold">Signal</th>
            <th className="px-3 py-2 font-semibold">Due</th>
            <th className="px-3 py-2 font-semibold">Progress</th>
            <th className="px-3 py-2 font-semibold">Status</th>
          </tr>
        </thead>
        <tbody>
          {tasks.map((t) => {
            const done = (t.status || "").toUpperCase() === "DONE";
            const sig = (t.signal || "").toUpperCase();
            const progress = t.progress_percent ?? 0;
            return (
              <tr key={t.id} className={`border-t border-brand-border ${done ? "opacity-60" : ""}`}>
                <td className="px-3 py-2">
                  <div className="font-medium text-brand-dark">{t.title}</div>
                  {t.material_name && <div className="text-xs text-brand-muted">{t.material_name}</div>}
                </td>
                <td className="px-3 py-2 text-brand-dark">{t.priority}</td>
                <td className="px-3 py-2">
                  {sig ? (
                    <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${SIGNAL_CHIP[sig] ?? "bg-gray-100 text-gray-700"}`}>
                      {sig}
                    </span>
                  ) : (
                    "—"
                  )}
                </td>
                <td className="px-3 py-2 text-brand-dark">{fmtDate(t.due_date)}</td>
                <td className="px-3 py-2">
                  <div className="flex items-center gap-2">
                    <div className="h-1.5 w-20 overflow-hidden rounded-full bg-gray-100">
                      <div className="h-full rounded-full bg-emerald-500" style={{ width: `${progress}%` }} />
                    </div>
                    {editable ? (
                      <input
                        type="number"
                        min={0}
                        max={100}
                        defaultValue={progress}
                        disabled={busyId === t.id}
                        onBlur={(e) => {
                          const v = Math.max(0, Math.min(100, Number(e.target.value) || 0));
                          if (v !== progress) void run(t.id, { progress_percent: v });
                        }}
                        className="w-14 rounded border border-brand-border px-1 py-0.5 text-xs"
                      />
                    ) : (
                      <span className="text-xs text-brand-muted">{progress}%</span>
                    )}
                  </div>
                </td>
                <td className="px-3 py-2">
                  {editable ? (
                    <select
                      value={t.status}
                      disabled={busyId === t.id}
                      onChange={(e) => void run(t.id, { status: e.target.value })}
                      className="rounded border border-brand-border px-2 py-1 text-xs"
                    >
                      {STATUSES.map((s) => (
                        <option key={s} value={s}>
                          {STATUS_LABEL[s] ?? s}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <span className="rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-700">
                      {STATUS_LABEL[t.status] ?? t.status}
                    </span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

"use client";

import { memo } from "react";
import {
  CheckSquare,
  ClipboardCheck,
  PackageSearch,
  Plus,
  RefreshCw,
} from "lucide-react";
import type { CommunicationTask } from "@/lib/types";
import { useRenderCount } from "./hooks";

interface TaskPanelProps {
  tasks: CommunicationTask[];
  loading: boolean;
  creating: boolean;
  onCreateTask: () => void;
  onQuickAction: (kind: "stock" | "supplier" | "planning") => void;
}

const PRIORITY_DOT: Record<string, string> = {
  P0: "bg-signal-red",
  P1: "bg-amber-500",
  P2: "bg-blue-500",
  P3: "bg-gray-400",
};

function TaskPanelBase({
  tasks,
  loading,
  creating,
  onCreateTask,
  onQuickAction,
}: TaskPanelProps) {
  useRenderCount("TaskPanel");
  const openTasks = tasks.filter((t) => t.status !== "DONE");

  return (
    <div className="space-y-3 border-t border-brand-border p-3">
      <div className="grid grid-cols-2 gap-2">
        <button
          type="button"
          onClick={onCreateTask}
          disabled={creating}
          className="flex items-center justify-center gap-1.5 rounded-md border border-brand-border bg-white py-2 text-xs font-medium text-brand-dark hover:bg-gray-50 disabled:opacity-50"
        >
          <Plus className="h-3.5 w-3.5" /> Create Task
        </button>
        <button
          type="button"
          onClick={() => onQuickAction("stock")}
          disabled={creating}
          className="flex items-center justify-center gap-1.5 rounded-md border border-brand-border bg-white py-2 text-xs font-medium text-brand-dark hover:bg-gray-50 disabled:opacity-50"
        >
          <PackageSearch className="h-3.5 w-3.5" /> Stock Check
        </button>
        <button
          type="button"
          onClick={() => onQuickAction("supplier")}
          disabled={creating}
          className="flex items-center justify-center gap-1.5 rounded-md border border-brand-border bg-white py-2 text-xs font-medium text-brand-dark hover:bg-gray-50 disabled:opacity-50"
        >
          <RefreshCw className="h-3.5 w-3.5" /> Supplier Update
        </button>
        <button
          type="button"
          onClick={() => onQuickAction("planning")}
          disabled={creating}
          className="flex items-center justify-center gap-1.5 rounded-md border border-brand-border bg-white py-2 text-xs font-medium text-brand-dark hover:bg-gray-50 disabled:opacity-50"
        >
          <ClipboardCheck className="h-3.5 w-3.5" /> Planning Confirm
        </button>
      </div>

      <div>
        <div className="mb-1.5 flex items-center justify-between">
          <span className="text-[11px] font-semibold uppercase tracking-wide text-brand-muted">
            Open Tasks
          </span>
          <span className="flex h-5 min-w-5 items-center justify-center rounded-full bg-signal-red px-1.5 text-[11px] font-semibold text-white">
            {openTasks.length}
          </span>
        </div>

        {loading ? (
          <div className="py-3 text-center text-xs text-brand-muted">Loading tasks…</div>
        ) : openTasks.length === 0 ? (
          <div className="flex flex-col items-center gap-1 py-4 text-center text-xs text-brand-muted">
            <CheckSquare className="h-5 w-5 opacity-50" />
            No open tasks for this mail.
          </div>
        ) : (
          <div className="space-y-1.5">
            {openTasks.map((task) => (
              <div
                key={task.id}
                className="rounded-lg border border-brand-border bg-white p-2.5"
              >
                <div className="flex items-start justify-between gap-2">
                  <span className="text-xs font-medium text-brand-dark">{task.title}</span>
                  <span className="text-[10px] text-brand-muted">#{task.id}</span>
                </div>
                <div className="mt-1 flex items-center gap-2 text-[10px] text-brand-muted">
                  <span className="flex items-center gap-1">
                    <span className={`h-2 w-2 rounded-full ${PRIORITY_DOT[task.priority] || "bg-gray-400"}`} />
                    {task.priority}
                  </span>
                  <span>· {task.status}</span>
                  {task.assigned_to && <span>· {task.assigned_to}</span>}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export const TaskPanel = memo(TaskPanelBase);

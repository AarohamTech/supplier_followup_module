"use client";

import { useCallback, useEffect, useState } from "react";

import { api } from "@/lib/api";
import type { PortalTask } from "@/lib/types";
import PortalTaskList from "@/components/portal/PortalTaskList";

export default function EmployeeTasksPage() {
  const [tasks, setTasks] = useState<PortalTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setTasks(await api.eportalTasks());
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const onUpdate = useCallback(
    async (id: number, patch: { status?: string; progress_percent?: number }) => {
      await api.eportalUpdateTask(id, patch);
      await load();
    },
    [load],
  );

  return (
    <div className="page-stack">
      <div className="page-header">
        <div>
          <h1 className="page-title">My Tasks</h1>
          <p className="page-subtitle">
            {loading ? "Loading…" : `${tasks.length} task(s) assigned to you or on your POs`}
          </p>
        </div>
      </div>
      {error && <div className="rounded-md bg-red-50 px-3 py-2 text-xs text-signal-red">{error}</div>}
      {!loading && <PortalTaskList tasks={tasks} onUpdate={onUpdate} />}
    </div>
  );
}

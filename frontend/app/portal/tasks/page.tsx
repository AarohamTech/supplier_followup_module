"use client";

import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import type { PortalTask } from "@/lib/types";
import PortalTaskList from "@/components/portal/PortalTaskList";

export default function SupplierTasksPage() {
  const [tasks, setTasks] = useState<PortalTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const t = await api.portalTasks();
        if (!cancelled) setTasks(t);
      } catch (e) {
        if (!cancelled) setError((e as Error).message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="page-stack">
      <div className="page-header">
        <div>
          <h1 className="page-title">Tasks</h1>
          <p className="page-subtitle">
            {loading ? "Loading…" : `${tasks.length} task(s) on your purchase orders`}
          </p>
        </div>
      </div>
      {error && <div className="rounded-md bg-red-50 px-3 py-2 text-xs text-signal-red">{error}</div>}
      {!loading && <PortalTaskList tasks={tasks} />}
    </div>
  );
}

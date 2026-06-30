"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AlertTriangle, Boxes, Clock, FileSpreadsheet, Layers, ShieldAlert } from "lucide-react";

import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { EmployeePo, EmployeeSummary } from "@/lib/types";
import { StatCard } from "@/components/portal/PortalCards";
import EmployeePoTable from "@/components/eportal/EmployeePoTable";

export default function EmployeeDashboard() {
  const { user } = useAuth();
  const [summary, setSummary] = useState<EmployeeSummary | null>(null);
  const [pos, setPos] = useState<EmployeePo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [s, p] = await Promise.all([api.eportalSummary(), api.eportalPos()]);
        if (!cancelled) {
          setSummary(s);
          setPos(p.items);
        }
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

  const name = summary?.full_name || user?.full_name || user?.username || "Employee";

  return (
    <div className="page-stack">
      <div className="page-header">
        <div>
          <h1 className="page-title">Welcome, {name}</h1>
          <p className="page-subtitle">Purchase orders assigned to you, live from the CRM.</p>
        </div>
        <Link href="/eportal/pos" className="btn-primary">
          <FileSpreadsheet size={14} /> My Purchase Orders
        </Link>
      </div>

      {error && <div className="rounded-md bg-red-50 px-3 py-2 text-xs text-signal-red">{error}</div>}

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-6">
        <StatCard label="Total POs" value={loading ? "—" : summary?.total_pos ?? 0} icon={Layers} tint="bg-blue-50 text-blue-600" />
        <StatCard label="Materials" value={loading ? "—" : summary?.total_materials ?? 0} icon={Boxes} tint="bg-indigo-50 text-indigo-600" />
        <StatCard label="Red" value={loading ? "—" : summary?.red ?? 0} icon={AlertTriangle} tint="bg-red-50 text-signal-red" />
        <StatCard label="Black" value={loading ? "—" : summary?.black ?? 0} icon={ShieldAlert} tint="bg-subtle text-brand-dark" strong />
        <StatCard label="Overdue POs" value={loading ? "—" : summary?.overdue_pos ?? 0} icon={Clock} tint="bg-amber-50 text-amber-600" />
        <StatCard label="Escalated" value={loading ? "—" : summary?.escalated_pos ?? 0} icon={ShieldAlert} tint="bg-orange-50 text-orange-600" />
      </div>

      <div>
        <div className="mb-2 flex items-center justify-between">
          <div className="text-[11px] font-semibold uppercase tracking-wider text-brand-muted">Your Purchase Orders</div>
          <Link href="/eportal/pos" className="text-xs font-medium text-signal-red hover:underline">
            View all →
          </Link>
        </div>
        {!loading && <EmployeePoTable pos={pos.slice(0, 10)} />}
      </div>
    </div>
  );
}

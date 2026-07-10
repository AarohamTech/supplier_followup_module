"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { FileSpreadsheet, ListChecks, ListFilter, MessagesSquare } from "lucide-react";

import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useStore } from "@/lib/store";
import type { EmployeePo, PortalTaskDashboard } from "@/lib/types";
import PoExpandableTable from "@/components/po/PoExpandableTable";
import KpiStrip from "@/components/dashboard/KpiStrip";
import StatusDonut from "@/components/dashboard/StatusDonut";
import OverdueDonut from "@/components/dashboard/OverdueDonut";
import AIInsights from "@/components/dashboard/AIInsights";
import TasksSummaryCard from "@/components/dashboard/TasksSummaryCard";
import SupplierChart from "@/components/dashboard/SupplierChart";

const QUICK_LINKS = [
  { href: "/eportal/pos", label: "My Purchase Orders", icon: FileSpreadsheet },
  { href: "/eportal/followups", label: "Black Follow-ups", icon: ListFilter },
  { href: "/eportal/communication", label: "Communication", icon: MessagesSquare },
  { href: "/eportal/tasks", label: "My Tasks", icon: ListChecks },
];

/**
 * Employee dashboard — same depth as the admin control tower (KPI strip, signal
 * donut, workload bar, AI insights), but scoped to the employee's owned POs via
 * the shared store (scope='employee'), plus a tasks overview and the owned-PO list.
 */
export default function EmployeeDashboard() {
  const { user } = useAuth();
  const setScope = useStore((s) => s.setScope);
  const refresh = useStore((s) => s.refresh);
  const breakdown = useStore((s) => s.breakdown);
  const [pos, setPos] = useState<EmployeePo[]>([]);
  const [tasks, setTasks] = useState<PortalTaskDashboard | null>(null);

  useEffect(() => {
    setScope("employee");
    void refresh();
    let cancelled = false;
    (async () => {
      try {
        const [p, t] = await Promise.all([api.eportalPos(), api.eportalTasksDashboard()]);
        if (!cancelled) {
          setPos(p.items);
          setTasks(t);
        }
      } catch {
        /* non-fatal — KPI/chart cards still render from the store */
      }
    })();
    return () => {
      cancelled = true;
      // Reset so the staff /po-followups page behaves normally if revisited.
      setScope("staff");
    };
  }, [setScope, refresh]);

  const name = user?.full_name || user?.username || "Employee";

  return (
    <div className="page-stack">
      <div className="page-header">
        <div>
          <h1 className="page-title">Welcome, {name}</h1>
          <p className="page-subtitle">Your assigned purchase orders at a glance, live from the CRM.</p>
        </div>
        <Link href="/eportal/pos" className="btn-primary">
          <FileSpreadsheet size={14} /> My Purchase Orders
        </Link>
      </div>

      <KpiStrip />

      <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-4">
        <StatusDonut />
        <SupplierChart />
        <OverdueDonut />
        <TasksSummaryCard data={tasks} href="/eportal/tasks" />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <div className="mb-2 flex items-center justify-between">
            <div className="text-[11px] font-semibold uppercase tracking-wider text-brand-muted">
              Your Purchase Orders
              {breakdown ? (
                <span className="ml-2 rounded-full bg-red-50 px-1.5 py-0.5 text-[10px] font-semibold text-signal-red">
                  {breakdown.pending_count} pending
                </span>
              ) : null}
            </div>
            <Link href="/eportal/pos" className="text-xs font-medium text-signal-red hover:underline">
              View all →
            </Link>
          </div>
          <PoExpandableTable
            pos={pos.slice(0, 10)}
            loadDetail={(p) => api.eportalPoDetail(p.supplier_po_no, p.supplier_name || undefined)}
            requestCancel={(p, remark) => api.eportalRequestPoCancel(p.supplier_po_no, p.supplier_name || undefined, remark).then(() => {})}
          />
        </div>
        <div className="space-y-4">
          <AIInsights />
          <div className="card p-4">
            <div className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-brand-muted">
              Quick actions
            </div>
            <div className="space-y-1">
              {QUICK_LINKS.map(({ href, label, icon: Icon }) => (
                <Link
                  key={href}
                  href={href}
                  className="flex items-center gap-2.5 rounded-md px-2 py-2 text-sm text-brand-dark hover:bg-subtle"
                >
                  <Icon size={15} className="text-brand-muted" />
                  {label}
                </Link>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

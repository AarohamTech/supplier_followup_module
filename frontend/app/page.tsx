import Link from "next/link";
import { MessagesSquare, ShieldAlert } from "lucide-react";

import SyncCard from "@/components/dashboard/SyncCard";
import SupplierMasterCard from "@/components/dashboard/SupplierMasterCard";
import EmailMasterCard from "@/components/dashboard/EmailMasterCard";
import AlertsCard from "@/components/dashboard/AlertsCard";
import KpiStrip from "@/components/dashboard/KpiStrip";
import FiltersBar from "@/components/procurement/FiltersBar";
import QuickFilters from "@/components/procurement/QuickFilters";
import PoTable from "@/components/procurement/PoTable";
import ActionCenter from "@/components/dashboard/ActionCenter";
import RecentReplies from "@/components/dashboard/RecentReplies";
import NoReplySince from "@/components/dashboard/NoReplySince";
import AIInsights from "@/components/dashboard/AIInsights";
import OverdueDonut from "@/components/dashboard/OverdueDonut";
import StatusDonut from "@/components/dashboard/StatusDonut";
import MailEngineStatusCard from "@/components/dashboard/MailEngineStatusCard";
import PageHeader from "@/components/layout/PageHeader";
import LazyMount from "@/components/LazyMount";

export default function DashboardPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Procurement control tower"
        description="Priorities, supplier communication and shipment risk in one operational view."
        actions={
          <>
            <Link href="/mail-history" className="btn-outline">
              <MessagesSquare size={14} /> Communication hub
            </Link>
            <Link href="/black-followups" className="btn-primary">
              <ShieldAlert size={14} /> Black follow-ups
            </Link>
          </>
        }
      />

      <KpiStrip />

      <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_20rem]">
        <div className="min-w-0 space-y-5">
          <div className="grid gap-4 sm:grid-cols-3">
            <SupplierMasterCard />
            <EmailMasterCard />
            <AlertsCard />
          </div>

          <section className="card overflow-hidden">
            <div className="border-b border-brand-border px-4 py-3">
              <h2 className="text-sm font-semibold text-brand-dark">Purchase order workspace</h2>
              <p className="mt-0.5 text-xs text-brand-muted">Narrow the live queue by supplier, signal or order reference.</p>
            </div>
            <div className="p-4">
              <FiltersBar />
            </div>
            <div className="border-t border-brand-border bg-slate-50/70 p-3">
              <QuickFilters />
            </div>
          </section>

          <PoTable />
        </div>

        <aside className="space-y-4 xl:sticky xl:top-20">
          <SyncCard />
          <NoReplySince />
          <ActionCenter />
          <RecentReplies />
        </aside>
      </div>

      <LazyMount minHeight={340}>
        <section>
          <div className="mb-3">
            <h2 className="text-sm font-semibold text-brand-dark">Operational intelligence</h2>
            <p className="mt-0.5 text-xs text-brand-muted">Risk signals and workload patterns derived from the current queue.</p>
          </div>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            <AIInsights />
            <OverdueDonut />
            <StatusDonut />
          </div>
        </section>
      </LazyMount>

      <LazyMount minHeight={120}>
        <MailEngineStatusCard />
      </LazyMount>
    </div>
  );
}

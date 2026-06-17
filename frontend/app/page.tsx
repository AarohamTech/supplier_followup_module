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
import { Activity } from "lucide-react";

export default function DashboardPage() {
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className="grid h-10 w-10 place-items-center rounded-lg bg-brand-dark text-white shadow-card">
            <Activity size={18} />
          </span>
          <div>
            <h1 className="text-xl font-bold text-brand-dark">Control Tower</h1>
            <p className="text-sm text-brand-muted">Live supplier follow-up, risk, and mail operations.</p>
          </div>
        </div>
        <span className="chip bg-emerald-50 text-emerald-700">Auto-monitoring</span>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <SyncCard />
        <SupplierMasterCard />
        <EmailMasterCard />
        <AlertsCard />
      </div>
      <KpiStrip />
      <FiltersBar />
      <QuickFilters />
      <div className="grid grid-cols-1 xl:grid-cols-[1fr_320px] gap-4">
        <PoTable />
        <div className="space-y-4">
          <ActionCenter />
          <RecentReplies />
          <NoReplySince />
        </div>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <AIInsights />
        <OverdueDonut />
        <StatusDonut />
      </div>
      <MailEngineStatusCard />
    </div>
  );
}

import { LayoutDashboard } from "lucide-react";

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

export default function DashboardPage() {
  return (
    <div className="page-stack">
      <PageHeader
        title="Dashboard"
        description="Live procurement signals, mail status and supplier follow-up priorities."
        icon={LayoutDashboard}
      />
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

import { FileSpreadsheet } from "lucide-react";

import DownloadPoButton from "@/components/procurement/DownloadPoButton";
import FiltersBar from "@/components/procurement/FiltersBar";
import QuickFilters from "@/components/procurement/QuickFilters";
import PoTable from "@/components/procurement/PoTable";
import PageHeader from "@/components/layout/PageHeader";

export default function Page() {
  return (
    <div className="page-stack">
      <PageHeader
        title="PO Follow-ups"
        description={
          <>
            Signal-based PO mails are queued automatically in the background. Use{" "}
            <span className="font-medium text-signal-red">PO Mail</span> only for a manual queue action.
          </>
        }
        icon={FileSpreadsheet}
        actions={<DownloadPoButton />}
      />
      <FiltersBar />
      <QuickFilters />
      <PoTable />
    </div>
  );
}

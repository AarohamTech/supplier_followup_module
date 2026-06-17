import FiltersBar from "@/components/procurement/FiltersBar";
import QuickFilters from "@/components/procurement/QuickFilters";
import PoTable from "@/components/procurement/PoTable";
import { FileSpreadsheet } from "lucide-react";

export default function Page() {
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className="grid h-10 w-10 place-items-center rounded-lg bg-brand-dark text-white shadow-card">
            <FileSpreadsheet size={18} />
          </span>
          <div>
            <h1 className="text-xl font-bold text-brand-dark">PO Follow-ups</h1>
            <p className="text-sm text-brand-muted">Signal-based mail queues with manual PO Mail override.</p>
          </div>
        </div>
      </div>
      <FiltersBar />
      <QuickFilters />
      <PoTable />
    </div>
  );
}

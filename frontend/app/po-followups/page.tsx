import FiltersBar from "@/components/procurement/FiltersBar";
import QuickFilters from "@/components/procurement/QuickFilters";
import PoTable from "@/components/procurement/PoTable";

export default function Page() {
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">PO Follow-ups</h1>
      <p className="text-sm text-brand-muted">Signal-based PO mails are queued automatically in the background. Use <span className="font-medium text-signal-red">PO Mail</span> only for a manual queue action.</p>
      <FiltersBar />
      <QuickFilters />
      <PoTable />
    </div>
  );
}

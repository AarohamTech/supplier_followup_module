"use client";

import { useEffect } from "react";
import { FileSpreadsheet } from "lucide-react";

import { useStore } from "@/lib/store";
import FiltersBar from "@/components/procurement/FiltersBar";
import QuickFilters from "@/components/procurement/QuickFilters";
import PoTable from "@/components/procurement/PoTable";
import PageHeader from "@/components/layout/PageHeader";

/**
 * Employee PO Follow-ups — the SAME page the staff get at /po-followups
 * (PageHeader + FiltersBar + QuickFilters + PoTable, all reading the shared
 * zustand store), but scoped to the employee's own POs by flipping the store
 * scope to 'employee' on mount (and back to 'staff' on unmount).
 */
export default function EmployeeFollowupsPage() {
  const setScope = useStore((s) => s.setScope);
  const refresh = useStore((s) => s.refresh);

  useEffect(() => {
    setScope("employee");
    void refresh();
    return () => {
      // Reset so the staff /po-followups page behaves normally if revisited.
      setScope("staff");
    };
  }, [setScope, refresh]);

  return (
    <div className="page-stack">
      <PageHeader
        title="PO Follow-ups"
        description="Your assigned POs by signal — filter to your Black (critical) follow-ups."
        icon={FileSpreadsheet}
      />
      <FiltersBar />
      <QuickFilters />
      <PoTable />
    </div>
  );
}

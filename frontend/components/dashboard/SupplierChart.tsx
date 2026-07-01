"use client";
import { useStore } from "@/lib/store";
import SupplierDonut from "./SupplierDonut";

function scrollToWorkspace() {
  if (typeof document !== "undefined")
    document.getElementById("po-workspace")?.scrollIntoView({ behavior: "smooth", block: "start" });
}

/** Store-connected supplier-distribution donut (reads the scoped `breakdown`).
 * When `drillable`, clicking a supplier filters the PO table to it. The aggregated
 * "Others" slice is not a real supplier, so it is not clickable. */
export default function SupplierChart({ drillable = false }: { drillable?: boolean }) {
  const breakdown = useStore((s) => s.breakdown);
  const setFilters = useStore((s) => s.setFilters);
  const data = (breakdown?.by_supplier ?? []).map((s) => ({ name: s.name, value: s.count }));
  const onSliceClick = drillable
    ? (name: string) => {
        if (name === "Others") return;
        setFilters({ supplier_name: name });
        scrollToWorkspace();
      }
    : undefined;
  return <SupplierDonut data={data} onSliceClick={onSliceClick} />;
}

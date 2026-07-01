"use client";
import { useStore } from "@/lib/store";
import SignalDonut from "./SignalDonut";

function scrollToWorkspace() {
  if (typeof document !== "undefined")
    document.getElementById("po-workspace")?.scrollIntoView({ behavior: "smooth", block: "start" });
}

/** Signal donut for the staff/employee dashboard — feeds SignalDonut from the
 * scoped store KPIs. When `drillable`, clicking a slice filters the PO table to
 * that signal and scrolls up to it (admin dashboard drill-down). */
export default function StatusDonut({ drillable = false }: { drillable?: boolean }) {
  const k = useStore((s) => s.kpis);
  const setFilters = useStore((s) => s.setFilters);
  const onSliceClick = drillable
    ? (signal: string) => {
        setFilters({ signal });
        scrollToWorkspace();
      }
    : undefined;
  return (
    <SignalDonut
      green={k?.green_count ?? 0}
      yellow={k?.yellow_count ?? 0}
      red={k?.red_count ?? 0}
      black={k?.black_count ?? 0}
      onSliceClick={onSliceClick}
    />
  );
}

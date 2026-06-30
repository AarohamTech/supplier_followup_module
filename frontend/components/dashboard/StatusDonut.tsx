"use client";
import { useStore } from "@/lib/store";
import SignalDonut from "./SignalDonut";

/** Signal donut for the staff/employee dashboard — feeds SignalDonut from the
 * scoped store KPIs (staff = all POs, employee = owned POs). */
export default function StatusDonut() {
  const k = useStore((s) => s.kpis);
  return (
    <SignalDonut
      green={k?.green_count ?? 0}
      yellow={k?.yellow_count ?? 0}
      red={k?.red_count ?? 0}
      black={k?.black_count ?? 0}
    />
  );
}

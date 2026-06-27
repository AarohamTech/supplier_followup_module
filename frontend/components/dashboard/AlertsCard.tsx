"use client";
import { useStore } from "@/lib/store";
import { AlertTriangle, ArrowUpRight } from "lucide-react";
import Link from "next/link";

export default function AlertsCard() {
  const k = useStore((s) => s.kpis);
  return (
    <div className="card flex min-h-40 flex-col p-4">
      <div className="flex items-center gap-2">
        <div className="h-8 w-8 rounded-md bg-red-50 grid place-content-center">
          <AlertTriangle size={16} className="text-signal-red" />
        </div>
        <div className="text-sm font-medium">System Alerts</div>
      </div>
      <div className="mt-3 space-y-1">
        <Row label="Black" value={k?.black_count ?? 0} tone="red" />
        <Row label="Red (Overdue)" value={k?.red_count ?? 0} tone="red" />
        <Row label="HI Follow-up Required" value={k?.ai_required_count ?? 0} />
      </div>
      <Link href="/black-followups" className="mt-auto inline-flex items-center gap-1 pt-4 text-xs font-semibold text-signal-red hover:text-red-700 active:scale-[0.98]">
        View black follow-ups <ArrowUpRight size={13} />
      </Link>
    </div>
  );
}
function Row({ label, value, tone }: { label: string; value: number; tone?: "red" }) {
  return (
    <div className="flex justify-between text-sm">
      <span className="text-brand-muted">{label}</span>
      <span className={"font-medium " + (tone === "red" ? "text-signal-red" : "")}>{value}</span>
    </div>
  );
}

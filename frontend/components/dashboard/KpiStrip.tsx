"use client";
import { useStore } from "@/lib/store";
import { Layers, Calendar, AlertCircle, Zap, MessageSquare, Sparkles } from "lucide-react";

export default function KpiStrip() {
  const k = useStore((s) => s.kpis);
  const items = [
    { icon: Layers, label: "Total records", value: k?.total_records ?? 0, tint: "bg-blue-50 text-blue-700" },
    { icon: Calendar, label: "Due today", value: k?.due_today_count ?? 0, tint: "bg-amber-50 text-amber-700" },
    { icon: AlertCircle, label: "Overdue", value: k?.overdue_count ?? 0, tint: "bg-red-50 text-signal-red", strong: true },
    { icon: Zap, label: "Black", value: k?.black_count ?? 0, tint: "bg-red-50 text-signal-red", strong: true },
    { icon: MessageSquare, label: "Red signal", value: k?.red_count ?? 0, tint: "bg-rose-50 text-rose-700" },
    { icon: Sparkles, label: "HI required", value: k?.ai_required_count ?? 0, tint: "bg-violet-50 text-violet-700" },
  ];
  return (
    <section aria-label="Procurement overview" className="grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-brand-border bg-brand-border shadow-card md:grid-cols-3 lg:grid-cols-6">
      {items.map((it) => {
        const I = it.icon;
        return (
          <div key={it.label} className="flex min-w-0 items-center gap-3 bg-white p-4 lg:p-5">
            <div className={"grid h-9 w-9 shrink-0 place-content-center rounded-md " + it.tint}>
              <I size={16} strokeWidth={1.8} />
            </div>
            <div className="min-w-0">
              <div className="truncate text-[10px] font-semibold uppercase tracking-[0.12em] text-brand-muted" title={it.label}>{it.label}</div>
              <div className={"mt-0.5 text-2xl font-semibold tracking-tight " + (it.strong ? "text-signal-red" : "text-brand-dark")}>{it.value}</div>
            </div>
          </div>
        );
      })}
    </section>
  );
}

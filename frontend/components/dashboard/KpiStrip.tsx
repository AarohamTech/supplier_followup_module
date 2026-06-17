"use client";
import { useStore } from "@/lib/store";
import { Layers, Calendar, AlertCircle, Zap, MessageSquare, Sparkles } from "lucide-react";

export default function KpiStrip() {
  const k = useStore((s) => s.kpis);
  const items = [
    { icon: Layers, label: "Total records", value: k?.total_records ?? 0, tint: "bg-blue-50 text-blue-700" },
    { icon: Calendar, label: "Due today", value: k?.due_today_count ?? 0, tint: "bg-amber-50 text-amber-700" },
    { icon: AlertCircle, label: "Overdue", value: k?.overdue_count ?? 0, tint: "bg-red-50 text-signal-red", strong: true },
    { icon: Zap, label: "Critical", value: k?.black_count ?? 0, tint: "bg-gray-100 text-gray-900", strong: true },
    { icon: MessageSquare, label: "Red signal", value: k?.red_count ?? 0, tint: "bg-red-50 text-signal-red" },
    { icon: Sparkles, label: "AI required", value: k?.ai_required_count ?? 0, tint: "bg-violet-50 text-violet-700" },
  ];
  return (
    <div className="card grid grid-cols-2 overflow-hidden md:grid-cols-3 lg:grid-cols-6">
      {items.map((it, index) => {
        const I = it.icon;
        return (
          <div
            key={it.label}
            className="flex items-center gap-3 border-b border-brand-border/70 p-4 last:border-b-0 md:[&:nth-last-child(-n+3)]:border-b-0 lg:border-b-0 lg:border-r lg:last:border-r-0"
            style={{ animation: "page-in 460ms cubic-bezier(0.2, 0.8, 0.2, 1) both", animationDelay: `${index * 45}ms` }}
          >
            <div className={"grid h-10 w-10 shrink-0 place-content-center rounded-lg " + it.tint}>
              <I size={16} />
            </div>
            <div className="min-w-0">
              <div className="truncate text-xs font-semibold text-brand-muted">{it.label}</div>
              <div className={"kpi-num " + (it.strong ? "text-signal-red" : "")}>{it.value}</div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

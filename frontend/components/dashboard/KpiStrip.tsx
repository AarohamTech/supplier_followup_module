"use client";
import { useStore } from "@/lib/store";
import { Layers, Calendar, AlertCircle, Zap, MessageSquare, Sparkles } from "lucide-react";

export default function KpiStrip() {
  const k = useStore((s) => s.kpis);
  const items = [
    { icon: Layers, label: "TOTAL RECORDS", value: k?.total_records ?? 0, tint: "bg-blue-50 text-blue-600" },
    { icon: Calendar, label: "DUE TODAY", value: k?.due_today_count ?? 0, tint: "bg-amber-50 text-amber-600" },
    { icon: AlertCircle, label: "OVERDUE", value: k?.overdue_count ?? 0, tint: "bg-red-50 text-signal-red", strong: true },
    { icon: Zap, label: "BLACK / CRITICAL", value: k?.black_count ?? 0, tint: "bg-gray-100 text-gray-900", strong: true },
    { icon: MessageSquare, label: "RED", value: k?.red_count ?? 0, tint: "bg-red-50 text-signal-red" },
    { icon: Sparkles, label: "AI REQUIRED", value: k?.ai_required_count ?? 0, tint: "bg-purple-50 text-purple-600" },
  ];
  return (
    <div className="card grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 divide-x divide-brand-border">
      {items.map((it) => {
        const I = it.icon;
        return (
          <div key={it.label} className="p-4 flex items-center gap-3">
            <div className={"h-9 w-9 rounded-md grid place-content-center " + it.tint}>
              <I size={16} />
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-wider text-brand-muted font-semibold">{it.label}</div>
              <div className={"kpi-num " + (it.strong ? "text-signal-red" : "")}>{it.value}</div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

"use client";
import { useStore } from "@/lib/store";
import { Activity } from "lucide-react";

export default function AIInsights() {
  const list = useStore((s) => s.list);
  const k = useStore((s) => s.kpis);

  const items: string[] = [];
  if (k) {
    if (k.black_count) items.push(`${k.black_count} BLACK record(s) flagged for escalation.`);
    if (k.red_count) items.push(`${k.red_count} RED record(s) overdue — urgent follow-up due today.`);
    if (k.ai_required_count) items.push(`${k.ai_required_count} record(s) need AI-generated follow-up mails.`);
    if (k.due_today_count) items.push(`${k.due_today_count} shipment(s) are due today — confirm dispatch.`);
  }
  // top supplier with most overdue / RED+BLACK rows
  const supplierCounts = new Map<string, number>();
  (list?.items ?? []).forEach((r) => {
    if (r.signal === "RED" || r.signal === "BLACK") {
      const s = r.supplier_name ?? "Unknown";
      supplierCounts.set(s, (supplierCounts.get(s) ?? 0) + 1);
    }
  });
  const topSupplier = [...supplierCounts.entries()].sort((a, b) => b[1] - a[1])[0];
  if (topSupplier) items.push(`${topSupplier[0]} has ${topSupplier[1]} BLACK / RED PO line(s).`);

  if (!items.length) items.push("All records are on track. No immediate action required.");

  return (
    <div className="card p-4">
      <div className="flex items-center gap-2 mb-3">
        <Activity size={14} className="text-signal-red" />
        <div className="font-semibold text-sm">Harmony Intelligent</div>
      </div>
      <ul className="space-y-2">
        {items.map((t, i) => (
          <li key={i} className="flex gap-2 text-sm">
            <span className="text-signal-red mt-1">•</span>
            <span>{t}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

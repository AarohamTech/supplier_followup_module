"use client";
import { useStore } from "@/lib/store";
import { fmtDate } from "@/lib/format";
import Link from "next/link";

export default function RecentReplies() {
  const list = useStore((s) => s.list);
  const items = (list?.items ?? [])
    .filter((r) => r.last_supplier_reply)
    .slice(0, 3);
  return (
    <div className="card p-4">
      <div className="mb-3 flex items-center justify-between">
        <div className="text-sm font-semibold">Recent supplier replies</div>
        <Link href="/mail-history" className="text-xs font-medium text-signal-red hover:text-red-700">View all</Link>
      </div>
      <div className="space-y-3">
        {items.length === 0 && <div className="text-xs text-brand-muted">No supplier replies recorded yet.</div>}
        {items.map((r) => (
          <div key={r.id} className="flex gap-2">
            <div className="h-2 w-2 mt-2 rounded-full bg-emerald-500" />
            <div className="flex-1">
              <div className="text-sm font-medium">{r.supplier_name}</div>
              <div className="text-xs text-brand-muted line-clamp-2">{r.last_supplier_reply}</div>
              <div className="text-[10px] uppercase text-brand-muted mt-0.5 tracking-wider">{fmtDate(r.last_followup_date)}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

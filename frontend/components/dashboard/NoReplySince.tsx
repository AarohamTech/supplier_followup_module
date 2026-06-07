"use client";
import { useStore } from "@/lib/store";

export default function NoReplySince() {
  const list = useStore((s) => s.list);
  const noReply = (list?.items ?? []).filter((r) => !r.last_supplier_reply && (r.signal === "RED" || r.signal === "BLACK")).length;
  return (
    <div className="card p-4">
      <div className="flex items-center justify-between mb-2">
        <div className="font-semibold text-sm">No Reply (Critical)</div>
      </div>
      <div className="flex items-end gap-2">
        <div className="text-4xl font-bold">{noReply}</div>
        <div className="text-xs text-brand-muted pb-1">RED/BLACK records with no supplier reply</div>
      </div>
    </div>
  );
}

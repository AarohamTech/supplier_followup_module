"use client";
import { useStore } from "@/lib/store";
import { MessageCircleOff } from "lucide-react";

export default function NoReplySince() {
  const list = useStore((s) => s.list);
  const noReply = (list?.items ?? []).filter((r) => !r.last_supplier_reply && (r.signal === "RED" || r.signal === "BLACK")).length;
  return (
    <div className="card p-4">
      <div className="mb-2 flex items-center gap-2">
        <MessageCircleOff size={14} className="text-signal-red" />
        <div className="text-sm font-semibold">Black / red without reply</div>
      </div>
      <div className="flex items-end gap-3">
        <div className="text-3xl font-semibold tracking-tight text-brand-dark">{noReply}</div>
        <div className="pb-1 text-xs leading-relaxed text-brand-muted">Black or red records awaiting a supplier response</div>
      </div>
    </div>
  );
}

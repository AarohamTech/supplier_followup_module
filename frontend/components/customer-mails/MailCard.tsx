"use client";

import { memo } from "react";
import type { CustomerMail } from "@/lib/types";
import { useRenderCount } from "./hooks";
import { PRIORITY_TONE, formatDateTime } from "./shared";

interface MailCardProps {
  mail: CustomerMail;
  selected: boolean;
  onSelect: (id: number) => void;
}

/**
 * Memoized so it only re-renders when its own mail/selected state changes —
 * not when the parent re-renders for unrelated reasons (typing, drawer, etc.).
 */
function MailCardBase({ mail, selected, onSelect }: MailCardProps) {
  useRenderCount("MailCard");
  const openTasks = mail.open_task_count ?? 0;

  return (
    <button
      type="button"
      onClick={() => onSelect(mail.id)}
      className={[
        "w-full text-left rounded-lg border px-3 py-2.5 transition-colors",
        selected
          ? "border-signal-red bg-red-50/70"
          : "border-brand-border bg-white hover:bg-gray-50",
      ].join(" ")}
    >
      <div className="flex items-start justify-between gap-2">
        <span className="text-sm font-semibold text-brand-dark truncate">
          {mail.subject || "(no subject)"}
        </span>
        <span className="shrink-0 text-[11px] text-brand-muted">
          {formatDateTime(mail.received_at)}
        </span>
      </div>

      <div className="mt-0.5 text-xs text-brand-muted truncate">
        {mail.from_name || mail.customer_name || mail.from_email || "Unknown sender"}
      </div>

      <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
        {mail.linked_supplier_po_no && (
          <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-red-50 text-signal-red">
            {mail.linked_supplier_po_no}
          </span>
        )}
        <span
          className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${
            PRIORITY_TONE[mail.priority] || "bg-gray-200 text-brand-dark"
          }`}
        >
          {mail.priority}
        </span>
        {openTasks > 0 && (
          <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-violet-100 text-violet-700">
            {openTasks} task{openTasks === 1 ? "" : "s"}
          </span>
        )}
      </div>
    </button>
  );
}

export const MailCard = memo(MailCardBase);

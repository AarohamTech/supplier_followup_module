"use client";

import { memo } from "react";
import type { CustomerMail } from "@/lib/types";
import { useRenderCount } from "./hooks";
import { PRIORITY_TONE, URGENCY_TONE, formatDateTime } from "./shared";

interface MailCardProps {
  mail: CustomerMail;
  selected: boolean;
  onSelect: (id: number) => void;
}

/**
 * Flush list row (calm, like the Communication Hub). Memoized so it only
 * re-renders when its own mail/selected state changes — not when the parent
 * re-renders for unrelated reasons (typing, drawer, etc.).
 */
function MailCardBase({ mail, selected, onSelect }: MailCardProps) {
  useRenderCount("MailCard");
  const openTasks = mail.open_task_count ?? 0;

  return (
    <button
      type="button"
      onClick={() => onSelect(mail.id)}
      className={[
        "w-full border-b border-brand-border px-4 py-3 text-left transition-colors hover:bg-gray-50",
        selected ? "bg-red-50/40 shadow-[inset_3px_0_0_#E11D2E]" : "",
      ].join(" ")}
    >
      <div className="flex items-center gap-2">
        <span className="flex-1 truncate text-sm font-semibold text-brand-dark">
          {mail.subject || "(no subject)"}
        </span>
        <span className="shrink-0 text-[10px] text-gray-400">{formatDateTime(mail.received_at)}</span>
      </div>

      <div className="mt-0.5 truncate text-xs text-brand-muted">
        {mail.from_name || mail.customer_name || mail.from_email || "Unknown sender"}
      </div>

      <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
        <span
          className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${
            PRIORITY_TONE[mail.priority] || "bg-gray-100 text-gray-600"
          }`}
        >
          {mail.priority}
        </span>
        {mail.linked_supplier_po_no && (
          <span className="rounded bg-red-50 px-1.5 py-0.5 text-[10px] font-medium text-signal-red">
            {mail.linked_supplier_po_no}
          </span>
        )}
        {openTasks > 0 && (
          <span className="rounded bg-gray-100 px-1.5 py-0.5 text-[10px] font-medium text-gray-700">
            {openTasks} task{openTasks === 1 ? "" : "s"}
          </span>
        )}
        {mail.ai_urgency && (
          <span
            className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${
              URGENCY_TONE[mail.ai_urgency] || "bg-gray-100 text-brand-muted"
            }`}
            title={`AI triage${mail.ai_category ? ` · ${mail.ai_category}` : ""}${
              mail.ai_action ? ` · ${mail.ai_action}` : ""
            }`}
          >
            {mail.ai_urgency}
          </span>
        )}
      </div>
    </button>
  );
}

export const MailCard = memo(MailCardBase);

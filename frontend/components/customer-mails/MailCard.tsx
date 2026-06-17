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
 * Memoized so it only re-renders when its own mail/selected state changes -
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
        "mail-list-item px-3.5 py-3 transition-colors",
        selected
          ? "mail-list-item-active"
          : "",
      ].join(" ")}
    >
      <div className="flex items-start justify-between gap-2">
        <span className="truncate text-sm font-bold text-brand-dark">
          {mail.subject || "(no subject)"}
        </span>
        <span className="shrink-0 text-[11px] text-brand-muted">
          {formatDateTime(mail.received_at)}
        </span>
      </div>

      <div className="mt-1 truncate text-xs font-medium text-brand-muted">
        {mail.from_name || mail.customer_name || mail.from_email || "Unknown sender"}
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-1.5">
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
        {mail.ai_urgency && (
          <span
            className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${
              URGENCY_TONE[mail.ai_urgency] || "bg-gray-100 text-brand-muted"
            }`}
            title={`AI triage${mail.ai_category ? ` | ${mail.ai_category}` : ""}${
              mail.ai_action ? ` | ${mail.ai_action}` : ""
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

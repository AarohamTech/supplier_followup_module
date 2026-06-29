"use client";

import { memo } from "react";
import { Calendar, Clock, PanelRightOpen } from "lucide-react";
import type { CustomerMail } from "@/lib/types";
import { ReplyComposer } from "./ReplyComposer";
import { useRenderCount } from "./hooks";
import { PRIORITY_TONE, formatDateTime, timeAgo } from "./shared";

export interface LocalReply {
  id: number;
  text: string;
  at: string;
  status?: string;
}

function replyStatusLabel(status?: string): string | null {
  if (!status) return null;
  if (status === "SENT") return "Sent";
  if (status === "READY") return "Queued";
  if (status === "FAILED") return "Failed";
  return status;
}

interface ConversationPanelProps {
  mail: CustomerMail;
  localReplies: LocalReply[];
  sending: boolean;
  seed?: { text: string; nonce: number };
  onSend: (text: string) => void;
  onOpenContext: () => void;
}

function ConversationPanelBase({
  mail,
  localReplies,
  sending,
  seed,
  onSend,
  onOpenContext,
}: ConversationPanelProps) {
  useRenderCount("ConversationPanel");
  const recipient = mail.from_name || mail.customer_name || mail.from_email || "customer";

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {/* Header — clean single line */}
      <div className="shrink-0 border-b border-brand-border px-5 py-3">
        <div className="flex items-center gap-2">
          <h2 className="min-w-0 flex-1 truncate text-base font-semibold text-brand-dark">
            {mail.subject || "(no subject)"}
          </h2>
          <span
            className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-semibold ${
              PRIORITY_TONE[mail.priority] || "bg-gray-200 text-brand-dark"
            }`}
          >
            {mail.priority}
          </span>
          <button
            type="button"
            className="rounded-md p-1.5 text-gray-400 hover:bg-gray-100 hover:text-brand-dark"
            title="Schedule"
          >
            <Calendar className="h-4 w-4" />
          </button>
          <button
            type="button"
            className="rounded-md p-1.5 text-gray-400 hover:bg-gray-100 hover:text-brand-dark"
            title="History"
          >
            <Clock className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={onOpenContext}
            className="rounded-md p-1.5 text-gray-400 hover:bg-gray-100 hover:text-brand-dark 2xl:hidden"
            title="Procurement context"
          >
            <PanelRightOpen className="h-4 w-4" />
          </button>
        </div>
        <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-brand-muted">
          <span className="font-medium text-brand-dark">
            {mail.from_name || mail.customer_name || "Unknown"}
          </span>
          <span className="truncate">{mail.from_email}</span>
          {mail.linked_supplier_po_no && (
            <span className="text-signal-red">· Ref {mail.linked_supplier_po_no}</span>
          )}
        </div>
      </div>

      {/* Messages (scrolls) — chat bubbles with breathing room */}
      <div className="min-h-0 flex-1 space-y-5 overflow-y-auto bg-brand-surface/40 px-4 py-5 sm:px-6">
        {/* Incoming customer mail — left */}
        <div className="flex justify-start">
          <article className="max-w-[90%] rounded-xl border border-brand-border bg-white p-4 lg:max-w-[72ch]">
            <div className="mb-2 flex items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <span className="flex h-7 w-7 items-center justify-center rounded-md bg-signal-red text-[11px] font-semibold text-white">
                  {(mail.from_name || mail.from_email || "?").slice(0, 2).toUpperCase()}
                </span>
                <div className="leading-tight">
                  <div className="text-sm font-semibold text-brand-dark">
                    {mail.from_name || mail.customer_name || "Unknown"}
                  </div>
                  <div className="text-[11px] text-brand-muted">to ProcureDirect Support</div>
                </div>
              </div>
              <span className="shrink-0 text-[11px] text-brand-muted">
                {formatDateTime(mail.received_at)} · {timeAgo(mail.received_at)}
              </span>
            </div>
            <p className="whitespace-pre-wrap text-sm leading-relaxed text-brand-dark">
              {mail.body || "(empty body)"}
            </p>
          </article>
        </div>

        {/* Outgoing replies — right */}
        {localReplies.map((reply) => (
          <div key={reply.id} className="flex justify-end">
            <article className="max-w-[90%] rounded-xl border border-gray-200 bg-gray-50 p-4 lg:max-w-[72ch]">
              <div className="mb-1.5 flex items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold text-brand-dark">You replied</span>
                  {replyStatusLabel(reply.status) && (
                    <span className="rounded-full border border-brand-border bg-white px-1.5 py-0.5 text-[10px] font-medium text-brand-muted">
                      {replyStatusLabel(reply.status)}
                    </span>
                  )}
                </div>
                <span className="shrink-0 text-[11px] text-brand-muted">{formatDateTime(reply.at)}</span>
              </div>
              <p className="whitespace-pre-wrap text-sm leading-relaxed text-brand-dark">{reply.text}</p>
            </article>
          </div>
        ))}
      </div>

      {/* Composer pinned to bottom */}
      <ReplyComposer
        mailId={mail.id}
        recipientName={recipient}
        seed={seed}
        sending={sending}
        onSend={onSend}
      />
    </div>
  );
}

export const ConversationPanel = memo(ConversationPanelBase);

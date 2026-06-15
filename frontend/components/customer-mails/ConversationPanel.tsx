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
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="shrink-0 border-b border-brand-border px-4 py-3">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="truncate text-base font-semibold text-brand-dark">
              {mail.subject || "(no subject)"}
            </h2>
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
          <div className="flex shrink-0 items-center gap-1.5">
            <span
              className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${
                PRIORITY_TONE[mail.priority] || "bg-gray-200 text-brand-dark"
              }`}
            >
              {mail.priority}
            </span>
            <button
              type="button"
              className="rounded-md border border-brand-border p-1.5 text-brand-muted hover:bg-gray-50"
              title="Schedule"
            >
              <Calendar className="h-4 w-4" />
            </button>
            <button
              type="button"
              className="rounded-md border border-brand-border p-1.5 text-brand-muted hover:bg-gray-50"
              title="History"
            >
              <Clock className="h-4 w-4" />
            </button>
            <button
              type="button"
              onClick={onOpenContext}
              className="rounded-md border border-brand-border p-1.5 text-brand-muted hover:bg-gray-50 xl:hidden"
              title="Procurement context"
            >
              <PanelRightOpen className="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>

      {/* Messages (scrolls) */}
      <div className="flex-1 space-y-3 overflow-y-auto bg-brand-surface px-4 py-4">
        <article className="rounded-xl border border-brand-border bg-white p-4">
          <div className="mb-2 flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <span className="flex h-7 w-7 items-center justify-center rounded-md bg-signal-red text-[11px] font-semibold text-white">
                {(mail.from_name || mail.from_email || "?").slice(0, 2).toUpperCase()}
              </span>
              <div className="leading-tight">
                <div className="text-sm font-semibold text-brand-dark">
                  {mail.from_name || mail.customer_name || "Unknown"}
                </div>
                <div className="text-[11px] text-brand-muted">
                  to ProcureDirect Support
                </div>
              </div>
            </div>
            <span className="text-[11px] text-brand-muted">
              {formatDateTime(mail.received_at)} · {timeAgo(mail.received_at)}
            </span>
          </div>
          <p className="whitespace-pre-wrap text-sm leading-relaxed text-brand-dark">
            {mail.body || "(empty body)"}
          </p>
        </article>

        {localReplies.map((reply) => (
          <article
            key={reply.id}
            className="ml-8 rounded-xl border border-red-200 bg-red-50/60 p-4"
          >
            <div className="mb-1.5 flex items-center justify-between">
              <span className="text-sm font-semibold text-signal-red">You replied</span>
              <span className="text-[11px] text-brand-muted">
                {formatDateTime(reply.at)}
              </span>
            </div>
            <p className="whitespace-pre-wrap text-sm leading-relaxed text-brand-dark">
              {reply.text}
            </p>
          </article>
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

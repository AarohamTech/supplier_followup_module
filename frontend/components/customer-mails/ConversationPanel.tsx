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
  onAiGenerate?: (instruction: string) => Promise<string>;
}

function ConversationPanelBase({
  mail,
  localReplies,
  sending,
  seed,
  onSend,
  onOpenContext,
  onAiGenerate,
}: ConversationPanelProps) {
  useRenderCount("ConversationPanel");
  const recipient = mail.from_name || mail.customer_name || mail.from_email || "customer";

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="mail-thread-header shrink-0 px-5 py-4">
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
                <span className="text-signal-red">Ref {mail.linked_supplier_po_no}</span>
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
              className="grid h-8 w-8 place-items-center rounded-lg border border-brand-border bg-white text-brand-muted hover:bg-gray-50"
              title="Schedule"
            >
              <Calendar className="h-4 w-4" />
            </button>
            <button
              type="button"
              className="grid h-8 w-8 place-items-center rounded-lg border border-brand-border bg-white text-brand-muted hover:bg-gray-50"
              title="History"
            >
              <Clock className="h-4 w-4" />
            </button>
            <button
              type="button"
              onClick={onOpenContext}
              className="grid h-8 w-8 place-items-center rounded-lg border border-brand-border bg-white text-brand-muted hover:bg-gray-50 xl:hidden"
              title="Procurement context"
            >
              <PanelRightOpen className="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>

      {/* Messages (scrolls) */}
      <div className="flex-1 space-y-4 overflow-y-auto px-4 py-5 lg:px-6">
        <article className="mail-message mail-message-incoming p-4">
          <div className="mb-2 flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <span className="mail-avatar">
                {(mail.from_name || mail.from_email || "?").slice(0, 2).toUpperCase()}
              </span>
              <div className="leading-tight">
                <div className="text-sm font-semibold text-brand-dark">
                  {mail.from_name || mail.customer_name || "Unknown"}
                </div>
                <div className="text-[11px] text-brand-muted">
                  to support
                </div>
              </div>
            </div>
            <span className="text-[11px] text-brand-muted">
              {formatDateTime(mail.received_at)} | {timeAgo(mail.received_at)}
            </span>
          </div>
          <p className="whitespace-pre-wrap text-sm leading-relaxed text-brand-dark">
            {mail.body || "(empty body)"}
          </p>
        </article>

        {localReplies.map((reply) => (
          <article
            key={reply.id}
            className="mail-message mail-message-outgoing ml-8 p-4"
          >
            <div className="mb-1.5 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-sm font-semibold text-signal-red">You replied</span>
                {replyStatusLabel(reply.status) && (
                  <span className="rounded-full border border-brand-border bg-white px-1.5 py-0.5 text-[10px] font-medium text-brand-muted">
                    {replyStatusLabel(reply.status)}
                  </span>
                )}
              </div>
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
        onAiGenerate={onAiGenerate}
      />
    </div>
  );
}

export const ConversationPanel = memo(ConversationPanelBase);

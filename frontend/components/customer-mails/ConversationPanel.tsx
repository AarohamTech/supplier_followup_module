"use client";

import { memo } from "react";
import { Calendar, Clock, PanelRightOpen } from "lucide-react";
import type { CustomerMail } from "@/lib/types";
import { useT } from "@/lib/i18n";
import { ReplyComposer } from "./ReplyComposer";
import { useRenderCount } from "./hooks";
import { PRIORITY_TONE, formatDateTime, timeAgo } from "./shared";

export interface LocalReply {
  id: number;
  text: string;
  at: string;
  status?: string;
}

function replyStatusLabel(t: (text: string) => string, status?: string): string | null {
  if (!status) return null;
  if (status === "SENT") return t("Sent");
  if (status === "READY") return t("Queued");
  if (status === "FAILED") return t("Failed");
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
  const { t } = useT();
  const recipient = mail.from_name || mail.customer_name || mail.from_email || t("customer");

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {/* Header — clean single line */}
      <div className="shrink-0 border-b border-brand-border px-5 py-3">
        <div className="flex items-center gap-2">
          <h2 className="min-w-0 flex-1 truncate text-base font-semibold text-brand-dark">
            {mail.subject || t("(no subject)")}
          </h2>
          <span
            className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-semibold ${
              PRIORITY_TONE[mail.priority] || "bg-subtle text-brand-dark"
            }`}
          >
            {t(mail.priority)}
          </span>
          <button
            type="button"
            className="rounded-md p-1.5 text-brand-muted hover:bg-subtle hover:text-brand-dark"
            title={t("Schedule")}
          >
            <Calendar className="h-4 w-4" />
          </button>
          <button
            type="button"
            className="rounded-md p-1.5 text-brand-muted hover:bg-subtle hover:text-brand-dark"
            title={t("History")}
          >
            <Clock className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={onOpenContext}
            className="rounded-md p-1.5 text-brand-muted hover:bg-subtle hover:text-brand-dark 2xl:hidden"
            title={t("Procurement context")}
          >
            <PanelRightOpen className="h-4 w-4" />
          </button>
        </div>
        <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-brand-muted">
          <span className="font-medium text-brand-dark">
            {mail.from_name || mail.customer_name || t("Unknown")}
          </span>
          <span className="truncate">{mail.from_email}</span>
          {mail.linked_supplier_po_no && (
            <span className="text-signal-red">· {t("Ref {po}", { po: mail.linked_supplier_po_no })}</span>
          )}
        </div>
      </div>

      {/* Messages (scrolls) — chat bubbles with breathing room */}
      <div className="min-h-0 flex-1 space-y-5 overflow-y-auto bg-brand-surface/40 px-4 py-5 sm:px-6">
        {/* Incoming customer mail — left */}
        <div className="flex justify-start">
          <article className="max-w-[90%] rounded-xl border border-brand-border bg-card p-4 lg:max-w-[72ch]">
            <div className="mb-2 flex items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <span className="flex h-7 w-7 items-center justify-center rounded-md bg-signal-red text-[11px] font-semibold text-white">
                  {(mail.from_name || mail.from_email || "?").slice(0, 2).toUpperCase()}
                </span>
                <div className="leading-tight">
                  <div className="text-sm font-semibold text-brand-dark">
                    {mail.from_name || mail.customer_name || t("Unknown")}
                  </div>
                  <div className="text-[11px] text-brand-muted">{t("to ProcureDirect Support")}</div>
                </div>
              </div>
              <span className="shrink-0 text-[11px] text-brand-muted">
                {formatDateTime(mail.received_at)} · {timeAgo(mail.received_at)}
              </span>
            </div>
            <p className="whitespace-pre-wrap text-sm leading-relaxed text-brand-dark">
              {mail.body || t("(empty body)")}
            </p>
          </article>
        </div>

        {/* Outgoing replies — right */}
        {localReplies.map((reply) => (
          <div key={reply.id} className="flex justify-end">
            <article className="max-w-[90%] rounded-xl border border-brand-border bg-subtle p-4 lg:max-w-[72ch]">
              <div className="mb-1.5 flex items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold text-brand-dark">{t("You replied")}</span>
                  {replyStatusLabel(t, reply.status) && (
                    <span className="rounded-full border border-brand-border bg-card px-1.5 py-0.5 text-[10px] font-medium text-brand-muted">
                      {replyStatusLabel(t, reply.status)}
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

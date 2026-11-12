"use client";

import { useEffect, useState } from "react";
import { Mail, Paperclip } from "lucide-react";

import { AttachmentChips } from "@/components/attachments/Attachments";
import { useT } from "@/lib/i18n";
import type { CommunicationTask, TaskSourceMessage } from "@/lib/types";

function fmt(value?: string | null) {
  if (!value) return "";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? value : d.toLocaleString();
}

/**
 * "Source mail" block on the task detail: the mail / portal message the task
 * was assigned from — subject, sender, date, a body excerpt and the mail's own
 * attachments (downloadable; the files are referenced, not copied). Renders
 * nothing for tasks that were not created from a message.
 */
export default function SourceMailBlock({
  task,
  load,
  attachmentEndpoint,
}: {
  task: CommunicationTask;
  load: (taskId: number) => Promise<{ source: TaskSourceMessage | null }>;
  attachmentEndpoint: (attachmentId: number) => string;
}) {
  const { t } = useT();
  const [source, setSource] = useState<TaskSourceMessage | null>(null);
  const [expanded, setExpanded] = useState(false);
  const hasLink = !!(task.source_message_id || task.linked_mail_id);

  useEffect(() => {
    let alive = true;
    setSource(null);
    if (!hasLink) return;
    load(task.id)
      .then((r) => alive && setSource(r.source))
      .catch(() => alive && setSource(null));
    return () => {
      alive = false;
    };
  }, [task.id, hasLink, load]);

  if (!source) return null;
  const excerpt = source.body_excerpt || "";
  const long = excerpt.length > 400;
  const shown = expanded || !long ? excerpt : `${excerpt.slice(0, 400)}…`;

  return (
    <div className="rounded-lg border border-brand-border bg-subtle/60 p-3">
      <div className="mb-2 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-brand-muted">
        <Mail size={12} /> {t("Source mail")}
        {source.attachments.length > 0 && (
          <span className="ml-auto inline-flex items-center gap-0.5 font-normal normal-case">
            <Paperclip size={11} /> {source.attachments.length}
          </span>
        )}
      </div>
      <div className="text-sm font-medium text-brand-dark">{source.subject || t("(no subject)")}</div>
      <div className="mt-0.5 flex flex-wrap gap-x-3 text-[11px] text-brand-muted">
        {source.sender && <span>{t("From")}: {source.sender}</span>}
        {source.to && <span>{t("To")}: {source.to}</span>}
        {source.date && <span>{fmt(source.date)}</span>}
        {source.supplier_po_no && <span>{t("PO")}: {source.supplier_po_no}</span>}
      </div>
      {excerpt && (
        <p className="mt-2 whitespace-pre-wrap text-xs leading-relaxed text-brand-dark">{shown}</p>
      )}
      {(long || source.truncated) && (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="mt-1 text-[11px] font-medium text-signal-red hover:underline"
        >
          {expanded ? t("Show less") : t("Show more")}
        </button>
      )}
      <AttachmentChips items={source.attachments} endpointFor={attachmentEndpoint} />
    </div>
  );
}

"use client";

import { useEffect, useState } from "react";
import { useStore } from "@/lib/store";
import api from "@/lib/api";
import type { MailDraft, MailDraftPo } from "@/lib/types";
import { X, Loader2, Sparkles, Mail, Copy, Check, Send, ExternalLink } from "lucide-react";

type AnyDraft =
  | ({ kind: "single" } & MailDraft)
  | ({ kind: "po" } & MailDraftPo);

export default function MailDraftModal() {
  const id = useStore((s) => s.selectedRecordId);
  const poKey = useStore((s) => s.selectedPoKey);
  const closeSingle = useStore((s) => s.selectRecord);
  const closePo = useStore((s) => s.selectPoGroup);
  const refresh = useStore((s) => s.refresh);

  const [draft, setDraft] = useState<AnyDraft | null>(null);
  const [bodyText, setBodyText] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [status, setStatus] = useState<string>("DRAFT");
  const [viewMode, setViewMode] = useState<"html" | "text">("html");

  const isOpen = !!id || !!poKey;

  useEffect(() => {
    if (!isOpen) {
      setDraft(null);
      setBodyText("");
      setError(null);
      setCopied(false);
      setStatus("DRAFT");
      return;
    }

    setLoading(true);
    setDraft(null);
    setBodyText("");
    setError(null);
    setCopied(false);
    setStatus("DRAFT");

    const promise = poKey
      ? api
          .generatePoMailDraft({
            supplier_name: poKey.supplier_name,
            supplier_po_no: poKey.supplier_po_no,
          })
          .then<AnyDraft>((d) => ({ kind: "po", ...d }))
      : api
          .generateMailDraft(id as number)
          .then<AnyDraft>((d) => ({ kind: "single", ...d }));

    promise
      .then((nextDraft) => {
        setDraft(nextDraft);
        setBodyText(nextDraft.body);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [id, poKey, isOpen]);

  if (!isOpen) return null;

  const dismiss = () => {
    closeSingle(undefined);
    closePo(undefined);
  };

  const updateStatus = async (nextStatus: string) => {
    if (!draft) return;
    await api.updateMailHistoryStatus(draft.history_id, nextStatus);
    setStatus(nextStatus);
    await refresh();
    window.dispatchEvent(
      new CustomEvent("mail-history-updated", {
        detail: {
          history_id: draft.history_id,
          procurement_record_id: draft.procurement_record_id,
          supplier_po_no: "supplier_po_no" in draft ? draft.supplier_po_no : undefined,
          sent_status: nextStatus,
        },
      }),
    );
  };

  const copyDraft = async () => {
    if (!draft) return;
    await copyDraftBody(draft, bodyText);
    await updateStatus("COPIED");
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  const openOutlook = async () => {
    if (!draft) return;
    setError(null);
    await api.openOutlookDraft({
      history_id: draft.history_id,
      procurement_record_id: draft.procurement_record_id,
      supplier_po_no: "supplier_po_no" in draft ? draft.supplier_po_no : undefined,
      to_emails: draft.to_emails,
      cc_emails: draft.cc_emails,
      bcc_emails: draft.bcc_emails,
      escalation_emails: draft.escalation_emails,
      subject: draft.subject,
      body: bodyText,
      body_html: draft.kind === "po" ? draft.body_html : undefined,
    });
    await updateStatus("MAILTO_OPENED");
  };

  const markSent = async () => {
    await updateStatus("SENT_MANUALLY");
  };

  const isPo = draft?.kind === "po";

  return (
    <div className="fixed inset-0 z-50 bg-black/40 grid place-items-center p-4" onClick={dismiss}>
      <div
        className="bg-card rounded-lg shadow-xl w-full max-w-4xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="px-5 py-3 border-b border-brand-border flex items-center justify-between">
          <div className="flex items-center gap-2 flex-wrap">
            <Mail size={18} className="text-signal-red" />
            <div className="font-semibold">
              {isPo ? "PO-wise Mail Draft" : "Mail Draft"}
            </div>
            {draft && (
              <span
                className={
                  "chip ml-2 " +
                  (("ai_required" in draft && draft.ai_required)
                    ? "bg-purple-50 text-purple-700 border-purple-100"
                    : "bg-emerald-50 text-emerald-700 border-emerald-100")
                }
              >
                {"ai_required" in draft && draft.ai_required && <Sparkles size={12} />}{" "}
                {draft.mail_type}
              </span>
            )}
            {isPo && draft && (
              <>
                <span className="chip ml-1 bg-subtle text-brand-dark border-brand-border">
                  PO {(draft as MailDraftPo).supplier_po_no}
                </span>
                <span className="chip ml-1 bg-subtle text-brand-dark border-brand-border">
                  {(draft as MailDraftPo).material_count} material(s)
                </span>
                <span className="chip ml-1 bg-subtle text-brand-dark border-brand-border">
                  Signal {(draft as MailDraftPo).overall_signal}
                </span>
                {(draft as MailDraftPo).reused_existing && (
                  <span className="chip ml-1 bg-amber-50 text-amber-700 border-amber-200">
                    Reused today's draft
                  </span>
                )}
              </>
            )}
            {draft && <span className="chip ml-1">{status}</span>}
          </div>
          <button className="p-1 rounded hover:bg-subtle" onClick={dismiss}>
            <X size={18} />
          </button>
        </div>

        <div className="p-5 space-y-3 max-h-[75vh] overflow-y-auto">
          {loading && (
            <div className="flex items-center gap-2 text-sm text-brand-muted">
              <Loader2 size={14} className="animate-spin" /> Generating draft...
            </div>
          )}
          {error && <div className="text-sm text-signal-red">Error: {error}</div>}
          {draft && (
            <>
              {draft.notes && (
                <div className="bg-amber-50 border border-amber-200 text-amber-800 text-xs px-3 py-2 rounded">
                  {draft.notes}
                </div>
              )}
              <Field label="TO" value={joinEmails(draft.to_emails) || "(no email mapped)"} />
              <Field label="CC" value={joinEmails(draft.cc_emails)} />
              <Field label="BCC" value={joinEmails(draft.bcc_emails)} />
              <Field label="Escalation" value={joinEmails(draft.escalation_emails)} />
              <Field label="Subject" value={draft.subject} />

              {isPo && (
                <div>
                  <div className="text-[10px] uppercase tracking-wider text-brand-muted font-semibold mb-1">
                    Materials in this PO
                  </div>
                  <div className="overflow-x-auto border border-brand-border rounded">
                    <table className="min-w-full text-xs">
                      <thead className="bg-subtle">
                        <tr>
                          {["Sr", "CRM No", "Material Name", "PO Qty", "UOM", "Due", "Status", "Commit Date", "Remark"].map((h, i) => (
                            <th key={i} className="text-left px-2 py-1.5 font-semibold text-brand-dark border-b border-brand-border whitespace-nowrap">
                              {h}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {(draft as MailDraftPo).materials.map((m, idx) => (
                          <tr key={m.procurement_record_id} className="border-t border-brand-border">
                            <td className="px-2 py-1.5 whitespace-nowrap">{idx + 1}</td>
                            <td className="px-2 py-1.5 whitespace-nowrap font-mono">{m.crm_no}</td>
                            <td className="px-2 py-1.5 max-w-[260px] truncate" title={m.material_name}>{m.material_name}</td>
                            <td className="px-2 py-1.5 whitespace-nowrap">{m.po_qty ?? "-"}</td>
                            <td className="px-2 py-1.5 whitespace-nowrap">{m.uom ?? "-"}</td>
                            <td className="px-2 py-1.5 whitespace-nowrap">{m.due_date ?? "-"}</td>
                            <td className="px-2 py-1.5 whitespace-nowrap">{m.current_status ?? m.signal}</td>
                            <td className="px-2 py-1.5 whitespace-nowrap">{m.commitment?.commitment_date ?? "-"}</td>
                            <td className="px-2 py-1.5 max-w-[220px] truncate" title={m.commitment?.supplier_remark ?? ""}>
                              {m.commitment?.supplier_remark ?? "-"}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              <div>
                <div className="flex items-center justify-between mb-1">
                  <div className="text-[10px] uppercase tracking-wider text-brand-muted font-semibold">
                    Body
                  </div>
                  {isPo && (
                    <div className="text-[10px] flex items-center gap-1">
                      <button
                        className={
                          "px-2 py-0.5 rounded " +
                          (viewMode === "html" ? "bg-subtle" : "hover:bg-subtle")
                        }
                        onClick={() => setViewMode("html")}
                      >
                        HTML preview
                      </button>
                      <button
                        className={
                          "px-2 py-0.5 rounded " +
                          (viewMode === "text" ? "bg-subtle" : "hover:bg-subtle")
                        }
                        onClick={() => setViewMode("text")}
                      >
                        Edit text
                      </button>
                    </div>
                  )}
                </div>
                {isPo && viewMode === "html" ? (
                  <div
                    className="border border-brand-border rounded-md px-3 py-2 text-sm bg-card overflow-x-auto"
                    dangerouslySetInnerHTML={{ __html: (draft as MailDraftPo).body_html }}
                  />
                ) : (
                  <textarea
                    className="w-full border border-brand-border rounded-md px-3 py-2 text-sm font-mono leading-relaxed h-64"
                    value={bodyText}
                    onChange={(event) => setBodyText(event.target.value)}
                  />
                )}
              </div>
            </>
          )}
        </div>

        {draft && (
          <div className="px-5 py-3 border-t border-brand-border flex flex-wrap items-center justify-end gap-2">
            {isPo && (
              <div className="mr-auto text-[11px] text-brand-muted">
                Open Outlook creates a native Outlook draft with the HTML table body.
              </div>
            )}
            <button className="btn-ghost" onClick={copyDraft}>
              {copied ? <Check size={14} /> : <Copy size={14} />} {copied ? "Copied" : isPo ? "Copy HTML Body" : "Copy"}
            </button>
            <button className="btn-ghost" onClick={openOutlook}>
              <ExternalLink size={14} /> Open Outlook
            </button>
            <button className="btn-primary" onClick={markSent}>
              <Send size={14} /> Mark Sent
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

async function copyDraftBody(draft: AnyDraft, bodyText: string) {
  if (
    draft.kind === "po" &&
    draft.body_html &&
    typeof window !== "undefined" &&
    "ClipboardItem" in window &&
    typeof navigator !== "undefined" &&
    navigator.clipboard &&
    "write" in navigator.clipboard
  ) {
    const item = new window.ClipboardItem({
      "text/html": new Blob([draft.body_html], { type: "text/html" }),
      "text/plain": new Blob([bodyText], { type: "text/plain" }),
    });
    await navigator.clipboard.write([item]);
    return;
  }

  if (draft.kind === "po") {
    await navigator.clipboard.writeText(bodyText);
    return;
  }

  await navigator.clipboard.writeText(`Subject: ${draft.subject}\n\n${bodyText}`);
}

function joinEmails(values: string[]) {
  return values.filter(Boolean).join(", ");
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-brand-muted font-semibold mb-1">
        {label}
      </div>
      <div className="border border-brand-border rounded-md px-3 py-1.5 text-sm bg-subtle break-words">
        {value || "-"}
      </div>
    </div>
  );
}

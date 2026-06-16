"use client";

import { useCallback, useEffect, useState } from "react";
import { Check, Loader2, MailCheck, Trash2 } from "lucide-react";

import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { OutboxDraft } from "@/lib/types";

export default function ApprovalsPage() {
  const { hasRole } = useAuth();
  const [drafts, setDrafts] = useState<OutboxDraft[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    api
      .listOutboxDrafts()
      .then(setDrafts)
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (hasRole("manager")) load();
    else setLoading(false);
  }, [hasRole, load]);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 2500);
    return () => clearTimeout(t);
  }, [toast]);

  if (!hasRole("manager")) {
    return (
      <div className="rounded-xl border border-brand-border bg-white p-8 text-center text-sm text-brand-muted">
        <MailCheck className="mx-auto mb-2 h-6 w-6 text-brand-muted" />
        You need the <strong>manager</strong> role to review outbound approvals.
      </div>
    );
  }

  const act = (id: number, fn: () => Promise<unknown>, msg: string) => {
    setBusyId(id);
    setError(null);
    fn()
      .then(() => {
        setDrafts((prev) => prev.filter((d) => d.id !== id));
        setToast(msg);
      })
      .catch((e) => setError((e as Error).message))
      .finally(() => setBusyId(null));
  };

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-brand-dark">Outbound Approvals</h1>
          <p className="text-xs text-brand-muted">
            Review system-drafted mails (e.g. auto-acknowledgements) before they are sent.
          </p>
        </div>
        {toast && (
          <span className="rounded-md bg-brand-dark px-3 py-1.5 text-xs text-white">{toast}</span>
        )}
      </div>

      {error && (
        <div className="rounded-md bg-red-50 px-3 py-2 text-xs text-signal-red">{error}</div>
      )}

      {loading ? (
        <div className="rounded-xl border border-brand-border bg-white p-8 text-center text-sm text-brand-muted">
          Loading…
        </div>
      ) : drafts.length === 0 ? (
        <div className="rounded-xl border border-brand-border bg-white p-10 text-center text-sm text-brand-muted">
          <MailCheck className="mx-auto mb-2 h-6 w-6 text-emerald-500" />
          Nothing waiting for approval.
        </div>
      ) : (
        <div className="space-y-3">
          {drafts.map((d) => (
            <article key={d.id} className="rounded-xl border border-brand-border bg-white p-4">
              <div className="mb-2 flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="truncate text-sm font-semibold text-brand-dark">
                    {d.subject || "(no subject)"}
                  </div>
                  <div className="mt-0.5 flex flex-wrap items-center gap-x-2 text-xs text-brand-muted">
                    <span className="rounded bg-gray-100 px-1.5 py-0.5">{d.mail_type || "DRAFT"}</span>
                    <span>To: {d.to_emails.join(", ") || d.receiver_email || "—"}</span>
                    {d.supplier_po_no && <span className="text-signal-red">· PO {d.supplier_po_no}</span>}
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-1.5">
                  <button
                    onClick={() => act(d.id, () => api.approveMessage(d.id), "Approved — queued to send.")}
                    disabled={busyId === d.id}
                    className="inline-flex items-center gap-1 rounded-md bg-emerald-600 px-2.5 py-1.5 text-xs font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
                  >
                    {busyId === d.id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />}
                    Approve &amp; send
                  </button>
                  <button
                    onClick={() => act(d.id, () => api.discardMessage(d.id), "Draft discarded.")}
                    disabled={busyId === d.id}
                    className="inline-flex items-center gap-1 rounded-md border border-brand-border px-2.5 py-1.5 text-xs text-brand-muted hover:bg-red-50 hover:text-signal-red disabled:opacity-50"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                    Discard
                  </button>
                </div>
              </div>
              <p className="whitespace-pre-wrap rounded-md bg-brand-surface p-3 text-sm leading-relaxed text-brand-dark">
                {d.body || "(empty body)"}
              </p>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}

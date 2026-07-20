"use client";

import { useEffect, useState } from "react";
import { AlertCircle, CheckCircle2, Loader2, Send } from "lucide-react";

import { api } from "@/lib/api";
import type { PortalPo } from "@/lib/types";

/** Supplier "Raise an issue" — creates a task for the buyer team (routed to
 *  the PO's owner when a PO is selected) and notifies them instantly. */
export default function PortalIssuesPage() {
  const [subject, setSubject] = useState("");
  const [description, setDescription] = useState("");
  const [poNo, setPoNo] = useState("");
  const [pos, setPos] = useState<PortalPo[]>([]);
  const [sending, setSending] = useState(false);
  const [done, setDone] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.portalPos().then((r) => setPos(r.items)).catch(() => {});
  }, []);

  const submit = async () => {
    if (subject.trim().length < 3 || sending) return;
    setSending(true);
    setError(null);
    try {
      const res = await api.portalRaiseIssue({
        subject: subject.trim(),
        description: description.trim() || undefined,
        supplier_po_no: poNo || undefined,
      });
      setDone(res.task_id);
      setSubject("");
      setDescription("");
      setPoNo("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="page-stack">
      <div className="page-header">
        <div>
          <h1 className="page-title">Raise an Issue</h1>
          <p className="page-subtitle">
            Tell your buyer team about a problem — quality, documents, payment, anything. They are notified immediately.
          </p>
        </div>
        <span className="grid h-9 w-9 place-items-center rounded-lg bg-red-50 text-signal-red"><AlertCircle size={17} /></span>
      </div>

      {done !== null && (
        <div className="flex items-center gap-2 rounded-md border border-emerald-100 bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
          <CheckCircle2 size={15} /> Issue submitted — the buyer team has been notified (ticket #{done}).
        </div>
      )}
      {error && <div className="rounded-md bg-red-50 px-3 py-2 text-xs text-signal-red">{error}</div>}

      <div className="card max-w-2xl space-y-4 p-5">
        <label className="block text-sm">
          <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-brand-muted">Subject *</span>
          <input
            className="input w-full"
            maxLength={200}
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            placeholder="e.g. Drawing revision missing for PO 2627-002342"
          />
        </label>

        <label className="block text-sm">
          <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-brand-muted">Related PO (optional)</span>
          <select className="input w-full bg-card" value={poNo} onChange={(e) => setPoNo(e.target.value)}>
            <option value="">— No specific PO —</option>
            {pos.map((p) => (
              <option key={p.supplier_po_no} value={p.supplier_po_no}>
                {p.po_ref || p.supplier_po_no}
              </option>
            ))}
          </select>
        </label>

        <label className="block text-sm">
          <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-brand-muted">Details</span>
          <textarea
            className="input w-full resize-none"
            rows={5}
            maxLength={2000}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Describe the issue — what happened, what you need from the buyer team, any deadlines…"
          />
        </label>

        <div className="flex justify-end">
          <button
            className="btn-primary"
            disabled={subject.trim().length < 3 || sending}
            onClick={() => void submit()}
          >
            {sending ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />} Submit issue
          </button>
        </div>
      </div>
    </div>
  );
}

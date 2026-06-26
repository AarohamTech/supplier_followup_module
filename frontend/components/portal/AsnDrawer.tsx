"use client";

import { useState } from "react";
import { AlertTriangle, Send, X } from "lucide-react";

import { api } from "@/lib/api";
import { ADVANCE_STAGES, stageMeta } from "@/lib/asn";
import { fmtDate } from "@/lib/format";
import type { Asn } from "@/lib/types";

export default function AsnDrawer({
  asn,
  onClose,
  onUpdated,
  staff = false,
}: {
  asn: Asn;
  onClose: () => void;
  onUpdated: (asn: Asn) => void;
  // staff=true → drive the internal /api/asns endpoints instead of the portal ones.
  staff?: boolean;
}) {
  const addEvent = staff ? api.addAsnEvent : api.addPortalAsnEvent;
  const updateAsn = staff ? api.updateAsn : api.updatePortalAsn;
  const meta = stageMeta(asn.status);
  const [stage, setStage] = useState<string>("");
  const [location, setLocation] = useState("");
  const [note, setNote] = useState("");
  const [alert, setAlert] = useState(false);
  const [alertReason, setAlertReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isClosed = asn.status === "DELIVERED" || asn.status === "CANCELLED";

  const advance = async () => {
    if (!stage) {
      setError("Choose a stage.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const updated = await addEvent(asn.id, {
        stage,
        location: location || null,
        note: note || null,
        alert,
        alert_reason: alert ? alertReason || "Delayed" : null,
      });
      onUpdated(updated);
      setStage("");
      setLocation("");
      setNote("");
      setAlert(false);
      setAlertReason("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const submitDraft = async () => {
    setBusy(true);
    setError(null);
    try {
      const updated = await updateAsn(asn.id, { submit: true });
      onUpdated(updated);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/40" onClick={onClose}>
      <div
        className="h-full w-full max-w-md overflow-y-auto bg-white shadow-2xl animate-fade-in-up"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-brand-border bg-white px-5 py-3">
          <div>
            <div className="font-semibold text-brand-dark">{asn.asn_no}</div>
            <div className="text-xs text-brand-muted">PO {asn.supplier_po_no}</div>
          </div>
          <div className="flex items-center gap-2">
            <span className={"badge " + meta.badge}>{asn.status_label || meta.label}</span>
            <button className="p-1 rounded hover:bg-gray-100" onClick={onClose}><X size={18} /></button>
          </div>
        </div>

        <div className="space-y-5 p-5">
          {error && <div className="rounded-md bg-red-50 px-3 py-2 text-xs text-signal-red">{error}</div>}

          {asn.alert && (
            <div className="flex items-start gap-2 rounded-md bg-red-50 px-3 py-2 text-xs text-signal-red">
              <AlertTriangle size={14} className="mt-0.5 shrink-0" />
              <span>{asn.alert_reason || "Shipment flagged as delayed / needs attention."}</span>
            </div>
          )}

          {/* Progress */}
          <div>
            <div className="mb-1 flex items-center justify-between text-xs">
              <span className="font-medium text-brand-dark">{meta.label}</span>
              <span className="text-brand-muted">{asn.progress_percent}%</span>
            </div>
            <div className="h-2 w-full overflow-hidden rounded-full bg-gray-100">
              <div className={"h-full rounded-full " + meta.bar} style={{ width: `${asn.progress_percent}%` }} />
            </div>
          </div>

          {/* Details */}
          <dl className="grid grid-cols-2 gap-3 text-sm">
            <Detail label="Carrier" value={asn.carrier_name} />
            <Detail label="Tracking" value={asn.tracking_no} />
            <Detail label="Mode" value={asn.transport_mode} />
            <Detail label="Route" value={asn.origin || asn.destination ? `${asn.origin || "—"} → ${asn.destination || "—"}` : null} />
            <Detail label="Dispatch" value={fmtDate(asn.dispatch_date)} />
            <Detail label="ETA" value={fmtDate(asn.eta)} />
          </dl>

          {/* Items */}
          {asn.items.length > 0 && (
            <div>
              <div className="mb-1 text-[10px] uppercase tracking-wider text-brand-muted font-semibold">Shipped Items</div>
              <div className="rounded-md border border-brand-border divide-y divide-brand-border">
                {asn.items.map((it) => (
                  <div key={it.id} className="px-3 py-2 text-sm">
                    <div className="truncate font-medium text-brand-dark">{it.material_name}</div>
                    <div className="mt-0.5 flex flex-wrap gap-x-4 gap-y-0.5 text-xs text-brand-muted">
                      <span>PO: {it.po_qty ?? "—"} {it.uom || ""}</span>
                      <span>Shipped: <span className="font-medium text-brand-dark">{it.qty_shipped ?? "—"} {it.uom || ""}</span></span>
                      {it.invoice_no && <span>Invoice: {it.invoice_no}</span>}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Timeline */}
          <div>
            <div className="mb-2 text-[10px] uppercase tracking-wider text-brand-muted font-semibold">Tracking Timeline</div>
            {asn.events.length === 0 ? (
              <div className="text-xs text-brand-muted">No tracking updates yet.</div>
            ) : (
              <ol className="relative ml-2 border-l border-brand-border">
                {[...asn.events].reverse().map((ev) => (
                  <li key={ev.id} className="mb-4 ml-4">
                    <span className="absolute -left-1.5 mt-1 h-3 w-3 rounded-full bg-signal-red" />
                    <div className="text-sm font-medium text-brand-dark">{ev.status_label || ev.stage}</div>
                    <div className="text-xs text-brand-muted">
                      {fmtDate(ev.occurred_at)}{ev.location ? ` · ${ev.location}` : ""}
                    </div>
                    {ev.note && <div className="text-xs text-brand-dark/80">{ev.note}</div>}
                  </li>
                ))}
              </ol>
            )}
          </div>

          {/* Actions */}
          {asn.status === "DRAFT" && (
            <button className="btn-primary w-full" disabled={busy} onClick={submitDraft}>
              <Send size={14} /> Submit ASN
            </button>
          )}

          {!isClosed && asn.status !== "DRAFT" && (
            <div className="rounded-lg border border-brand-border p-3 space-y-3">
              <div className="text-[10px] uppercase tracking-wider text-brand-muted font-semibold">Add tracking update</div>
              <select className="input" value={stage} onChange={(e) => setStage(e.target.value)}>
                <option value="">Select stage…</option>
                {ADVANCE_STAGES.map((s) => (
                  <option key={s} value={s}>{stageMeta(s).label}</option>
                ))}
              </select>
              <input className="input" placeholder="Location (optional)" value={location} onChange={(e) => setLocation(e.target.value)} />
              <input className="input" placeholder="Note (optional)" value={note} onChange={(e) => setNote(e.target.value)} />
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={alert} onChange={(e) => setAlert(e.target.checked)} />
                Flag as delayed / needs attention
              </label>
              {alert && (
                <input className="input" placeholder="Reason (e.g. Documentation Missing)" value={alertReason} onChange={(e) => setAlertReason(e.target.value)} />
              )}
              <button className="btn-primary w-full" disabled={busy} onClick={advance}>
                {busy ? "Saving…" : "Add update"}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Detail({ label, value }: { label: string; value?: string | null }) {
  return (
    <div>
      <dt className="text-[10px] uppercase tracking-wider text-brand-muted font-semibold">{label}</dt>
      <dd className="text-sm text-brand-dark">{value || "—"}</dd>
    </div>
  );
}

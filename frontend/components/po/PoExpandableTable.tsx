"use client";

import { Fragment, useState } from "react";
import { Ban, ChevronDown, ChevronRight, Loader2 } from "lucide-react";

import { overdueDays } from "@/lib/format";
import type { EmployeePo, PoDetail, PoMessage } from "@/lib/types";

const SIGNAL_CLASS: Record<string, string> = {
  GREEN: "bg-emerald-50 text-emerald-700 ring-emerald-100",
  YELLOW: "bg-amber-50 text-amber-700 ring-amber-100",
  RED: "bg-red-50 text-signal-red ring-red-100",
  BLACK: "bg-ink text-white ring-gray-700",
};

function SignalChip({ signal }: { signal?: string | null }) {
  const s = (signal || "").toUpperCase();
  const cls = SIGNAL_CLASS[s] || "bg-subtle text-brand-muted ring-gray-200";
  return (
    <span className={`inline-flex rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase ring-1 ring-inset ${cls}`}>
      {s || "—"}
    </span>
  );
}

function fmtDate(d?: string | null) {
  if (!d) return "—";
  const dt = new Date(d);
  return isNaN(dt.getTime()) ? "—" : dt.toLocaleDateString();
}

function fmtDateTime(d?: string | null) {
  if (!d) return "—";
  const dt = new Date(d);
  return isNaN(dt.getTime()) ? "—" : dt.toLocaleString();
}

// PO numbers are recycled across suppliers, so scope every key by (supplier, PO).
function poKey(p: EmployeePo): string {
  return `${(p.supplier_name || "").toUpperCase()}|${p.supplier_po_no}`;
}

function MessageRow({ m }: { m: PoMessage }) {
  const inbound = m.direction === "INCOMING";
  const when = inbound ? m.received_at || m.created_at : m.sent_at || m.created_at;
  return (
    <div className="border-t border-brand-border/60 py-2 first:border-t-0">
      <div className="flex flex-wrap items-center gap-2">
        <span className={`inline-flex rounded px-1.5 py-0.5 text-[9px] font-semibold uppercase ${inbound ? "bg-blue-50 text-blue-700" : "bg-emerald-50 text-emerald-700"}`}>
          {inbound ? "In" : "Out"}
        </span>
        <span className="text-xs font-medium text-brand-dark">{m.subject || "(no subject)"}</span>
        {m.status && <span className="text-[10px] uppercase text-brand-muted">{m.status}</span>}
        <span className="ml-auto text-[11px] text-brand-muted">{fmtDateTime(when)}</span>
      </div>
      {(m.sender_email || m.receiver_email) && (
        <div className="mt-0.5 text-[11px] text-brand-muted">
          {inbound ? `from ${m.sender_email || "—"}` : `to ${m.receiver_email || "—"}`}
        </div>
      )}
      {m.snippet && <div className="mt-1 text-xs text-brand-dark/80 line-clamp-3">{m.snippet}</div>}
    </div>
  );
}

export default function PoExpandableTable({
  pos,
  loadDetail,
  requestCancel,
}: {
  pos: EmployeePo[];
  loadDetail: (po: EmployeePo) => Promise<PoDetail>;
  requestCancel: (po: EmployeePo) => Promise<void>;
}) {
  const [open, setOpen] = useState<string | null>(null);
  const [detail, setDetail] = useState<Record<string, PoDetail>>({});
  const [loading, setLoading] = useState<string | null>(null);
  const [cancelOverride, setCancelOverride] = useState<Record<string, string>>({});
  const [confirmPo, setConfirmPo] = useState<EmployeePo | null>(null);
  const [requesting, setRequesting] = useState(false);
  const [cancelError, setCancelError] = useState<string | null>(null);

  const cancelStatusOf = (p: EmployeePo): string =>
    (cancelOverride[poKey(p)] ?? p.cancellation_status ?? "").toUpperCase();

  const toggle = async (p: EmployeePo) => {
    const key = poKey(p);
    if (open === key) {
      setOpen(null);
      return;
    }
    setOpen(key);
    if (!detail[key]) {
      setLoading(key);
      try {
        const d = await loadDetail(p);
        setDetail((cur) => ({ ...cur, [key]: d }));
      } catch {
        /* ignore */
      } finally {
        setLoading(null);
      }
    }
  };

  async function confirmCancel() {
    if (!confirmPo) return;
    setRequesting(true);
    setCancelError(null);
    try {
      await requestCancel(confirmPo);
      setCancelOverride((cur) => ({ ...cur, [poKey(confirmPo)]: "PENDING" }));
      setConfirmPo(null);
    } catch (e) {
      setCancelError((e as Error).message);
    } finally {
      setRequesting(false);
    }
  }

  if (!pos.length) {
    return <div className="card p-6 text-center text-sm text-brand-muted">No purchase orders to show.</div>;
  }

  return (
    <>
      <div className="card overflow-x-auto">
        <table className="w-full min-w-[760px] text-sm">
          <thead className="bg-subtle text-left text-[11px] uppercase tracking-wider text-brand-muted">
            <tr>
              <th className="w-8 px-3 py-2" />
              <th className="px-3 py-2">Signal</th>
              <th className="px-3 py-2">PO No</th>
              <th className="px-3 py-2">Vendor</th>
              <th className="px-3 py-2">Materials</th>
              <th className="px-3 py-2">Earliest Ship</th>
              <th className="px-3 py-2">Status</th>
              <th className="px-3 py-2 text-right">Cancel</th>
            </tr>
          </thead>
          <tbody>
            {pos.map((p) => {
              const key = poKey(p);
              const isOpen = open === key;
              const d = detail[key];
              return (
                <Fragment key={key}>
                  <tr className="cursor-pointer border-t border-brand-border hover:bg-subtle" onClick={() => toggle(p)}>
                    <td className="px-3 py-2 text-brand-muted">
                      {isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                    </td>
                    <td className="px-3 py-2"><SignalChip signal={p.overall_signal} /></td>
                    <td className="px-3 py-2 font-medium text-brand-dark">
                      {p.supplier_po_no}
                      {p.escalated && (
                        <span className="ml-2 rounded bg-red-50 px-1.5 py-0.5 text-[10px] font-semibold text-signal-red">ESCALATED</span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-brand-dark">{p.supplier_name || "—"}</td>
                    <td className="px-3 py-2">{p.material_count}</td>
                    <td className="px-3 py-2">{fmtDate(p.earliest_shipment_date)}</td>
                    <td className="px-3 py-2">{p.po_status || "—"}</td>
                    <td className="px-3 py-2 text-right" onClick={(e) => e.stopPropagation()}>
                      {cancelStatusOf(p) === "CANCELLED" ? (
                        <span className="inline-flex rounded-full bg-red-50 px-2 py-0.5 text-[10px] font-semibold uppercase text-signal-red ring-1 ring-inset ring-red-100">Cancelled</span>
                      ) : cancelStatusOf(p) === "PENDING" ? (
                        <span className="inline-flex rounded-full bg-amber-50 px-2 py-0.5 text-[10px] font-semibold uppercase text-amber-700 ring-1 ring-inset ring-amber-100">Pending cancellation</span>
                      ) : (
                        <button
                          type="button"
                          onClick={() => { setConfirmPo(p); setCancelError(null); }}
                          className="inline-flex items-center gap-1 rounded-md border border-brand-border px-2 py-1 text-[11px] font-medium text-signal-red hover:bg-red-50"
                        >
                          <Ban size={12} /> Request cancel
                        </button>
                      )}
                    </td>
                  </tr>
                  {isOpen && (
                    <tr className="bg-subtle/60">
                      <td colSpan={8} className="px-3 py-3">
                        {loading === key ? (
                          <div className="flex items-center gap-2 text-xs text-brand-muted">
                            <Loader2 size={14} className="animate-spin" /> Loading details…
                          </div>
                        ) : d ? (
                          <div className="space-y-4">
                            {/* Materials */}
                            <div>
                              <div className="mb-1 text-[11px] font-semibold uppercase text-brand-muted">Materials</div>
                              {d.materials.length ? (
                                <table className="w-full text-xs">
                                  <thead className="text-left text-[10px] uppercase text-brand-muted">
                                    <tr>
                                      <th className="px-2 py-1">Material</th>
                                      <th className="px-2 py-1">UoM</th>
                                      <th className="px-2 py-1">Qty</th>
                                      <th className="px-2 py-1">Signal</th>
                                      <th className="px-2 py-1">Ship Date</th>
                                      <th className="px-2 py-1">Overdue</th>
                                      <th className="px-2 py-1">Commitment</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {d.materials.map((m) => (
                                      <tr key={m.procurement_record_id} className="border-t border-brand-border/60">
                                        <td className="px-2 py-1 text-brand-dark">{m.material_name}</td>
                                        <td className="px-2 py-1">{m.uom || "—"}</td>
                                        <td className="px-2 py-1">{m.qty ?? "—"}</td>
                                        <td className="px-2 py-1"><SignalChip signal={m.signal} /></td>
                                        <td className="px-2 py-1">{fmtDate(m.shipment_date)}</td>
                                        <td className="px-2 py-1">
                                          {overdueDays(m.shipment_date) > 0 ? (
                                            <span className="font-semibold text-signal-red">{overdueDays(m.shipment_date)}d</span>
                                          ) : (
                                            <span className="text-brand-muted">—</span>
                                          )}
                                        </td>
                                        <td className="px-2 py-1">{fmtDate(m.commitment_date)}</td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              ) : (
                                <div className="text-xs text-brand-muted">No materials.</div>
                              )}
                            </div>

                            {/* Communication */}
                            <div>
                              <div className="mb-1 text-[11px] font-semibold uppercase text-brand-muted">
                                Communication ({d.messages.length})
                              </div>
                              {d.messages.length ? (
                                <div className="rounded-md border border-brand-border/60 bg-card px-3">
                                  {d.messages.map((m) => <MessageRow key={m.id} m={m} />)}
                                </div>
                              ) : (
                                <div className="text-xs text-brand-muted">No messages on this PO yet.</div>
                              )}
                            </div>
                          </div>
                        ) : (
                          <div className="text-xs text-brand-muted">Could not load details.</div>
                        )}
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>

      {confirmPo && (
        <div className="fixed inset-0 z-50 bg-black/40 grid place-items-center p-4" onClick={() => !requesting && setConfirmPo(null)}>
          <div className="bg-card rounded-lg shadow-xl w-full max-w-sm" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
            <div className="border-b border-brand-border px-5 py-3 font-semibold text-sm">Request PO cancellation</div>
            <div className="px-5 py-4 space-y-2 text-sm">
              <p>
                Raise a cancellation for PO <span className="font-semibold">{confirmPo.supplier_po_no}</span>
                {confirmPo.supplier_name ? <> ({confirmPo.supplier_name})</> : null}?
              </p>
              <p className="text-xs text-brand-muted">
                The PO will be marked <span className="font-medium">Pending cancellation</span> until it is confirmed.
              </p>
              {cancelError && <p className="text-xs text-signal-red">{cancelError}</p>}
            </div>
            <div className="border-t border-brand-border px-5 py-3 flex items-center justify-end gap-2">
              <button type="button" disabled={requesting} onClick={() => setConfirmPo(null)} className="btn-outline text-xs">Cancel</button>
              <button
                type="button"
                disabled={requesting}
                onClick={confirmCancel}
                className="inline-flex items-center gap-1 rounded-md bg-signal-red px-3 py-1.5 text-xs font-semibold text-white hover:opacity-90 disabled:opacity-60"
              >
                {requesting ? <Loader2 size={13} className="animate-spin" /> : <Ban size={13} />}
                {requesting ? "Requesting…" : "Yes, request cancellation"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

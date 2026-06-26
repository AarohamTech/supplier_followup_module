"use client";

import { useEffect, useMemo, useState } from "react";
import { Save, Send, X } from "lucide-react";

import { api } from "@/lib/api";
import { TRANSPORT_MODES } from "@/lib/asn";
import type { Asn, AsnItemInput, PortalPo, PortalPoMaterial } from "@/lib/types";

interface LineDraft extends AsnItemInput {
  _selected: boolean;
}

export default function AsnCreateModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (asn: Asn) => void;
}) {
  const [pos, setPos] = useState<PortalPo[]>([]);
  const [poNo, setPoNo] = useState("");
  const [lines, setLines] = useState<LineDraft[]>([]);
  const [loadingMaterials, setLoadingMaterials] = useState(false);

  const [carrier, setCarrier] = useState("");
  const [tracking, setTracking] = useState("");
  const [mode, setMode] = useState("");
  const [origin, setOrigin] = useState("");
  const [destination, setDestination] = useState("");
  const [dispatchDate, setDispatchDate] = useState("");
  const [eta, setEta] = useState("");
  const [remarks, setRemarks] = useState("");

  const [busy, setBusy] = useState<"draft" | "submit" | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const res = await api.portalPos();
        setPos(res.items);
      } catch (e) {
        setError((e as Error).message);
      }
    })();
  }, []);

  useEffect(() => {
    if (!poNo) {
      setLines([]);
      return;
    }
    let cancelled = false;
    setLoadingMaterials(true);
    (async () => {
      try {
        const materials: PortalPoMaterial[] = await api.portalPoMaterials(poNo);
        if (cancelled) return;
        setLines(
          materials.map((m) => ({
            _selected: true,
            procurement_record_id: m.procurement_record_id,
            material_name: m.material_name,
            po_qty: m.qty ?? null,
            qty_shipped: m.qty ?? null,
            uom: m.uom ?? null,
            invoice_no: null,
          })),
        );
      } catch (e) {
        if (!cancelled) setError((e as Error).message);
      } finally {
        if (!cancelled) setLoadingMaterials(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [poNo]);

  const selectedLines = useMemo(() => lines.filter((l) => l._selected), [lines]);

  const setLine = (idx: number, patch: Partial<LineDraft>) =>
    setLines((prev) => prev.map((l, i) => (i === idx ? { ...l, ...patch } : l)));

  const save = async (submit: boolean) => {
    setError(null);
    if (!poNo) {
      setError("Select a PO reference.");
      return;
    }
    if (submit && selectedLines.length === 0) {
      setError("Add at least one shipped line to submit.");
      return;
    }
    setBusy(submit ? "submit" : "draft");
    try {
      const asn = await api.createPortalAsn({
        supplier_po_no: poNo,
        carrier_name: carrier || null,
        tracking_no: tracking || null,
        transport_mode: mode || null,
        origin: origin || null,
        destination: destination || null,
        dispatch_date: dispatchDate || null,
        eta: eta || null,
        remarks: remarks || null,
        items: selectedLines.map(({ _selected, ...rest }) => rest),
        submit,
      });
      onCreated(asn);
    } catch (e) {
      setError((e as Error).message);
      setBusy(null);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/40 grid place-items-center p-4" onClick={onClose}>
      <div
        className="bg-white rounded-lg shadow-xl w-full max-w-2xl max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="px-5 py-3 border-b border-brand-border flex items-center justify-between sticky top-0 bg-white">
          <div className="font-semibold">Create New ASN</div>
          <button className="p-1 rounded hover:bg-gray-100" onClick={onClose}><X size={18} /></button>
        </div>

        <div className="p-5 space-y-4">
          {error && <div className="text-sm text-signal-red bg-red-50 border border-red-100 rounded-md px-3 py-2">{error}</div>}

          <Field label="PO Reference *">
            <select className="input" value={poNo} onChange={(e) => setPoNo(e.target.value)}>
              <option value="">Select a purchase order</option>
              {pos.map((p) => (
                <option key={p.supplier_po_no} value={p.supplier_po_no}>
                  {p.supplier_po_no}{p.crm_no ? ` · CRM ${p.crm_no}` : ""} ({p.material_count} material{p.material_count === 1 ? "" : "s"})
                </option>
              ))}
            </select>
          </Field>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <Field label="Carrier"><input className="input" value={carrier} onChange={(e) => setCarrier(e.target.value)} placeholder="e.g. Maersk Line" /></Field>
            <Field label="Tracking No"><input className="input" value={tracking} onChange={(e) => setTracking(e.target.value)} placeholder="e.g. MSK-L81122" /></Field>
            <Field label="Mode">
              <select className="input" value={mode} onChange={(e) => setMode(e.target.value)}>
                <option value="">—</option>
                {TRANSPORT_MODES.map((m) => <option key={m} value={m}>{m}</option>)}
              </select>
            </Field>
            <Field label="Dispatch Date"><input type="date" className="input" value={dispatchDate} onChange={(e) => setDispatchDate(e.target.value)} /></Field>
            <Field label="Origin"><input className="input" value={origin} onChange={(e) => setOrigin(e.target.value)} /></Field>
            <Field label="Destination"><input className="input" value={destination} onChange={(e) => setDestination(e.target.value)} /></Field>
            <Field label="Estimated Delivery (ETA)"><input type="date" className="input" value={eta} onChange={(e) => setEta(e.target.value)} /></Field>
            <Field label="Remarks"><input className="input" value={remarks} onChange={(e) => setRemarks(e.target.value)} /></Field>
          </div>

          <div>
            <div className="mb-1 text-[10px] uppercase tracking-wider text-brand-muted font-semibold">Shipped Materials</div>
            {!poNo && <div className="empty-state">Select a PO to load its materials.</div>}
            {poNo && loadingMaterials && <div className="empty-state">Loading materials…</div>}
            {poNo && !loadingMaterials && lines.length === 0 && (
              <div className="empty-state">No materials found for this PO.</div>
            )}
            {lines.length > 0 && (
              <div className="table-shell">
                <table className="min-w-full text-sm">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-3 py-2 text-left table-header">Ship</th>
                      <th className="px-3 py-2 text-left table-header">Material</th>
                      <th className="px-3 py-2 text-left table-header">PO Qty</th>
                      <th className="px-3 py-2 text-left table-header">Qty Shipped</th>
                      <th className="px-3 py-2 text-left table-header">UOM</th>
                      <th className="px-3 py-2 text-left table-header">Invoice No</th>
                    </tr>
                  </thead>
                  <tbody>
                    {lines.map((l, idx) => (
                      <tr key={idx} className="border-t border-brand-border">
                        <td className="px-3 py-2">
                          <input type="checkbox" checked={l._selected} onChange={(e) => setLine(idx, { _selected: e.target.checked })} />
                        </td>
                        <td className="px-3 py-2">{l.material_name}</td>
                        <td className="px-3 py-2 text-brand-muted whitespace-nowrap">
                          {l.po_qty ?? "—"} {l.uom || ""}
                        </td>
                        <td className="px-3 py-2">
                          <input
                            type="number"
                            className="input py-1 w-24"
                            value={l.qty_shipped ?? ""}
                            onChange={(e) => setLine(idx, { qty_shipped: e.target.value === "" ? null : Number(e.target.value) })}
                          />
                        </td>
                        <td className="px-3 py-2 text-xs text-brand-muted">{l.uom || "—"}</td>
                        <td className="px-3 py-2">
                          <input
                            type="text"
                            className="input py-1 w-28"
                            placeholder="INV-…"
                            value={l.invoice_no ?? ""}
                            onChange={(e) => setLine(idx, { invoice_no: e.target.value || null })}
                          />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>

        <div className="px-5 py-3 border-t border-brand-border flex items-center justify-end gap-2 sticky bottom-0 bg-white">
          <button className="btn-ghost" onClick={onClose}>Cancel</button>
          <button className="btn-outline" disabled={busy !== null} onClick={() => save(false)}>
            <Save size={14} /> {busy === "draft" ? "Saving…" : "Save Draft"}
          </button>
          <button className="btn-primary" disabled={busy !== null} onClick={() => save(true)}>
            <Send size={14} /> {busy === "submit" ? "Submitting…" : "Submit ASN"}
          </button>
        </div>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-brand-muted font-semibold mb-1">{label}</div>
      {children}
    </div>
  );
}

"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, MessageSquare } from "lucide-react";

import { api } from "@/lib/api";
import { signalBadge } from "@/lib/asn";
import { fmtDate, fmtNum } from "@/lib/format";
import type { Asn, PortalPo, PortalPoMaterial } from "@/lib/types";
import AsnTable from "@/components/portal/AsnTable";
import AsnDrawer from "@/components/portal/AsnDrawer";

export default function PoDetailPage() {
  const router = useRouter();
  const params = useParams<{ supplier_po_no: string }>();
  const poNo = decodeURIComponent(
    Array.isArray(params.supplier_po_no) ? params.supplier_po_no[0] : params.supplier_po_no,
  );

  const [po, setPo] = useState<PortalPo | null>(null);
  const [materials, setMaterials] = useState<PortalPoMaterial[]>([]);
  const [asns, setAsns] = useState<Asn[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [openAsn, setOpenAsn] = useState<Asn | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [pos, mats, asnRes] = await Promise.all([
          api.portalPos(),
          api.portalPoMaterials(poNo),
          api.portalAsns(),
        ]);
        if (cancelled) return;
        setPo(pos.items.find((p) => p.supplier_po_no === poNo) ?? null);
        setMaterials(mats);
        setAsns(asnRes.items.filter((a) => a.supplier_po_no === poNo));
      } catch (e) {
        if (!cancelled) setError((e as Error).message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [poNo]);

  const poAsns = useMemo(() => asns, [asns]);

  return (
    <div className="page-stack">
      <button onClick={() => router.push("/portal/pos")} className="btn-ghost w-fit px-0 hover:bg-transparent">
        <ArrowLeft size={15} /> Back to Purchase Orders
      </button>

      <div className="page-header">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="page-title">PO {poNo}</h1>
            {po?.escalated && <span className="badge badge-critical">Escalated</span>}
            {po?.overall_signal && <span className={"badge " + signalBadge(po.overall_signal)}>{po.overall_signal}</span>}
            {po?.completed ? (
              <span className="badge badge-track">Completed</span>
            ) : (
              <span className="badge badge-due">Pending</span>
            )}
          </div>
          <p className="page-subtitle">
            {po?.crm_no ? `CRM ${po.crm_no} · ` : ""}{materials.length} material{materials.length === 1 ? "" : "s"} · {poAsns.length} ASN{poAsns.length === 1 ? "" : "s"}
          </p>
        </div>
        <button onClick={() => router.push(`/portal/communication?po=${encodeURIComponent(poNo)}`)} className="btn-primary">
          <MessageSquare size={15} /> Open Communication
        </button>
      </div>

      {error && <div className="rounded-md bg-red-50 px-3 py-2 text-xs text-signal-red">{error}</div>}

      {/* Materials */}
      <div>
        <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-brand-muted">Materials</div>
        <div className="table-shell">
          <table className="min-w-full text-sm">
            <thead className="bg-gray-50">
              <tr>
                {["Material", "CRM", "Qty", "UOM", "Signal", "Due"].map((h) => (
                  <th key={h} className="px-4 py-3 text-left table-header whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading && <tr><td colSpan={6} className="px-4 py-8 text-center text-brand-muted">Loading…</td></tr>}
              {!loading && materials.length === 0 && (
                <tr><td colSpan={6} className="px-4 py-8 text-center text-brand-muted">No materials.</td></tr>
              )}
              {materials.map((m) => (
                <tr key={m.procurement_record_id} className="border-t border-brand-border">
                  <td className="px-4 py-3 font-medium text-brand-dark">{m.material_name}</td>
                  <td className="px-4 py-3 text-xs text-brand-muted">{m.crm_no}</td>
                  <td className="px-4 py-3">{fmtNum(m.qty)}</td>
                  <td className="px-4 py-3 text-xs text-brand-muted">{m.uom || "—"}</td>
                  <td className="px-4 py-3">
                    {m.signal ? <span className={"badge " + signalBadge(m.signal)}>{m.signal}</span> : "—"}
                  </td>
                  <td className="px-4 py-3 text-xs">{fmtDate(m.shipment_date)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* ASNs for this PO */}
      <div>
        <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-brand-muted">Shipments (ASN)</div>
        <AsnTable items={poAsns} loading={loading} onOpen={setOpenAsn} emptyLabel="No ASNs for this PO yet." />
      </div>

      {openAsn && (
        <AsnDrawer
          asn={openAsn}
          onClose={() => setOpenAsn(null)}
          onUpdated={(a) => {
            setOpenAsn(a);
            setAsns((prev) => prev.map((x) => (x.id === a.id ? a : x)));
          }}
        />
      )}
    </div>
  );
}

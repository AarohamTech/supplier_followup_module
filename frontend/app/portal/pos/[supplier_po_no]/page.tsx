"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, CalendarCheck, ListChecks, MessageSquare, Save } from "lucide-react";

import { api } from "@/lib/api";
import { signalBadge } from "@/lib/asn";
import { fmtDate, fmtNum } from "@/lib/format";
import type { Asn, PortalPo, PortalPoMaterial, PortalTask } from "@/lib/types";
import AsnTable from "@/components/portal/AsnTable";
import AsnDrawer from "@/components/portal/AsnDrawer";

const STATUS_OPTIONS = ["CONFIRMED", "DELAYED", "PARTIAL", "DISPATCHED", "ON_HOLD", "CANCELLED"];

function taskStatusBadge(status: string): string {
  const s = (status || "").toUpperCase();
  if (s === "DONE") return "bg-emerald-50 text-emerald-700";
  if (s === "BLOCKED") return "bg-red-50 text-signal-red";
  if (s.startsWith("WAITING")) return "bg-amber-50 text-amber-700";
  if (s === "IN_PROGRESS") return "bg-blue-50 text-blue-600";
  return "bg-gray-100 text-gray-600";
}

type Draft = { date: string; status: string; remark: string };

function isoDay(s?: string | null): string {
  return s ? s.slice(0, 10) : "";
}

export default function PoDetailPage() {
  const router = useRouter();
  const params = useParams<{ supplier_po_no: string }>();
  const poNo = decodeURIComponent(
    Array.isArray(params.supplier_po_no) ? params.supplier_po_no[0] : params.supplier_po_no,
  );

  const [po, setPo] = useState<PortalPo | null>(null);
  const [materials, setMaterials] = useState<PortalPoMaterial[]>([]);
  const [asns, setAsns] = useState<Asn[]>([]);
  const [tasks, setTasks] = useState<PortalTask[]>([]);
  const [drafts, setDrafts] = useState<Record<number, Draft>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [savedMsg, setSavedMsg] = useState<string | null>(null);
  const [openAsn, setOpenAsn] = useState<Asn | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [pos, mats, asnRes, taskList] = await Promise.all([
          api.portalPos(),
          api.portalPoMaterials(poNo),
          api.portalAsns(),
          api.portalPoTasks(poNo),
        ]);
        if (cancelled) return;
        setPo(pos.items.find((p) => p.supplier_po_no === poNo) ?? null);
        setMaterials(mats);
        setAsns(asnRes.items.filter((a) => a.supplier_po_no === poNo));
        setTasks(taskList);
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

  // Seed the editable commitment drafts whenever materials (re)load.
  useEffect(() => {
    const d: Record<number, Draft> = {};
    for (const m of materials) {
      d[m.procurement_record_id] = {
        date: isoDay(m.commitment_date),
        status: m.commitment_status || "CONFIRMED",
        remark: m.commitment_remark || "",
      };
    }
    setDrafts(d);
  }, [materials]);

  const poAsns = useMemo(() => asns, [asns]);
  const committedCount = materials.filter((m) => m.commitment_date).length;

  const setDraft = (id: number, patch: Partial<Draft>) =>
    setDrafts((prev) => ({ ...prev, [id]: { ...prev[id], ...patch } }));

  const save = async () => {
    setSaving(true);
    setError(null);
    setSavedMsg(null);
    try {
      const items = materials.map((m) => {
        const d = drafts[m.procurement_record_id];
        return {
          procurement_record_id: m.procurement_record_id,
          commitment_date: d?.date || null,
          supplier_status: d?.date ? d?.status || "CONFIRMED" : null,
          supplier_remark: d?.remark || null,
        };
      });
      const updated = await api.submitPortalCommitments(poNo, items);
      setMaterials(updated);
      setSavedMsg("Commitment dates saved — your buyer has been notified.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

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
            {po?.crm_no ? `CRM ${po.crm_no} · ` : ""}{materials.length} material{materials.length === 1 ? "" : "s"} ·{" "}
            {committedCount}/{materials.length} committed · {poAsns.length} ASN{poAsns.length === 1 ? "" : "s"}
          </p>
        </div>
        <button onClick={() => router.push(`/portal/communication?po=${encodeURIComponent(poNo)}`)} className="btn-outline">
          <MessageSquare size={15} /> Open Communication
        </button>
      </div>

      {error && <div className="rounded-md bg-red-50 px-3 py-2 text-xs text-signal-red">{error}</div>}
      {savedMsg && <div className="rounded-md bg-emerald-50 px-3 py-2 text-xs text-emerald-700">{savedMsg}</div>}

      {/* Commitment form */}
      <div>
        <div className="mb-2 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-brand-muted">
          <CalendarCheck size={14} className="text-signal-red" /> Material commitments
        </div>
        <div className="table-shell">
          <table className="min-w-full text-sm">
            <thead className="bg-gray-50">
              <tr>
                {["Material", "CRM", "Qty", "UOM", "PO Date", "Required By", "Committed Date", "Status", "Remark"].map((h) => (
                  <th key={h} className="px-3 py-3 text-left table-header whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading && <tr><td colSpan={9} className="px-4 py-8 text-center text-brand-muted">Loading…</td></tr>}
              {!loading && materials.length === 0 && (
                <tr><td colSpan={9} className="px-4 py-8 text-center text-brand-muted">No materials.</td></tr>
              )}
              {materials.map((m) => {
                const d = drafts[m.procurement_record_id] || { date: "", status: "CONFIRMED", remark: "" };
                return (
                  <tr key={m.procurement_record_id} className="border-t border-brand-border align-top">
                    <td className="px-3 py-3 font-medium text-brand-dark">{m.material_name}</td>
                    <td className="px-3 py-3 text-xs text-brand-muted">{m.crm_no}</td>
                    <td className="px-3 py-3">{fmtNum(m.qty)}</td>
                    <td className="px-3 py-3 text-xs text-brand-muted">{m.uom || "—"}</td>
                    <td className="px-3 py-3 text-xs">{fmtDate(m.po_date)}</td>
                    <td className="px-3 py-3 text-xs">{fmtDate(m.shipment_date)}</td>
                    <td className="px-3 py-3">
                      <input
                        type="date"
                        className="input py-1 w-40"
                        value={d.date}
                        onChange={(e) => setDraft(m.procurement_record_id, { date: e.target.value })}
                      />
                    </td>
                    <td className="px-3 py-3">
                      <select
                        className="input py-1 w-32"
                        value={d.status}
                        onChange={(e) => setDraft(m.procurement_record_id, { status: e.target.value })}
                      >
                        {STATUS_OPTIONS.map((s) => <option key={s} value={s}>{s}</option>)}
                      </select>
                    </td>
                    <td className="px-3 py-3">
                      <input
                        type="text"
                        className="input py-1 w-44"
                        placeholder="Optional note"
                        value={d.remark}
                        onChange={(e) => setDraft(m.procurement_record_id, { remark: e.target.value })}
                      />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <div className="mt-3 flex items-center justify-between">
          <p className="text-xs text-brand-muted">
            Enter a committed dispatch date for each material. Once committed, follow-ups stop and your buyer sees the date.
          </p>
          <button className="btn-primary" disabled={saving || loading || materials.length === 0} onClick={save}>
            <Save size={15} /> {saving ? "Saving…" : "Save commitments"}
          </button>
        </div>
      </div>

      {/* Tasks the buyer's team is tracking for this PO (read-only) */}
      <div>
        <div className="mb-2 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-brand-muted">
          <ListChecks size={14} className="text-signal-red" /> Buyer Tasks
        </div>
        {tasks.length === 0 ? (
          <div className="empty-state">No tasks from your buyer's team for this PO.</div>
        ) : (
          <div className="space-y-2">
            {tasks.map((t) => (
              <div key={t.id} className="card flex flex-wrap items-start justify-between gap-3 p-3">
                <div className="min-w-0">
                  <div className="font-medium text-brand-dark">{t.title}</div>
                  {t.description && <div className="mt-0.5 text-xs text-brand-muted">{t.description}</div>}
                  <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-brand-muted">
                    {t.material_name && <span>{t.material_name}</span>}
                    {t.due_date && <span>· Due {fmtDate(t.due_date)}</span>}
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-1.5">
                  <span className="badge bg-gray-100 text-gray-600">{t.priority}</span>
                  <span className={"badge " + taskStatusBadge(t.status)}>{t.status.replace(/_/g, " ")}</span>
                </div>
              </div>
            ))}
          </div>
        )}
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

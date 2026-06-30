"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, CalendarCheck, ListChecks, MessageSquare, Save, Truck } from "lucide-react";

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
  return "bg-subtle text-brand-muted";
}

function taskPriorityBadge(priority: string): string {
  const p = (priority || "").toUpperCase();
  if (p === "P0") return "bg-red-50 text-signal-red";
  if (p === "P1") return "bg-amber-50 text-amber-700";
  if (p === "P2") return "bg-blue-50 text-blue-700";
  return "bg-subtle text-brand-muted";
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
    <div className="space-y-5">
      <button onClick={() => router.push("/portal/pos")} className="btn-ghost w-fit px-0 hover:bg-transparent">
        <ArrowLeft size={15} /> Back to purchase orders
      </button>

      <section className="card overflow-hidden">
        <div className="flex flex-col gap-4 px-5 py-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-xl font-semibold tracking-tight text-brand-dark">PO {poNo}</h1>
              {po?.escalated && <span className="badge badge-critical">Escalated</span>}
              {po?.overall_signal && <span className={"badge " + signalBadge(po.overall_signal)}>{po.overall_signal}</span>}
              {po?.completed ? <span className="badge badge-track">Completed</span> : <span className="badge badge-due">Pending</span>}
            </div>
            <p className="mt-1 max-w-2xl text-sm text-brand-muted">
              Review material commitments, buyer tasks and shipment progress for this purchase order.
            </p>
          </div>
          <button onClick={() => router.push(`/portal/communication?po=${encodeURIComponent(poNo)}`)} className="btn-outline shrink-0">
            <MessageSquare size={15} /> Open communication
          </button>
        </div>

        <dl className="grid grid-cols-2 border-t border-brand-border bg-subtle/70 sm:grid-cols-4">
          {[
            ["CRM reference", po?.crm_no || "—"],
            ["Materials", String(materials.length)],
            ["Commitments", `${committedCount} of ${materials.length}`],
            ["Shipments", String(poAsns.length)],
          ].map(([label, value], index) => (
            <div key={label} className={`px-5 py-3 ${index % 2 ? "border-l border-brand-border" : ""} ${index > 1 ? "border-t border-brand-border sm:border-t-0" : ""} sm:border-l sm:first:border-l-0`}>
              <dt className="text-[10px] font-semibold uppercase tracking-wider text-brand-muted">{label}</dt>
              <dd className="mt-0.5 text-sm font-semibold text-brand-dark">{value}</dd>
            </div>
          ))}
        </dl>
      </section>

      {error && <div role="alert" className="rounded-md border border-red-100 bg-red-50 px-3 py-2 text-xs text-signal-red">{error}</div>}
      {savedMsg && <div role="status" className="rounded-md border border-emerald-100 bg-emerald-50 px-3 py-2 text-xs text-emerald-700">{savedMsg}</div>}

      <section className="card overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-brand-border px-4 py-3">
          <div className="flex items-center gap-2">
            <CalendarCheck size={15} className="text-signal-red" />
            <div>
              <h2 className="text-sm font-semibold text-brand-dark">Material commitments</h2>
              <p className="text-xs text-brand-muted">Confirm dispatch dates and current material status.</p>
            </div>
          </div>
          <span className="text-xs font-medium text-brand-muted">{committedCount}/{materials.length} recorded</span>
        </div>

        <div className="overflow-x-auto">
          <table className="min-w-[1120px] w-full text-sm">
            <thead className="bg-subtle">
              <tr>
                {["Material", "CRM", "Qty", "UOM", "PO date", "Required by", "Committed date", "Status", "Remark"].map((h) => (
                  <th key={h} className="whitespace-nowrap px-3 py-3 text-left table-header">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading && <tr><td colSpan={9} className="px-4 py-10 text-center text-brand-muted">Loading…</td></tr>}
              {!loading && materials.length === 0 && <tr><td colSpan={9} className="px-4 py-10 text-center text-brand-muted">No materials found for this order.</td></tr>}
              {materials.map((m) => {
                const d = drafts[m.procurement_record_id] || { date: "", status: "CONFIRMED", remark: "" };
                return (
                  <tr key={m.procurement_record_id} className="border-t border-brand-border align-middle hover:bg-subtle/60">
                    <td className="min-w-[260px] px-3 py-3 font-medium text-brand-dark">{m.material_name}</td>
                    <td className="whitespace-nowrap px-3 py-3 text-xs text-brand-muted">{m.crm_no}</td>
                    <td className="px-3 py-3">{fmtNum(m.qty)}</td>
                    <td className="px-3 py-3 text-xs text-brand-muted">{m.uom || "—"}</td>
                    <td className="whitespace-nowrap px-3 py-3 text-xs">{fmtDate(m.po_date)}</td>
                    <td className="whitespace-nowrap px-3 py-3 text-xs">{fmtDate(m.shipment_date)}</td>
                    <td className="px-3 py-3">
                      <input type="date" className="input min-w-[9.5rem] py-1.5" value={d.date} onChange={(e) => setDraft(m.procurement_record_id, { date: e.target.value })} />
                    </td>
                    <td className="px-3 py-3">
                      <select className="input min-w-[8.5rem] py-1.5" value={d.status} onChange={(e) => setDraft(m.procurement_record_id, { status: e.target.value })}>
                        {STATUS_OPTIONS.map((s) => <option key={s} value={s}>{s.replace(/_/g, " ")}</option>)}
                      </select>
                    </td>
                    <td className="px-3 py-3">
                      <input type="text" className="input min-w-[11rem] py-1.5" placeholder="Optional note" value={d.remark} onChange={(e) => setDraft(m.procurement_record_id, { remark: e.target.value })} />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        <div className="flex flex-col gap-3 border-t border-brand-border bg-subtle/70 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="max-w-3xl text-xs leading-relaxed text-brand-muted">
            Add a dispatch date to stop automated follow-ups for that material and notify your buyer.
          </p>
          <button className="btn-primary shrink-0" disabled={saving || loading || materials.length === 0} onClick={save}>
            <Save size={15} /> {saving ? "Saving…" : "Save commitments"}
          </button>
        </div>
      </section>

      <section className="card overflow-hidden">
        <div className="flex items-center justify-between border-b border-brand-border px-4 py-3">
          <div className="flex items-center gap-2">
            <ListChecks size={15} className="text-signal-red" />
            <div>
              <h2 className="text-sm font-semibold text-brand-dark">Buyer tasks</h2>
              <p className="text-xs text-brand-muted">Read-only actions tracked by the buyer's team.</p>
            </div>
          </div>
          <span className="badge bg-subtle text-brand-dark">{tasks.length}</span>
        </div>

        {tasks.length === 0 ? (
          <div className="px-4 py-10 text-center text-sm text-brand-muted">No buyer tasks for this purchase order.</div>
        ) : (
          <div className="divide-y divide-brand-border">
            {tasks.map((t) => (
              <article key={t.id} className="flex flex-col gap-2 px-4 py-3 hover:bg-subtle/60 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0 flex-1">
                  <h3 className="text-sm font-medium leading-snug text-brand-dark">{t.title}</h3>
                  {t.description && <p className="mt-0.5 line-clamp-2 text-xs leading-relaxed text-brand-muted">{t.description}</p>}
                  {(t.material_name || t.due_date) && (
                    <div className="mt-1.5 flex flex-wrap items-center gap-x-2 text-[11px] text-brand-muted">
                      {t.material_name && <span>{t.material_name}</span>}
                      {t.due_date && <span>Due {fmtDate(t.due_date)}</span>}
                    </div>
                  )}
                </div>
                <div className="flex shrink-0 items-center gap-1.5">
                  <span className={"badge " + taskPriorityBadge(t.priority)}>{t.priority}</span>
                  <span className={"badge " + taskStatusBadge(t.status)}>{t.status.replace(/_/g, " ")}</span>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>

      <section>
        <div className="mb-2 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Truck size={15} className="text-signal-red" />
            <div>
              <h2 className="text-sm font-semibold text-brand-dark">Shipments</h2>
              <p className="text-xs text-brand-muted">Advance Shipping Notices linked to this order.</p>
            </div>
          </div>
          <span className="text-xs font-medium text-brand-muted">{poAsns.length} ASN{poAsns.length === 1 ? "" : "s"}</span>
        </div>
        <AsnTable items={poAsns} loading={loading} onOpen={setOpenAsn} emptyLabel="No ASNs for this PO yet." />
      </section>

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

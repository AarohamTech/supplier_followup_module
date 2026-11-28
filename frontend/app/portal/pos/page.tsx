"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ChevronRight, MessageSquare } from "lucide-react";

import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { PortalPo } from "@/lib/types";
import { fmtDate } from "@/lib/format";
import { useErrorText, useT } from "@/lib/i18n";
import { SUPPLIER_ESCALATED_LABEL, supplierSignalChip } from "@/lib/messageLabels";
import PoPdfButton from "@/components/po/PoPdfButton";

// English source strings — translated with t() where the header row renders.
const COLUMNS = ["PO Reference", "CRM No", "Materials", "Follow-up", "Earliest Due", "ASNs", "Messages", "Status", ""];

export default function PortalPosPage() {
  const router = useRouter();
  const { t, lang } = useT();
  const errorText = useErrorText();
  const [items, setItems] = useState<PortalPo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await api.portalPos();
        if (!cancelled) setItems(res.items);
      } catch (e) {
        if (!cancelled) setError((e as Error).message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const filtered = items.filter((p) =>
    !q.trim()
      ? true
      : `${p.po_ref ?? ""} ${p.supplier_po_no} ${p.crm_no ?? ""}`.toLowerCase().includes(q.trim().toLowerCase()),
  );

  const open = (po: string) => router.push(`/portal/pos/${encodeURIComponent(po)}`);

  return (
    <div className="page-stack">
      <div className="page-header">
        <div>
          <h1 className="page-title">{t("My Purchase Orders")}</h1>
          <p className="page-subtitle">{t("All your POs. Escalated orders are pinned to the top — click a row for details.")}</p>
        </div>
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={t("Search PO / CRM…")}
          className="input max-w-xs"
        />
      </div>

      {error && <div className="rounded-md bg-red-50 px-3 py-2 text-xs text-signal-red">{errorText(error)}</div>}

      <div className="table-shell">
        <table className="min-w-full text-sm">
          <thead className="bg-subtle">
            <tr>
              {COLUMNS.map((h) => (
                <th key={h} className="px-4 py-3 text-left table-header whitespace-nowrap">{h ? t(h) : ""}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr><td colSpan={9} className="px-4 py-10 text-center text-brand-muted">{t("Loading…")}</td></tr>
            )}
            {!loading && filtered.length === 0 && (
              <tr><td colSpan={9} className="px-4 py-10 text-center text-brand-muted">{t("No purchase orders found.")}</td></tr>
            )}
            {filtered.map((p) => (
              <tr
                key={p.supplier_po_no}
                onClick={() => open(p.supplier_po_no)}
                className={cn(
                  "cursor-pointer border-t border-brand-border hover:bg-subtle",
                  p.escalated && "bg-red-50/50",
                )}
              >
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    {/* The PO document reference (what the supplier's PO says); the
                        bare CRM counter is only a muted fallback hint. */}
                    <span className="font-medium text-brand-dark">{p.po_ref || p.supplier_po_no}</span>
                    <PoPdfButton
                      trnNo={p.po_trn_no}
                      fileLabel={p.po_ref || p.supplier_po_no}
                      endpoint="/api/portal/po-pdf"
                    />
                    {p.escalated && <span className="badge badge-critical">{t(SUPPLIER_ESCALATED_LABEL)}</span>}
                  </div>
                </td>
                <td className="px-4 py-3 text-xs text-brand-muted">{p.crm_no || "—"}</td>
                <td className="px-4 py-3">{p.material_count}</td>
                <td className="px-4 py-3">
                  {supplierSignalChip(p.overall_signal) ? (
                    <span className={"badge " + supplierSignalChip(p.overall_signal)!.cls}>{t(supplierSignalChip(p.overall_signal)!.label)}</span>
                  ) : "—"}
                </td>
                <td className="px-4 py-3 text-xs">{fmtDate(p.earliest_shipment_date, lang)}</td>
                <td className="px-4 py-3">{p.asn_count}</td>
                <td className="px-4 py-3">
                  <span className="inline-flex items-center gap-1 text-brand-muted">
                    <MessageSquare size={13} /> {p.message_count}
                  </span>
                </td>
                <td className="px-4 py-3">
                  {p.completed ? (
                    <span className="badge badge-track">{t("Completed")}</span>
                  ) : (
                    <span className="badge badge-due">{t("In progress")}</span>
                  )}
                </td>
                <td className="px-4 py-3 text-right text-brand-muted">
                  <ChevronRight size={16} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

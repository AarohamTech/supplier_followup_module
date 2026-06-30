"use client";

import { useEffect, useState } from "react";
import { History, Loader2, X } from "lucide-react";

import api from "@/lib/api";
import type { SupplierEmailAudit } from "@/lib/types";

function fmtVal(v: unknown): string {
  if (v === null || v === undefined || v === "") return "—";
  if (Array.isArray(v)) return v.length ? v.join(", ") : "—";
  if (typeof v === "boolean") return v ? "Active" : "Inactive";
  return String(v);
}

const FIELD_LABELS: Record<string, string> = {
  supplier_name: "Supplier",
  to_emails: "TO",
  cc_emails: "CC",
  bcc_emails: "BCC",
  escalation_emails: "Escalation",
  contact_person: "Contact person",
  phone: "Phone",
  remarks: "Remarks",
  is_active: "Active",
};

function actionBadge(action: SupplierEmailAudit["action"]) {
  const map: Record<string, string> = {
    CREATE: "bg-emerald-50 text-emerald-700",
    UPDATE: "bg-amber-50 text-amber-700",
    DELETE: "bg-red-50 text-signal-red",
  };
  return map[action] ?? "bg-subtle text-brand-dark";
}

export default function EmailAuditModal({ onClose }: { onClose: () => void }) {
  const [rows, setRows] = useState<SupplierEmailAudit[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .supplierEmailAudit(300)
      .then(setRows)
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="fixed inset-0 z-50 bg-black/40 grid place-items-center p-4" onClick={onClose}>
      <div className="bg-card rounded-lg shadow-xl w-full max-w-3xl max-h-[85vh] flex flex-col" onClick={(e) => e.stopPropagation()}>
        <div className="px-5 py-3 border-b border-brand-border flex items-center justify-between">
          <div className="flex items-center gap-2 font-semibold text-brand-dark">
            <History size={16} /> Email Master — Change Log
          </div>
          <button className="p-1 rounded hover:bg-subtle" onClick={onClose}><X size={18} /></button>
        </div>

        <div className="overflow-y-auto p-4">
          {loading ? (
            <div className="py-10 text-center text-brand-muted"><Loader2 className="mx-auto animate-spin" size={18} /></div>
          ) : error ? (
            <div className="rounded-md bg-red-50 px-3 py-2 text-xs text-signal-red">{error}</div>
          ) : rows.length === 0 ? (
            <div className="py-10 text-center text-sm text-brand-muted">No changes recorded yet.</div>
          ) : (
            <div className="space-y-3">
              {rows.map((r) => (
                <div key={r.id} className="rounded-md border border-brand-border p-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span className={`badge ${actionBadge(r.action)}`}>{r.action}</span>
                      <span className="text-sm font-medium text-brand-dark">{r.supplier_name || "—"}</span>
                    </div>
                    <div className="text-[11px] text-brand-muted">
                      {r.changed_by || "—"} · {new Date(r.created_at).toLocaleString()}
                    </div>
                  </div>
                  {r.changes && Object.keys(r.changes).length > 0 && (
                    <div className="mt-2 overflow-x-auto">
                      <table className="text-xs">
                        <tbody>
                          {Object.entries(r.changes).map(([field, d]) => (
                            <tr key={field} className="align-top">
                              <td className="pr-3 py-0.5 font-medium text-brand-muted whitespace-nowrap">
                                {FIELD_LABELS[field] ?? field}
                              </td>
                              {r.action === "UPDATE" ? (
                                <>
                                  <td className="pr-2 py-0.5 text-signal-red line-through">{fmtVal(d.old)}</td>
                                  <td className="pr-2 py-0.5 text-brand-muted">→</td>
                                  <td className="py-0.5 text-emerald-700">{fmtVal(d.new)}</td>
                                </>
                              ) : (
                                <td className="py-0.5 text-brand-dark" colSpan={3}>
                                  {fmtVal(r.action === "DELETE" ? d.old : d.new)}
                                </td>
                              )}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

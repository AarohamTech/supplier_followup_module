"use client";

import { useStore } from "@/lib/store";
import { signalClass } from "@/lib/format";
import { Users } from "lucide-react";

export default function Page() {
  const suppliers = useStore((s) => s.supplierMasters);

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3">
        <span className="grid h-10 w-10 place-items-center rounded-lg bg-brand-dark text-white shadow-card">
          <Users size={18} />
        </span>
        <div>
          <h1 className="text-xl font-bold text-brand-dark">Supplier Master</h1>
          <p className="text-sm text-brand-muted">Supplier health and mapped communication contacts.</p>
        </div>
      </div>
      <div className="card overflow-hidden">
        <table className="data-table min-w-full text-sm">
          <thead>
            <tr>
              {["Supplier", "Signal", "Email", "Primary email", "Latest PO"].map((h) => (
                <th key={h} className="text-left px-4 py-3 table-header whitespace-nowrap">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {suppliers.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-10 text-center text-brand-muted">
                  No suppliers yet. Sync procurement records first.
                </td>
              </tr>
            )}
            {suppliers.map((supplier) => {
              const sig = (supplier.latest_signal ?? "").toUpperCase();
              return (
                <tr key={supplier.id} className="border-t border-brand-border hover:bg-gray-50">
                  <td className="px-4 py-3 font-medium">{supplier.supplier_name}</td>
                  <td className="px-4 py-3">
                    {sig ? (
                      <span className={"inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold ring-1 " + (signalClass[sig] ?? "")}>
                        {sig}
                      </span>
                    ) : (
                      <span className="text-brand-muted">-</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {supplier.email_mapped
                      ? <span className="badge badge-track">Mapped</span>
                      : <span className="badge badge-overdue">Missing</span>}
                  </td>
                  <td className="px-4 py-3 text-xs">{supplier.primary_email ?? "-"}</td>
                  <td className="px-4 py-3 text-xs">{supplier.latest_supplier_po_no ?? "-"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

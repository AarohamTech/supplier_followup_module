"use client";

import { Users } from "lucide-react";

import { useStore } from "@/lib/store";
import { signalClass } from "@/lib/format";
import PageHeader from "@/components/layout/PageHeader";

export default function Page() {
  const suppliers = useStore((s) => s.supplierMasters);

  return (
    <div className="page-stack">
      <PageHeader
        title="Supplier Master"
        description="Supplier signal, contact mapping and latest PO visibility in one place."
        icon={Users}
      />
      <div className="card overflow-hidden">
        <table className="min-w-full text-sm">
          <thead className="bg-gray-50">
            <tr>
              {["Supplier", "Signal", "Email Mapped", "Primary Email", "PO No."].map((h) => (
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
                      ? <span className="badge badge-track">YES</span>
                      : <span className="badge badge-overdue">NO</span>}
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

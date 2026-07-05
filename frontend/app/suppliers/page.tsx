"use client";

import { useEffect, useMemo, useState } from "react";
import { Users } from "lucide-react";

import { useStore } from "@/lib/store";
import { signalClass } from "@/lib/format";
import PageHeader from "@/components/layout/PageHeader";
import Pager from "@/components/ui/Pager";

const SIZE = 50;

export default function Page() {
  const suppliers = useStore((s) => s.supplierMasters);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return suppliers;
    return suppliers.filter((s) =>
      `${s.supplier_name} ${s.primary_email ?? ""} ${s.latest_supplier_po_no ?? ""}`.toLowerCase().includes(q),
    );
  }, [suppliers, search]);

  useEffect(() => setPage(1), [search]);
  const paged = useMemo(() => filtered.slice((page - 1) * SIZE, page * SIZE), [filtered, page]);

  return (
    <div className="page-stack">
      <PageHeader
        title="Supplier Master"
        description="Supplier signal, contact mapping and latest PO visibility in one place."
        icon={Users}
        actions={
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search supplier / email / PO…"
            className="input max-w-xs"
          />
        }
      />
      <div className="card overflow-hidden">
        <table className="min-w-full text-sm">
          <thead className="bg-subtle">
            <tr>
              {["Supplier", "Signal", "Email Mapped", "Primary Email", "PO No."].map((h) => (
                <th key={h} className="text-left px-4 py-3 table-header whitespace-nowrap">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-10 text-center text-brand-muted">
                  {suppliers.length === 0 ? "No suppliers yet. Sync procurement records first." : "No suppliers match your search."}
                </td>
              </tr>
            )}
            {paged.map((supplier) => {
              const sig = (supplier.latest_signal ?? "").toUpperCase();
              return (
                <tr key={supplier.id} className="border-t border-brand-border hover:bg-subtle">
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
      <Pager page={page} size={SIZE} total={filtered.length} onPage={setPage} unit="suppliers" />
    </div>
  );
}

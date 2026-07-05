"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ClipboardList } from "lucide-react";

import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { EmployeePo } from "@/lib/types";
import PageHeader from "@/components/layout/PageHeader";
import PoExpandableTable from "@/components/po/PoExpandableTable";

export default function PurchaseOrdersPage() {
  const { hasRole } = useAuth();
  const isAdmin = hasRole("admin");

  const [pos, setPos] = useState<EmployeePo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.poViewList();
      setPos(r.items);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isAdmin) void load();
    else setLoading(false);
  }, [isAdmin, load]);

  const filtered = useMemo(() => {
    const s = search.trim().toLowerCase();
    return s
      ? pos.filter((p) => `${p.supplier_po_no} ${p.supplier_name || ""} ${p.crm_no || ""}`.toLowerCase().includes(s))
      : pos;
  }, [pos, search]);

  if (!isAdmin) {
    return (
      <div className="page-stack">
        <PageHeader title="Purchase Orders" description="All purchase orders." icon={ClipboardList} />
        <div className="card p-4 text-sm text-brand-muted">This page is available to administrators only.</div>
      </div>
    );
  }

  return (
    <div className="page-stack">
      <PageHeader
        title="Purchase Orders"
        description="Every PO. Expand one for its materials and full communication history, or raise a cancellation."
        icon={ClipboardList}
      />
      {error && <div className="card p-3 text-xs text-signal-red">{error}</div>}
      <div className="card p-3">
        <input
          className="border border-brand-border rounded px-3 py-2 text-sm w-full max-w-sm"
          placeholder="Search PO / vendor / CRM…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>
      {loading ? (
        <div className="card p-6 text-center text-sm text-brand-muted">Loading…</div>
      ) : (
        <PoExpandableTable
          pos={filtered}
          loadDetail={(p) => api.poViewDetail(p.supplier_po_no, p.supplier_name || undefined)}
          requestCancel={(p) => api.poViewRequestCancel(p.supplier_po_no, p.supplier_name || undefined).then(() => {})}
        />
      )}
    </div>
  );
}

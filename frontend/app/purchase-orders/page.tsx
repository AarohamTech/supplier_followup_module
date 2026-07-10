"use client";

import { useCallback, useEffect, useState } from "react";
import { ClipboardList } from "lucide-react";

import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { EmployeePo } from "@/lib/types";
import PageHeader from "@/components/layout/PageHeader";
import PoExpandableTable from "@/components/po/PoExpandableTable";
import Pager from "@/components/ui/Pager";

const SIZE = 50;

export default function PurchaseOrdersPage() {
  const { hasRole } = useAuth();
  const isAdmin = hasRole("admin");

  const [pos, setPos] = useState<EmployeePo[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");

  // Debounce the search box; reset to page 1 whenever the query changes.
  useEffect(() => {
    const t = setTimeout(() => {
      setDebounced(search.trim());
      setPage(1);
    }, 300);
    return () => clearTimeout(t);
  }, [search]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.poViewList({ search: debounced || undefined, page, size: SIZE });
      setPos(r.items);
      setTotal(r.total);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [debounced, page]);

  useEffect(() => {
    if (isAdmin) void load();
    else setLoading(false);
  }, [isAdmin, load]);

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
        <>
          <PoExpandableTable
            pos={pos}
            loadDetail={(p) => api.poViewDetail(p.supplier_po_no, p.supplier_name || undefined)}
            requestCancel={(p, remark) => api.poViewRequestCancel(p.supplier_po_no, p.supplier_name || undefined, remark).then(() => {})}
          />
          <Pager page={page} size={SIZE} total={total} onPage={setPage} unit="POs" />
        </>
      )}
    </div>
  );
}

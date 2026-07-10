"use client";

import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import type { EmployeePo } from "@/lib/types";
import PoExpandableTable from "@/components/po/PoExpandableTable";

export default function EmployeePosPage() {
  const [pos, setPos] = useState<EmployeePo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const p = await api.eportalPos();
        if (!cancelled) setPos(p.items);
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

  const filtered = pos.filter((p) => {
    const s = q.trim().toLowerCase();
    if (!s) return true;
    return `${p.supplier_po_no} ${p.supplier_name || ""} ${p.crm_no || ""}`.toLowerCase().includes(s);
  });

  return (
    <div className="page-stack">
      <div className="page-header">
        <div>
          <h1 className="page-title">My Purchase Orders</h1>
          <p className="page-subtitle">{loading ? "Loading…" : `${pos.length} PO(s) assigned to you`}</p>
        </div>
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search PO / vendor / CRM…"
          className="input max-w-xs"
        />
      </div>
      {error && <div className="rounded-md bg-red-50 px-3 py-2 text-xs text-signal-red">{error}</div>}
      {!loading && (
        <PoExpandableTable
          pos={filtered}
          loadDetail={(p) => api.eportalPoDetail(p.supplier_po_no, p.supplier_name || undefined)}
          requestCancel={(p, remark) => api.eportalRequestPoCancel(p.supplier_po_no, p.supplier_name || undefined, remark).then(() => {})}
        />
      )}
    </div>
  );
}

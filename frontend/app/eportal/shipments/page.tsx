"use client";

import { useCallback, useEffect, useState } from "react";
import { Truck } from "lucide-react";

import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { Asn, AsnSummary } from "@/lib/types";
import PageHeader from "@/components/layout/PageHeader";
import { AsnCards } from "@/components/portal/PortalCards";
import AsnTable from "@/components/portal/AsnTable";
import AsnDrawer from "@/components/portal/AsnDrawer";

const TABS = [
  { key: "active", label: "Active" },
  { key: "history", label: "History" },
  { key: "", label: "All" },
] as const;

/** Employee view: shipments raised against MY purchase orders only. */
export default function EmployeeShipmentsPage() {
  const [tab, setTab] = useState<(typeof TABS)[number]["key"]>("active");
  const [summary, setSummary] = useState<AsnSummary | null>(null);
  const [items, setItems] = useState<Asn[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<Asn | null>(null);

  const loadSummary = useCallback(async () => {
    try {
      setSummary(await api.eportalAsnSummary());
    } catch {
      /* non-fatal */
    }
  }, []);

  const loadList = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.eportalListAsns({ tab: tab || undefined, search: search || undefined });
      setItems(res.items);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [tab, search]);

  useEffect(() => {
    void loadSummary();
  }, [loadSummary]);

  useEffect(() => {
    const t = setTimeout(() => void loadList(), 150);
    return () => clearTimeout(t);
  }, [loadList]);

  const onUpdated = (asn: Asn) => {
    setSelected(asn);
    setItems((prev) => prev.map((a) => (a.id === asn.id ? asn : a)));
    void loadSummary();
  };

  return (
    <div className="page-stack">
      <PageHeader
        title="My Shipments"
        description="Shipments raised against your purchase orders — live tracking and timeline."
        icon={Truck}
        actions={
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search ASN / PO / carrier…"
            className="input max-w-xs"
          />
        }
      />

      <AsnCards s={summary} />

      <div className="card">
        <div className="flex items-center gap-1 border-b border-brand-border px-3">
          {TABS.map((t) => (
            <button
              key={t.key || "all"}
              onClick={() => setTab(t.key)}
              className={cn(
                "px-3 py-3 text-sm font-medium border-b-2 -mb-px",
                tab === t.key
                  ? "border-signal-red text-signal-red"
                  : "border-transparent text-brand-muted hover:text-brand-dark",
              )}
            >
              {t.label}
            </button>
          ))}
        </div>
        <div className="p-3">
          {error && <div className="mb-3 rounded-md bg-red-50 px-3 py-2 text-xs text-signal-red">{error}</div>}
          <AsnTable items={items} loading={loading} onOpen={setSelected} showSupplier emptyLabel="No shipments on your POs yet." />
        </div>
      </div>

      {selected && <AsnDrawer asn={selected} mode="eportal" onClose={() => setSelected(null)} onUpdated={onUpdated} />}
    </div>
  );
}

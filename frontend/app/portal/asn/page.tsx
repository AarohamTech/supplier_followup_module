"use client";

import { useCallback, useEffect, useState } from "react";
import { Plus, Truck } from "lucide-react";

import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { Asn, AsnSummary } from "@/lib/types";
import { AsnCards } from "@/components/portal/PortalCards";
import AsnTable from "@/components/portal/AsnTable";
import AsnCreateModal from "@/components/portal/AsnCreateModal";
import AsnDrawer from "@/components/portal/AsnDrawer";

const TABS = [
  { key: "active", label: "Active Shipments" },
  { key: "history", label: "History" },
  { key: "drafts", label: "Drafts" },
] as const;

export default function AsnPortalPage() {
  const [tab, setTab] = useState<(typeof TABS)[number]["key"]>("active");
  const [summary, setSummary] = useState<AsnSummary | null>(null);
  const [items, setItems] = useState<Asn[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [selected, setSelected] = useState<Asn | null>(null);

  const loadSummary = useCallback(async () => {
    try {
      setSummary(await api.portalAsnSummary());
    } catch {
      /* non-fatal */
    }
  }, []);

  const loadList = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.portalAsns({ tab });
      setItems(res.items);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [tab]);

  useEffect(() => {
    void loadSummary();
  }, [loadSummary]);

  useEffect(() => {
    void loadList();
  }, [loadList]);

  const onCreated = (asn: Asn) => {
    setCreating(false);
    void loadSummary();
    // Land the new ASN's tab so the user sees it immediately.
    setTab(asn.status === "DRAFT" ? "drafts" : "active");
    void loadList();
  };

  const onUpdated = (asn: Asn) => {
    setSelected(asn);
    setItems((prev) => prev.map((a) => (a.id === asn.id ? asn : a)));
    void loadSummary();
  };

  return (
    <div className="page-stack">
      <div className="page-header">
        <div className="flex items-start gap-3">
          <div className="icon-tile bg-red-50 text-signal-red">
            <Truck size={18} />
          </div>
          <div>
            <h1 className="page-title">Shipment Tracking</h1>
            <p className="page-subtitle">Create Advance Shipping Notices and track them to delivery.</p>
          </div>
        </div>
        <button className="btn-primary" onClick={() => setCreating(true)}>
          <Plus size={14} /> Create New ASN
        </button>
      </div>

      <AsnCards s={summary} />

      <div className="card">
        <div className="flex items-center gap-1 border-b border-brand-border px-3">
          {TABS.map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={cn(
                "px-3 py-3 text-sm font-medium border-b-2 -mb-px",
                tab === t.key
                  ? "border-signal-red text-signal-red"
                  : "border-transparent text-brand-muted hover:text-brand-dark",
              )}
            >
              {t.label}
              {t.key === "drafts" && summary?.drafts ? ` (${summary.drafts})` : ""}
            </button>
          ))}
        </div>
        <div className="p-3">
          {error && <div className="mb-3 rounded-md bg-red-50 px-3 py-2 text-xs text-signal-red">{error}</div>}
          <AsnTable
            items={items}
            loading={loading}
            onOpen={setSelected}
            emptyLabel={
              tab === "drafts" ? "No draft ASNs." : tab === "history" ? "No delivered/closed shipments yet." : "No active shipments."
            }
          />
        </div>
      </div>

      {creating && <AsnCreateModal onClose={() => setCreating(false)} onCreated={onCreated} />}
      {selected && <AsnDrawer asn={selected} onClose={() => setSelected(null)} onUpdated={onUpdated} />}
    </div>
  );
}

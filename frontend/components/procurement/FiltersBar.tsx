"use client";
import { useStore } from "@/lib/store";

export default function FiltersBar() {
  const filters = useStore((s) => s.filters);
  const setFilters = useStore((s) => s.setFilters);
  const list = useStore((s) => s.list);

  // build option lists from current data
  const suppliers = Array.from(new Set((list?.items ?? []).map((r) => r.supplier_name).filter(Boolean) as string[])).sort();
  const statuses = Array.from(new Set((list?.items ?? []).map((r) => r.po_status).filter(Boolean) as string[])).sort();

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-5">
      <Sel label="SIGNAL" value={filters.signal ?? ""} onChange={(v) => setFilters({ signal: v })} options={["GREEN", "YELLOW", "RED", "BLACK"]} />
      <Sel label="SUPPLIER" value={filters.supplier_name ?? ""} onChange={(v) => setFilters({ supplier_name: v })} options={suppliers} />
      <Sel label="PO STATUS" value={filters.po_status ?? ""} onChange={(v) => setFilters({ po_status: v })} options={statuses} />
      <Inp label="PO No." value={filters.supplier_po_no ?? ""} onChange={(v) => setFilters({ supplier_po_no: v })} />
      <Inp label="CRM No." value={filters.crm_no ?? ""} onChange={(v) => setFilters({ crm_no: v })} />
    </div>
  );
}

function Sel({ label, value, onChange, options }: { label: string; value: string; onChange: (v: string) => void; options: string[] }) {
  return (
    <div className="flex flex-col gap-1">
      <label className="text-[10px] uppercase tracking-wider text-brand-muted font-semibold">{label}</label>
      <select
        value={value} onChange={(e) => onChange(e.target.value)}
        className="input py-1.5"
      >
        <option value="">All</option>
        {options.map((o) => <option key={o} value={o}>{o}</option>)}
      </select>
    </div>
  );
}
function Inp({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <div className="flex flex-col gap-1">
      <label className="text-[10px] uppercase tracking-wider text-brand-muted font-semibold">{label}</label>
      <input
        value={value} onChange={(e) => onChange(e.target.value)}
        placeholder="Contains..."
        className="input py-1.5"
      />
    </div>
  );
}

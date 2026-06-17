"use client";
import { useStore } from "@/lib/store";
import { Search } from "lucide-react";

export default function QuickFilters() {
  const filters = useStore((s) => s.filters);
  const setFilters = useStore((s) => s.setFilters);
  const clear = useStore((s) => s.clearFilters);
  const k = useStore((s) => s.kpis);

  const chips: { label: string; sig?: string }[] = [
    { label: `Red (${k?.red_count ?? 0})`, sig: "RED" },
    { label: `Black (${k?.black_count ?? 0})`, sig: "BLACK" },
    { label: `Yellow (${k?.yellow_count ?? 0})`, sig: "YELLOW" },
    { label: `Green (${k?.green_count ?? 0})`, sig: "GREEN" },
  ];

  return (
    <div className="card flex flex-wrap items-center gap-2 p-3">
      <span className="mr-1 text-[11px] font-bold uppercase text-brand-muted">Signal</span>
      {chips.map((c) => {
        const active = filters.signal === c.sig;
        return (
          <button
            key={c.label}
            onClick={() => setFilters({ signal: active ? undefined : c.sig })}
            aria-pressed={active}
            className={"chip " + (active ? "bg-signal-red text-white border-signal-red" : "")}
          >
            {c.label}
          </button>
        );
      })}
      <div className="flex-1" />
      <div className="relative w-full sm:w-auto">
        <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-brand-muted" />
        <input
          placeholder="Search PO, CRM, material, supplier"
          value={filters.search ?? ""}
          onChange={(e) => setFilters({ search: e.target.value })}
          className="w-full border border-brand-border py-2 pl-8 pr-3 text-sm sm:w-[340px]"
        />
      </div>
      <button onClick={clear} className="btn-ghost">Clear Filters</button>
    </div>
  );
}

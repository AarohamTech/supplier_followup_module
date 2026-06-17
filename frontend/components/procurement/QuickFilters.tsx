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
    <div className="card p-3 flex flex-wrap items-center gap-2">
      <span className="text-[10px] uppercase tracking-wider text-brand-muted font-semibold mr-2">Quick Filters:</span>
      {chips.map((c) => {
        const active = filters.signal === c.sig;
        return (
          <button
            key={c.label}
            onClick={() => setFilters({ signal: active ? undefined : c.sig })}
            className={"chip " + (active ? "bg-signal-red text-white border-signal-red" : "")}
          >
            {c.label}
          </button>
        );
      })}
      <div className="flex-1" />
      <div className="relative">
        <Search size={14} className="absolute left-2 top-1/2 -translate-y-1/2 text-brand-muted" />
        <input
          placeholder="Search PO No. / CRM / material / supplier..."
          value={filters.search ?? ""}
          onChange={(e) => setFilters({ search: e.target.value })}
          className="pl-7 pr-3 py-1.5 border border-brand-border rounded-md text-sm w-[320px] bg-white"
        />
      </div>
      <button onClick={clear} className="btn-ghost">Clear Filters</button>
    </div>
  );
}

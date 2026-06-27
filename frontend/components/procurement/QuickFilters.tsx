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
    <div className="flex flex-wrap items-center gap-2">
      <span className="mr-1 text-[10px] font-semibold uppercase tracking-wider text-brand-muted">Quick filters</span>
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
      <div className="relative order-last w-full sm:order-none sm:ml-auto sm:w-auto">
        <Search size={14} className="absolute left-2 top-1/2 -translate-y-1/2 text-brand-muted" />
        <input
          placeholder="Search PO No. / CRM / material / supplier..."
          value={filters.search ?? ""}
          onChange={(e) => setFilters({ search: e.target.value })}
          className="input w-full py-1.5 pl-7 sm:w-80"
        />
      </div>
      <button onClick={clear} className="btn-ghost ml-auto sm:ml-0">Clear Filters</button>
    </div>
  );
}

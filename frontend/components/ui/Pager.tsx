"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";

const navBtn =
  "inline-flex h-7 items-center gap-1 rounded-md border border-brand-border bg-card px-2 text-xs font-medium text-brand-dark hover:bg-subtle active:scale-[0.96] disabled:pointer-events-none disabled:opacity-40";

// Compact server-side pager: "Showing a-b of N" + Prev / Page x/y / Next.
export default function Pager({
  page,
  size,
  total,
  onPage,
  unit = "items",
}: {
  page: number;
  size: number;
  total: number;
  onPage: (p: number) => void;
  unit?: string;
}) {
  const pages = Math.max(1, Math.ceil(total / size));
  const from = total === 0 ? 0 : (page - 1) * size + 1;
  const to = Math.min(total, (page - 1) * size + size);
  return (
    <nav aria-label="Pagination" className="flex flex-wrap items-center justify-between gap-2 px-1 py-2">
      <span className="tabular text-xs text-brand-muted">
        Showing <span className="font-medium text-brand-dark">{from}–{to}</span> of {total} {unit}
      </span>
      <div className="flex items-center gap-1.5">
        <button type="button" disabled={page <= 1} onClick={() => onPage(page - 1)} className={navBtn}>
          <ChevronLeft size={14} /> Prev
        </button>
        <span className="tabular px-1.5 text-xs text-brand-muted">
          Page <span className="font-medium text-brand-dark">{page}</span> / {pages}
        </span>
        <button type="button" disabled={page >= pages} onClick={() => onPage(page + 1)} className={navBtn}>
          Next <ChevronRight size={14} />
        </button>
      </div>
    </nav>
  );
}

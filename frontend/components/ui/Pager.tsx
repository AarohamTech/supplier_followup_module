"use client";

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
    <div className="flex items-center justify-between px-1 py-2">
      <span className="text-xs text-brand-muted">
        Showing {from}-{to} of {total} {unit}
      </span>
      <div className="flex items-center gap-1">
        <button
          type="button"
          disabled={page <= 1}
          onClick={() => onPage(page - 1)}
          className="px-2.5 py-1 rounded text-sm hover:bg-subtle disabled:opacity-40"
        >
          Prev
        </button>
        <span className="px-2 text-sm">Page {page} / {pages}</span>
        <button
          type="button"
          disabled={page >= pages}
          onClick={() => onPage(page + 1)}
          className="px-2.5 py-1 rounded text-sm hover:bg-subtle disabled:opacity-40"
        >
          Next
        </button>
      </div>
    </div>
  );
}

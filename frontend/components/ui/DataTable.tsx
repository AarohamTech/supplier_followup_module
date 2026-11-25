"use client";

import { useMemo, useState, type ReactNode } from "react";
import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  ChevronLeft,
  ChevronRight,
  Inbox,
  Search,
} from "lucide-react";

// Varied widths so skeleton rows read as text, not as a grid of bars.
const SKELETON_WIDTHS = ["w-24", "w-32", "w-16", "w-28", "w-20", "w-36"];

export type Column<T> = {
  /** Stable key; also used as the sort key. */
  key: string;
  header: string;
  /** Cell renderer. Defaults to String(sortValue). */
  render?: (row: T) => ReactNode;
  /** Return a comparable value to enable sorting on this column. */
  sortValue?: (row: T) => string | number | null | undefined;
  align?: "left" | "right" | "center";
  className?: string;
  headerClassName?: string;
};

type SortState = { key: string; dir: "asc" | "desc" } | null;

interface DataTableProps<T> {
  columns: Column<T>[];
  rows: T[];
  getRowId: (row: T) => string | number;
  onRowClick?: (row: T) => void;
  /** Return a string to match the search query against. Enables the search box. */
  searchText?: (row: T) => string;
  searchPlaceholder?: string;
  initialSort?: SortState;
  pageSize?: number;
  loading?: boolean;
  emptyMessage?: string;
  /** Extra controls rendered on the right of the toolbar. */
  toolbar?: ReactNode;
}

const alignClass = { left: "text-left", right: "text-right", center: "text-center" } as const;

export function DataTable<T>({
  columns,
  rows,
  getRowId,
  onRowClick,
  searchText,
  searchPlaceholder = "Search…",
  initialSort = null,
  pageSize,
  loading = false,
  emptyMessage = "No records.",
  toolbar,
}: DataTableProps<T>) {
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<SortState>(initialSort);
  const [page, setPage] = useState(0);

  const filtered = useMemo(() => {
    if (!searchText || !query.trim()) return rows;
    const q = query.trim().toLowerCase();
    return rows.filter((r) => searchText(r).toLowerCase().includes(q));
  }, [rows, query, searchText]);

  const sorted = useMemo(() => {
    if (!sort) return filtered;
    const col = columns.find((c) => c.key === sort.key);
    if (!col?.sortValue) return filtered;
    const dir = sort.dir === "asc" ? 1 : -1;
    return [...filtered].sort((a, b) => {
      const av = col.sortValue!(a);
      const bv = col.sortValue!(b);
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      if (typeof av === "number" && typeof bv === "number") return (av - bv) * dir;
      return String(av).localeCompare(String(bv)) * dir;
    });
  }, [filtered, sort, columns]);

  const pageCount = pageSize ? Math.max(1, Math.ceil(sorted.length / pageSize)) : 1;
  const safePage = Math.min(page, pageCount - 1);
  const visible = pageSize ? sorted.slice(safePage * pageSize, safePage * pageSize + pageSize) : sorted;

  const toggleSort = (col: Column<T>) => {
    if (!col.sortValue) return;
    setPage(0);
    setSort((prev) => {
      if (prev?.key !== col.key) return { key: col.key, dir: "asc" };
      if (prev.dir === "asc") return { key: col.key, dir: "desc" };
      return null; // third click clears sort
    });
  };

  return (
    <div className="space-y-2">
      {(searchText || toolbar) && (
        <div className="flex flex-wrap items-center gap-2">
          {searchText && (
            <div className="relative flex-1 sm:max-w-xs">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-brand-muted" />
              <input
                value={query}
                onChange={(e) => {
                  setQuery(e.target.value);
                  setPage(0);
                }}
                placeholder={searchPlaceholder}
                className="w-full rounded-md border border-brand-border bg-card py-1.5 pl-8 pr-3 text-sm outline-none focus:border-signal-red"
              />
            </div>
          )}
          {toolbar}
          <span className="ml-auto text-[11px] text-brand-muted">
            {sorted.length} {sorted.length === 1 ? "row" : "rows"}
          </span>
        </div>
      )}

      <div className="table-shell">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-brand-border bg-brand-surface">
              {columns.map((col) => {
                const active = sort?.key === col.key;
                const icon = col.sortValue
                  ? active
                    ? sort!.dir === "asc"
                      ? <ArrowUp className="h-3 w-3 text-brand-dark" />
                      : <ArrowDown className="h-3 w-3 text-brand-dark" />
                    : <ArrowUpDown className="h-3 w-3 opacity-40" />
                  : null;
                return (
                  <th
                    key={col.key}
                    scope="col"
                    aria-sort={active ? (sort!.dir === "asc" ? "ascending" : "descending") : undefined}
                    className={[
                      "table-header px-3 py-2",
                      alignClass[col.align ?? "left"],
                      col.headerClassName ?? "",
                    ].join(" ")}
                  >
                    {col.sortValue ? (
                      // A real button, so sorting works from the keyboard too.
                      <button
                        type="button"
                        onClick={() => toggleSort(col)}
                        className={[
                          "-mx-1 inline-flex select-none items-center gap-1 rounded px-1 uppercase tracking-wider hover:text-brand-dark",
                          active ? "text-brand-dark" : "",
                        ].join(" ")}
                      >
                        {col.header}
                        {icon}
                      </button>
                    ) : (
                      col.header
                    )}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              // Skeleton rows keep the table's shape, so nothing jumps when data lands.
              Array.from({ length: Math.min(pageSize ?? 6, 6) }, (_, r) => (
                <tr key={`sk-${r}`} className="border-b border-brand-border last:border-0" aria-hidden>
                  {columns.map((col, c) => (
                    <td key={col.key} className={["px-3 py-3", alignClass[col.align ?? "left"]].join(" ")}>
                      <div
                        className={[
                          "skeleton inline-block h-3 max-w-full",
                          SKELETON_WIDTHS[(r + c * 2) % SKELETON_WIDTHS.length],
                        ].join(" ")}
                      />
                    </td>
                  ))}
                </tr>
              ))
            ) : visible.length === 0 ? (
              <tr>
                <td colSpan={columns.length} className="px-3 py-12 text-center">
                  <div className="mx-auto flex max-w-xs flex-col items-center gap-2">
                    <span className="grid h-9 w-9 place-items-center rounded-full bg-subtle text-brand-muted">
                      {query.trim() ? <Search size={16} /> : <Inbox size={16} />}
                    </span>
                    <p className="text-sm text-brand-muted">
                      {query.trim() ? <>No rows match &ldquo;{query.trim()}&rdquo;.</> : emptyMessage}
                    </p>
                    {query.trim() && (
                      <button type="button" onClick={() => setQuery("")} className="text-xs font-medium text-signal-red hover:underline">
                        Clear search
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ) : (
              visible.map((row) => (
                <tr
                  key={getRowId(row)}
                  onClick={onRowClick ? () => onRowClick(row) : undefined}
                  className={[
                    "border-b border-brand-border last:border-0",
                    onRowClick ? "cursor-pointer hover:bg-brand-surface" : "",
                  ].join(" ")}
                >
                  {columns.map((col) => (
                    <td key={col.key} className={["px-3 py-2.5", alignClass[col.align ?? "left"], col.className ?? ""].join(" ")}>
                      {col.render ? col.render(row) : String(col.sortValue?.(row) ?? "")}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {pageSize && pageCount > 1 && (
        <div className="flex items-center justify-end gap-2 text-xs text-brand-muted">
          <span className="tabular">
            Page {safePage + 1} of {pageCount}
          </span>
          <button
            type="button"
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={safePage === 0}
            aria-label="Previous page"
            className="inline-flex items-center rounded-md border border-brand-border bg-card p-1 hover:bg-subtle active:scale-[0.96] disabled:opacity-40"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}
            disabled={safePage >= pageCount - 1}
            aria-label="Next page"
            className="inline-flex items-center rounded-md border border-brand-border bg-card p-1 hover:bg-subtle active:scale-[0.96] disabled:opacity-40"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      )}
    </div>
  );
}

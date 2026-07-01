"use client";
import { useTheme } from "@/lib/theme";
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from "recharts";

// Categorical palette for the supplier slices (theme-aware). The last entry is a
// muted grey reserved for the aggregated "Others" slice the backend appends.
const PALETTE_LIGHT = ["#E11D2E", "#F59E0B", "#10B981", "#3B82F6", "#8B5CF6", "#EC4899", "#14B8A6", "#F97316", "#6B7280"];
const PALETTE_DARK = ["#F4434E", "#FBBF24", "#34D399", "#60A5FA", "#A78BFA", "#F472B6", "#2DD4BF", "#FB923C", "#9CA3AF"];

export interface SupplierSlice {
  name: string;
  value: number;
}

/** Supplier-distribution donut driven by explicit {name,value} slices (top-N +
 * "Others", computed server-side). Optional onSliceClick lets a caller drill the
 * PO table into that supplier. Mirrors SignalDonut's look. */
export default function SupplierDonut({
  data,
  title = "Supplier Distribution",
  onSliceClick,
}: {
  data: SupplierSlice[];
  title?: string;
  onSliceClick?: (name: string) => void;
}) {
  const isDark = useTheme((s) => s.isDark);
  const palette = isDark ? PALETTE_DARK : PALETTE_LIGHT;
  const total = data.reduce((a, b) => a + b.value, 0);
  const clickable = Boolean(onSliceClick);

  return (
    <div className="card p-4">
      <div className="font-semibold text-sm mb-3">{title}</div>
      {total === 0 ? (
        <div className="py-8 text-center text-xs text-brand-muted">No supplier data for the current view.</div>
      ) : (
        <div className="flex items-center gap-4">
          <div className="h-36 w-36">
            <ResponsiveContainer>
              <PieChart>
                <Tooltip />
                <Pie
                  data={data}
                  dataKey="value"
                  nameKey="name"
                  innerRadius={45}
                  outerRadius={65}
                  stroke="none"
                  onClick={clickable ? (d: { name?: string }) => d?.name && onSliceClick!(d.name) : undefined}
                >
                  {data.map((_, i) => (
                    <Cell key={i} fill={palette[i % palette.length]} cursor={clickable ? "pointer" : "default"} />
                  ))}
                </Pie>
              </PieChart>
            </ResponsiveContainer>
          </div>
          <ul className="max-h-36 flex-1 space-y-1 overflow-y-auto text-xs">
            {data.map((d, i) => (
              <li
                key={d.name}
                className={`flex items-center justify-between ${clickable ? "cursor-pointer hover:text-brand-dark" : ""}`}
                onClick={clickable ? () => onSliceClick!(d.name) : undefined}
              >
                <span className="flex min-w-0 items-center gap-2">
                  <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: palette[i % palette.length] }} />
                  <span className="truncate" title={d.name}>
                    {d.name}
                  </span>
                </span>
                <span className="shrink-0 font-semibold">
                  {d.value}
                  {total ? ` (${Math.round((d.value / total) * 100)}%)` : ""}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

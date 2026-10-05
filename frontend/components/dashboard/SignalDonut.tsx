"use client";
import { useTheme } from "@/lib/theme";
import { useT } from "@/lib/i18n";
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from "recharts";

/** Signal-distribution donut driven by explicit counts (theme-aware). Used by the
 * staff/employee dashboards (via StatusDonut, from the store) and the supplier
 * dashboard (counts derived from its PO list). */
export default function SignalDonut({
  green,
  yellow,
  red,
  black,
  title = "Signal Distribution",
  onSliceClick,
}: {
  green: number;
  yellow: number;
  red: number;
  black: number;
  title?: string;
  // Optional drill-down: called with the uppercase signal ("GREEN"|"YELLOW"|
  // "RED"|"BLACK") when a slice or legend row is clicked.
  onSliceClick?: (signal: string) => void;
}) {
  const { t } = useT();
  const isDark = useTheme((s) => s.isDark);
  // `signal` drives drill-down; `name` is the translated label shown in the legend/tooltip.
  const data = [
    { signal: "GREEN", name: t("Green"), value: green, color: isDark ? "#34D399" : "#10B981" },
    { signal: "YELLOW", name: t("Yellow"), value: yellow, color: isDark ? "#FBBF24" : "#F59E0B" },
    { signal: "RED", name: t("Red"), value: red, color: isDark ? "#F4434E" : "#E11D2E" },
    // "Black" would vanish on a dark card — use a light ink in dark mode.
    { signal: "BLACK", name: t("Black"), value: black, color: isDark ? "#E6EAF0" : "#111827" },
  ];
  const total = data.reduce((a, b) => a + b.value, 0);
  const clickable = Boolean(onSliceClick);
  return (
    <div className="card p-4">
      <div className="font-semibold text-sm mb-3">{t(title)}</div>
      <div className="flex items-center gap-4">
        <div className="h-36 w-36">
          <ResponsiveContainer>
            <PieChart>
              <Tooltip />
              <Pie
                data={data}
                dataKey="value"
                innerRadius={45}
                outerRadius={65}
                stroke="none"
                onClick={clickable ? (_d: unknown, i: number) => data[i] && onSliceClick!(data[i].signal) : undefined}
              >
                {data.map((d, i) => (
                  <Cell key={i} fill={d.color} cursor={clickable ? "pointer" : "default"} />
                ))}
              </Pie>
            </PieChart>
          </ResponsiveContainer>
        </div>
        <ul className="flex-1 space-y-1 text-xs">
          {data.map((d) => (
            <li
              key={d.signal}
              className={`flex items-center justify-between ${clickable ? "cursor-pointer hover:text-brand-dark" : ""}`}
              onClick={clickable ? () => onSliceClick!(d.signal) : undefined}
            >
              <span className="flex items-center gap-2">
                <span className="h-2 w-2 rounded-full" style={{ background: d.color }} />
                {d.name}
              </span>
              <span className="font-semibold">
                {d.value}
                {total ? ` (${Math.round((d.value / total) * 100)}%)` : ""}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

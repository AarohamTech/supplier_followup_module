"use client";
import { useStore } from "@/lib/store";
import { useTheme } from "@/lib/theme";
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from "recharts";

export default function StatusDonut() {
  const k = useStore((s) => s.kpis);
  const isDark = useTheme((s) => s.isDark);
  const data = [
    { name: "Green", value: k?.green_count ?? 0, color: isDark ? "#34D399" : "#10B981" },
    { name: "Yellow", value: k?.yellow_count ?? 0, color: isDark ? "#FBBF24" : "#F59E0B" },
    { name: "Red", value: k?.red_count ?? 0, color: isDark ? "#F4434E" : "#E11D2E" },
    // "Black" would vanish on a dark card — use a light ink in dark mode.
    { name: "Black", value: k?.black_count ?? 0, color: isDark ? "#E6EAF0" : "#111827" },
  ];
  const total = data.reduce((a, b) => a + b.value, 0);
  return (
    <div className="card p-4">
      <div className="font-semibold text-sm mb-3">Signal Distribution</div>
      <div className="flex items-center gap-4">
        <div className="h-36 w-36">
          <ResponsiveContainer>
            <PieChart>
              <Tooltip />
              <Pie data={data} dataKey="value" innerRadius={45} outerRadius={65} stroke="none">
                {data.map((d, i) => <Cell key={i} fill={d.color} />)}
              </Pie>
            </PieChart>
          </ResponsiveContainer>
        </div>
        <ul className="flex-1 space-y-1 text-xs">
          {data.map((d) => (
            <li key={d.name} className="flex items-center justify-between">
              <span className="flex items-center gap-2"><span className="h-2 w-2 rounded-full" style={{ background: d.color }} />{d.name}</span>
              <span className="font-semibold">{d.value}{total ? ` (${Math.round(d.value / total * 100)}%)` : ""}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

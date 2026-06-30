"use client";
import { useStore } from "@/lib/store";
import { useTheme } from "@/lib/theme";
import { BarChart, Bar, XAxis, YAxis, ResponsiveContainer, Tooltip, CartesianGrid } from "recharts";

export default function OverdueDonut() {
  const k = useStore((s) => s.kpis);
  const isDark = useTheme((s) => s.isDark);
  const grid = isDark ? "#262C36" : "#eef";
  const axis = isDark ? "#9BA3AE" : "#6B7280";
  const data = [
    { name: "Total", value: k?.total_records ?? 0 },
    { name: "Overdue", value: k?.overdue_count ?? 0 },
    { name: "Due Today", value: k?.due_today_count ?? 0 },
    { name: "HI Req.", value: k?.ai_required_count ?? 0 },
  ];
  return (
    <div className="card p-4">
      <div className="font-semibold text-sm mb-3">Workload Overview</div>
      <div className="h-44">
        <ResponsiveContainer>
          <BarChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke={grid} />
            <XAxis dataKey="name" tick={{ fontSize: 11, fill: axis }} stroke={grid} />
            <YAxis tick={{ fontSize: 11, fill: axis }} stroke={grid} allowDecimals={false} />
            <Tooltip />
            <Bar dataKey="value" fill={isDark ? "#F4434E" : "#E11D2E"} radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

"use client";
import { useStore } from "@/lib/store";
import PageHeader from "@/components/layout/PageHeader";
import { BarChart3 } from "lucide-react";
import { BarChart, Bar, XAxis, YAxis, ResponsiveContainer, Tooltip, CartesianGrid, Legend } from "recharts";

export default function Page() {
  const list = useStore((s) => s.list);
  const items = list?.items ?? [];

  const map = new Map<string, { GREEN: number; YELLOW: number; RED: number; BLACK: number }>();
  items.forEach((r) => {
    const key = r.supplier_name || "Unknown";
    if (!map.has(key)) map.set(key, { GREEN: 0, YELLOW: 0, RED: 0, BLACK: 0 });
    const sig = (r.signal ?? "").toUpperCase() as "GREEN" | "YELLOW" | "RED" | "BLACK";
    if (map.get(key)![sig] !== undefined) map.get(key)![sig] += 1;
  });
  const supplierData = Array.from(map.entries()).map(([name, v]) => ({ name, ...v }));

  const statusMap = new Map<string, number>();
  items.forEach((r) => {
    const key = r.po_status || "Unknown";
    statusMap.set(key, (statusMap.get(key) ?? 0) + 1);
  });
  const statusData = Array.from(statusMap.entries()).map(([name, value]) => ({ name, value }));

  return (
    <div className="page-stack">
      <PageHeader
        title="Reports & Analytics"
        description="Visual signal mix, PO status lines and critical procurement follow-ups."
        icon={BarChart3}
      />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="card p-4">
          <div className="font-semibold text-sm mb-2">Supplier-wise Signal Mix</div>
          <div className="h-72">
            <ResponsiveContainer>
              <BarChart data={supplierData} layout="vertical" margin={{ left: 50 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#eef" />
                <XAxis type="number" tick={{ fontSize: 11 }} allowDecimals={false} />
                <YAxis type="category" dataKey="name" tick={{ fontSize: 11 }} width={180} />
                <Tooltip />
                <Legend />
                <Bar dataKey="GREEN" stackId="a" fill="#10B981" />
                <Bar dataKey="YELLOW" stackId="a" fill="#F59E0B" />
                <Bar dataKey="RED" stackId="a" fill="#E11D2E" />
                <Bar dataKey="BLACK" stackId="a" fill="#111827" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="card p-4">
          <div className="font-semibold text-sm mb-2">PO Status Lines</div>
          <div className="h-72">
            <ResponsiveContainer>
              <BarChart data={statusData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#eef" />
                <XAxis dataKey="name" tick={{ fontSize: 10 }} interval={0} angle={-15} height={60} />
                <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                <Tooltip />
                <Bar dataKey="value" fill="#3B82F6" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      <div className="card p-4">
        <div className="font-semibold text-sm mb-3">Critical Procurement Lines (RED + BLACK)</div>
        <table className="min-w-full text-sm">
          <thead className="bg-gray-50">
            <tr>{["PO No.", "SUPPLIER", "MATERIAL", "QTY", "SIGNAL", "STATUS"].map((h) => (
              <th key={h} className="text-left px-3 py-2 table-header">{h}</th>
            ))}</tr>
          </thead>
          <tbody>
            {items.filter((r) => r.signal === "RED" || r.signal === "BLACK").map((r) => (
              <tr key={r.id} className="border-t border-brand-border">
                <td className="px-3 py-2">{r.supplier_po_no}</td>
                <td className="px-3 py-2">{r.supplier_name}</td>
                <td className="px-3 py-2 max-w-[300px] truncate">{r.material_name}</td>
                <td className="px-3 py-2">{r.qty}</td>
                <td className="px-3 py-2 font-semibold">{r.signal}</td>
                <td className="px-3 py-2 text-xs">{r.followup_status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

"use client";

import { useState } from "react";
import { Download, Loader2 } from "lucide-react";
import {
  Bar,
  BarChart,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { getToken } from "@/lib/auth-token";
import { useTheme } from "@/lib/theme";
import { fmtDate } from "@/lib/format";
import type { WorkloadOpenTask, WorkloadPendingPo, WorkloadThroughputDay } from "@/lib/types";

export function signalChip(signal?: string | null): string {
  switch ((signal || "").toUpperCase()) {
    case "BLACK":
      return "bg-black text-white dark:bg-gray-100 dark:text-gray-900";
    case "RED":
      return "bg-red-50 text-signal-red";
    case "YELLOW":
      return "bg-amber-50 text-amber-700";
    case "GREEN":
      return "bg-emerald-50 text-emerald-700";
    default:
      return "bg-subtle text-brand-muted";
  }
}

export function Tile({ label, value, accent }: { label: string; value: number | string; accent?: boolean }) {
  const isWarn = accent && typeof value === "number" && value > 0;
  return (
    <div className="card px-4 py-3">
      <div className="text-[10px] font-semibold uppercase tracking-wider text-brand-muted">{label}</div>
      <div className={`mt-0.5 text-2xl font-semibold tabular-nums ${isWarn ? "text-signal-red" : "text-brand-dark"}`}>
        {typeof value === "number" ? value.toLocaleString() : value}
      </div>
    </div>
  );
}

export function Num({ v, warn }: { v: number; warn?: boolean }) {
  return (
    <span className={`tabular-nums ${warn && v > 0 ? "font-semibold text-signal-red" : v === 0 ? "text-brand-muted" : "text-brand-dark"}`}>
      {v}
    </span>
  );
}

/** Authenticated xlsx download (mirrors the task-analytics export pattern). */
export async function downloadXlsx(url: string, filename: string): Promise<void> {
  const token = getToken();
  const res = await fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
  if (!res.ok) throw new Error(`Export failed: ${res.status} ${res.statusText}`);
  const blob = await res.blob();
  const href = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = href;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(href);
}

export function ExportButton({ url, filename, label = "Export Excel" }: { url: string; filename: string; label?: string }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  return (
    <button
      className="btn-outline h-9"
      disabled={busy}
      title={err ?? "Download as .xlsx for meetings"}
      onClick={() => {
        setBusy(true);
        setErr(null);
        downloadXlsx(url, filename)
          .catch((e) => setErr((e as Error).message))
          .finally(() => setBusy(false));
      }}
    >
      {busy ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />}
      <span className="hidden sm:inline">{err ? "Retry export" : label}</span>
    </button>
  );
}

/** 14-day created vs completed task throughput — two fixed-hue series + legend. */
export function ThroughputChart({ data }: { data: WorkloadThroughputDay[] }) {
  const isDark = useTheme((s) => s.isDark);
  const created = isDark ? "#60A5FA" : "#3B82F6";
  const completed = isDark ? "#A78BFA" : "#8B5CF6";
  const ink = isDark ? "#9AA3B2" : "#6B7280";
  const rows = data.map((d) => ({ ...d, label: d.day.slice(5) }));
  return (
    <div className="card p-4">
      <div className="mb-3 text-sm font-semibold">Task throughput — last 14 days</div>
      <div className="h-52">
        <ResponsiveContainer>
          <BarChart data={rows} barGap={2}>
            <XAxis dataKey="label" tick={{ fontSize: 10, fill: ink }} tickLine={false} axisLine={false} />
            <YAxis allowDecimals={false} width={24} tick={{ fontSize: 10, fill: ink }} tickLine={false} axisLine={false} />
            <Tooltip cursor={{ fill: isDark ? "#ffffff14" : "#00000008" }} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Bar dataKey="created" name="Created" fill={created} radius={[3, 3, 0, 0]} maxBarSize={14} />
            <Bar dataKey="completed" name="Completed" fill={completed} radius={[3, 3, 0, 0]} maxBarSize={14} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export function BreakdownChips({ title, data }: { title: string; data: Record<string, number> }) {
  const entries = Object.entries(data).sort((a, b) => b[1] - a[1]);
  return (
    <div className="card p-4">
      <div className="mb-2 text-sm font-semibold">{title}</div>
      {entries.length === 0 ? (
        <div className="text-xs text-brand-muted">No tasks yet.</div>
      ) : (
        <div className="flex flex-wrap gap-1.5">
          {entries.map(([k, v]) => (
            <span key={k} className="inline-flex items-center gap-1.5 rounded-md bg-subtle px-2 py-1 text-[11px] font-medium text-brand-dark">
              {k.replaceAll("_", " ")}
              <span className="font-semibold tabular-nums">{v}</span>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

export function PendingPoTable({ rows, showSupplier }: { rows: WorkloadPendingPo[]; showSupplier?: boolean }) {
  return (
    <section className="card overflow-hidden">
      <div className="border-b border-brand-border px-4 py-3">
        <h2 className="text-sm font-semibold text-brand-dark">Pending PO lines ({rows.length})</h2>
        <p className="text-xs text-brand-muted">Not yet dispatched/closed — earliest ship date first.</p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-brand-border bg-subtle/60 text-left text-[10px] uppercase tracking-wider text-brand-muted">
              <th className="px-4 py-2 font-semibold">PO / Material</th>
              {showSupplier && <th className="px-3 py-2 font-semibold">Supplier</th>}
              <th className="px-3 py-2 font-semibold">Signal</th>
              <th className="px-3 py-2 text-right font-semibold">Qty</th>
              <th className="px-3 py-2 font-semibold">Status</th>
              <th className="px-3 py-2 text-right font-semibold">Ship date</th>
              <th className="px-3 py-2 text-right font-semibold">Days overdue</th>
              <th className="px-3 py-2 text-right font-semibold">Follow-ups</th>
              <th className="px-4 py-2 text-right font-semibold">Commitment</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-brand-border">
            {rows.map((r) => (
              <tr key={r.procurement_record_id} className="hover:bg-subtle/50">
                <td className="max-w-[280px] px-4 py-2">
                  <div className="font-medium text-brand-dark">{r.supplier_po_no}</div>
                  <div className="truncate text-[10px] text-brand-muted" title={r.material_name}>{r.material_name}</div>
                </td>
                {showSupplier && <td className="max-w-[160px] truncate px-3 py-2 text-brand-dark">{r.supplier_name || "—"}</td>}
                <td className="px-3 py-2">
                  {r.signal ? <span className={`badge ${signalChip(r.signal)}`}>{r.signal}</span> : <span className="text-brand-muted">—</span>}
                </td>
                <td className="px-3 py-2 text-right tabular-nums text-brand-dark">
                  {r.qty != null ? `${r.qty.toLocaleString()}${r.uom ? ` ${r.uom}` : ""}` : "—"}
                </td>
                <td className="px-3 py-2 text-brand-dark">{r.po_status || "—"}</td>
                <td className="px-3 py-2 text-right text-brand-dark">{r.shipment_date ? fmtDate(r.shipment_date) : "—"}</td>
                <td className="px-3 py-2 text-right"><Num v={r.days_overdue ?? 0} warn /></td>
                <td className="px-3 py-2 text-right"><Num v={r.followup_count} /></td>
                <td className="px-4 py-2 text-right text-brand-dark">{r.commitment_date ? fmtDate(r.commitment_date) : "—"}</td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={showSupplier ? 9 : 8} className="px-4 py-8 text-center text-brand-muted">Nothing pending. 🎉</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function OpenTaskTable({ rows }: { rows: WorkloadOpenTask[] }) {
  return (
    <section className="card overflow-hidden">
      <div className="border-b border-brand-border px-4 py-3">
        <h2 className="text-sm font-semibold text-brand-dark">Open tasks ({rows.length})</h2>
        <p className="text-xs text-brand-muted">Everything not done — earliest due first.</p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-brand-border bg-subtle/60 text-left text-[10px] uppercase tracking-wider text-brand-muted">
              <th className="px-4 py-2 font-semibold">Task</th>
              <th className="px-3 py-2 font-semibold">Priority</th>
              <th className="px-3 py-2 font-semibold">Status</th>
              <th className="px-3 py-2 font-semibold">Source</th>
              <th className="px-3 py-2 font-semibold">Supplier / PO</th>
              <th className="px-3 py-2 text-right font-semibold">Due</th>
              <th className="px-3 py-2 text-right font-semibold">Days overdue</th>
              <th className="px-4 py-2 text-right font-semibold">Progress</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-brand-border">
            {rows.map((t) => (
              <tr key={t.id} className="hover:bg-subtle/50">
                <td className="max-w-[280px] px-4 py-2">
                  <div className="truncate font-medium text-brand-dark" title={t.title}>{t.title}</div>
                </td>
                <td className="px-3 py-2 font-semibold text-brand-dark">{t.priority}</td>
                <td className="px-3 py-2 text-brand-dark">{t.status.replaceAll("_", " ")}</td>
                <td className="px-3 py-2 text-brand-muted">{t.task_source || "—"}</td>
                <td className="max-w-[180px] px-3 py-2">
                  <div className="truncate text-brand-dark">{t.supplier_name || "—"}</div>
                  {t.supplier_po_no && <div className="text-[10px] text-brand-muted">PO {t.supplier_po_no}</div>}
                </td>
                <td className="px-3 py-2 text-right text-brand-dark">{t.due_date ? fmtDate(t.due_date) : "—"}</td>
                <td className="px-3 py-2 text-right"><Num v={t.days_overdue ?? 0} warn /></td>
                <td className="px-4 py-2 text-right tabular-nums text-brand-dark">{t.progress_percent}%</td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={8} className="px-4 py-8 text-center text-brand-muted">No open tasks.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

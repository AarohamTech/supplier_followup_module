"use client";

import { useEffect, useMemo, useState } from "react";
import { Loader2, PieChart, RefreshCcw, ShieldCheck, Search } from "lucide-react";

import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useTheme } from "@/lib/theme";
import { fmtDate } from "@/lib/format";
import type { WorkloadReport, WorkloadSupplierRow, WorkloadUserRow } from "@/lib/types";
import SignalDonut from "@/components/dashboard/SignalDonut";
import PageHeader from "@/components/layout/PageHeader";

function signalChip(signal?: string | null): string {
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

function Tile({ label, value, accent }: { label: string; value: number; accent?: boolean }) {
  return (
    <div className="card px-4 py-3">
      <div className="text-[10px] font-semibold uppercase tracking-wider text-brand-muted">{label}</div>
      <div className={`mt-0.5 text-2xl font-semibold tabular-nums ${accent && value > 0 ? "text-signal-red" : "text-brand-dark"}`}>
        {value.toLocaleString()}
      </div>
    </div>
  );
}

function Num({ v, warn }: { v: number; warn?: boolean }) {
  return (
    <span className={`tabular-nums ${warn && v > 0 ? "font-semibold text-signal-red" : v === 0 ? "text-brand-muted" : "text-brand-dark"}`}>
      {v}
    </span>
  );
}

export default function WorkloadReportPage() {
  const { hasRole } = useAuth();
  const isDark = useTheme((s) => s.isDark);
  const [data, setData] = useState<WorkloadReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [userQuery, setUserQuery] = useState("");
  const [supQuery, setSupQuery] = useState("");

  const isAdmin = hasRole("admin");

  const load = () => {
    setLoading(true);
    setError(null);
    api
      .workloadReport()
      .then(setData)
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    if (isAdmin) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAdmin]);

  const users = useMemo<WorkloadUserRow[]>(() => {
    const q = userQuery.trim().toLowerCase();
    const rows = data?.users ?? [];
    if (!q) return rows;
    return rows.filter(
      (u) =>
        (u.name || "").toLowerCase().includes(q) ||
        (u.emp_code || "").toLowerCase().includes(q) ||
        (u.role || "").toLowerCase().includes(q),
    );
  }, [data, userQuery]);

  const suppliers = useMemo<WorkloadSupplierRow[]>(() => {
    const q = supQuery.trim().toLowerCase();
    const rows = data?.suppliers ?? [];
    if (!q) return rows;
    return rows.filter((s) => (s.supplier_name || "").toLowerCase().includes(q));
  }, [data, supQuery]);

  // Single-hue magnitude bars (workload, not status): blue, never the signal red.
  const barHue = isDark ? "#60A5FA" : "#3B82F6";
  const busiest = useMemo(() => {
    const rows = (data?.users ?? []).filter((u) => u.tasks.open > 0 || u.pos.pending > 0);
    return rows.slice(0, 12);
  }, [data]);
  const busiestMax = Math.max(1, ...busiest.map((u) => u.tasks.open + u.pos.pending));

  if (!isAdmin) {
    return (
      <div className="empty-state">
        <ShieldCheck className="mx-auto mb-2 h-6 w-6 text-brand-muted" />
        You need the <strong>admin</strong> role to view the workload report.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="Workload Report"
        description="Per-user, per-supplier and overall workload — pending POs, tasks, mail and shipments."
        icon={PieChart}
        tone="red"
        actions={
          <button onClick={load} className="btn-outline h-9" disabled={loading}>
            {loading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCcw size={14} />}
            <span className="hidden sm:inline">Refresh</span>
          </button>
        }
      />

      {error && (
        <div role="alert" className="rounded-md border border-red-100 bg-red-50 px-3 py-2 text-xs text-signal-red">
          {error}
        </div>
      )}

      {!data && loading && (
        <div className="empty-state">
          <Loader2 className="mx-auto mb-2 h-5 w-5 animate-spin text-brand-muted" /> Building report…
        </div>
      )}

      {data && (
        <>
          {/* Overall headline numbers */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 xl:grid-cols-8">
            <Tile label="Internal users" value={data.overall.internal_users} />
            <Tile label="Active suppliers" value={data.overall.suppliers_active} />
            <Tile label="Pending POs" value={data.overall.pos.pending} />
            <Tile label="Overdue POs" value={data.overall.pos.overdue} accent />
            <Tile label="Open tasks" value={data.overall.tasks.open} />
            <Tile label="Overdue tasks" value={data.overall.tasks.overdue} accent />
            <Tile label="Unread inbound" value={data.overall.unread_inbound} />
            <Tile label="ASNs in transit" value={data.overall.asns_in_transit} />
          </div>

          <div className="grid gap-3 lg:grid-cols-2">
            <SignalDonut
              title="Overall PO signal mix"
              green={data.overall.pos.green}
              yellow={data.overall.pos.yellow}
              red={data.overall.pos.red}
              black={data.overall.pos.black}
            />

            {/* Workload bars: open tasks + pending POs per user (magnitude, one hue) */}
            <div className="card p-4">
              <div className="mb-3 text-sm font-semibold">Busiest people — open tasks + pending POs</div>
              {busiest.length === 0 ? (
                <div className="py-8 text-center text-xs text-brand-muted">No open workload right now.</div>
              ) : (
                <ul className="space-y-2">
                  {busiest.map((u) => {
                    const val = u.tasks.open + u.pos.pending;
                    return (
                      <li key={u.user_id} className="flex items-center gap-2 text-xs" title={`${u.name}: ${u.tasks.open} open tasks · ${u.pos.pending} pending POs`}>
                        <span className="w-36 truncate text-brand-dark">{u.name}</span>
                        <span className="relative h-3.5 flex-1 overflow-hidden rounded bg-subtle">
                          <span
                            className="absolute inset-y-0 left-0 rounded"
                            style={{ width: `${(val / busiestMax) * 100}%`, background: barHue }}
                          />
                        </span>
                        <span className="w-8 text-right font-semibold tabular-nums text-brand-dark">{val}</span>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          </div>

          {/* Per-user detail */}
          <section className="card overflow-hidden">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-brand-border px-4 py-3">
              <div>
                <h2 className="text-sm font-semibold text-brand-dark">By user</h2>
                <p className="text-xs text-brand-muted">Owned POs (via desk code) and assigned tasks per internal account.</p>
              </div>
              <div className="relative">
                <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-brand-muted" />
                <input
                  value={userQuery}
                  onChange={(e) => setUserQuery(e.target.value)}
                  placeholder="Filter users…"
                  className="input h-8 w-52 pl-8 text-xs"
                />
              </div>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-brand-border bg-subtle/60 text-left text-[10px] uppercase tracking-wider text-brand-muted">
                    <th className="px-4 py-2 font-semibold">User</th>
                    <th className="px-3 py-2 text-right font-semibold">Pending POs</th>
                    <th className="px-3 py-2 text-right font-semibold">Overdue POs</th>
                    <th className="px-3 py-2 text-right font-semibold">Red/Black POs</th>
                    <th className="px-3 py-2 text-right font-semibold">Open tasks</th>
                    <th className="px-3 py-2 text-right font-semibold">Overdue tasks</th>
                    <th className="px-3 py-2 text-right font-semibold">Due today</th>
                    <th className="px-3 py-2 text-right font-semibold">Done</th>
                    <th className="px-4 py-2 text-right font-semibold">Last login</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-brand-border">
                  {users.map((u) => (
                    <tr key={u.user_id} className="hover:bg-subtle/50">
                      <td className="px-4 py-2">
                        <div className="font-medium text-brand-dark">{u.name}</div>
                        <div className="text-[10px] text-brand-muted">
                          {u.role}
                          {u.emp_code ? ` · ${u.emp_code}` : ""}
                        </div>
                      </td>
                      <td className="px-3 py-2 text-right"><Num v={u.pos.pending} /></td>
                      <td className="px-3 py-2 text-right"><Num v={u.pos.overdue} warn /></td>
                      <td className="px-3 py-2 text-right"><Num v={u.pos.red + u.pos.black} warn /></td>
                      <td className="px-3 py-2 text-right"><Num v={u.tasks.open} /></td>
                      <td className="px-3 py-2 text-right"><Num v={u.tasks.overdue} warn /></td>
                      <td className="px-3 py-2 text-right"><Num v={u.tasks.due_today} /></td>
                      <td className="px-3 py-2 text-right"><Num v={u.tasks.done} /></td>
                      <td className="px-4 py-2 text-right text-brand-muted">{u.last_login_at ? fmtDate(u.last_login_at) : "—"}</td>
                    </tr>
                  ))}
                  {users.length === 0 && (
                    <tr>
                      <td colSpan={9} className="px-4 py-8 text-center text-brand-muted">No users match.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>

          {/* Per-supplier detail */}
          <section className="card overflow-hidden">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-brand-border px-4 py-3">
              <div>
                <h2 className="text-sm font-semibold text-brand-dark">By supplier</h2>
                <p className="text-xs text-brand-muted">POs, tasks, mail and shipments per active supplier — worst first.</p>
              </div>
              <div className="relative">
                <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-brand-muted" />
                <input
                  value={supQuery}
                  onChange={(e) => setSupQuery(e.target.value)}
                  placeholder="Filter suppliers…"
                  className="input h-8 w-52 pl-8 text-xs"
                />
              </div>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-brand-border bg-subtle/60 text-left text-[10px] uppercase tracking-wider text-brand-muted">
                    <th className="px-4 py-2 font-semibold">Supplier</th>
                    <th className="px-3 py-2 font-semibold">Signal</th>
                    <th className="px-3 py-2 text-right font-semibold">Pending POs</th>
                    <th className="px-3 py-2 text-right font-semibold">Overdue POs</th>
                    <th className="px-3 py-2 text-right font-semibold">Avg follow-ups</th>
                    <th className="px-3 py-2 text-right font-semibold">Open tasks</th>
                    <th className="px-3 py-2 text-right font-semibold">Escalations</th>
                    <th className="px-3 py-2 text-right font-semibold">Unread mail</th>
                    <th className="px-4 py-2 text-right font-semibold">ASN in transit</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-brand-border">
                  {suppliers.map((s) => (
                    <tr key={s.supplier_id} className="hover:bg-subtle/50">
                      <td className="px-4 py-2">
                        <div className="font-medium text-brand-dark">{s.supplier_name}</div>
                        <div className="text-[10px] text-brand-muted">
                          {s.pos.total} PO lines · {s.mails.incoming} in / {s.mails.outgoing} out
                        </div>
                      </td>
                      <td className="px-3 py-2">
                        {s.worst_signal ? (
                          <span className={`badge ${signalChip(s.worst_signal)}`}>{s.worst_signal}</span>
                        ) : (
                          <span className="text-brand-muted">—</span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-right"><Num v={s.pos.pending} /></td>
                      <td className="px-3 py-2 text-right"><Num v={s.pos.overdue} warn /></td>
                      <td className="px-3 py-2 text-right tabular-nums text-brand-dark">{s.pos.avg_followups.toFixed(1)}</td>
                      <td className="px-3 py-2 text-right"><Num v={s.tasks.open} /></td>
                      <td className="px-3 py-2 text-right"><Num v={s.tasks.escalations} warn /></td>
                      <td className="px-3 py-2 text-right"><Num v={s.mails.unread} /></td>
                      <td className="px-4 py-2 text-right">
                        <span className="tabular-nums text-brand-dark">{s.asns.in_transit}</span>
                        <span className="text-brand-muted"> / {s.asns.total}</span>
                      </td>
                    </tr>
                  ))}
                  {suppliers.length === 0 && (
                    <tr>
                      <td colSpan={9} className="px-4 py-8 text-center text-brand-muted">No suppliers match.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>

          <div className="text-right text-[10px] text-brand-muted">
            Generated {fmtDate(data.overall.generated_at)}
          </div>
        </>
      )}
    </div>
  );
}

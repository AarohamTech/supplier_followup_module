"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { ChevronRight, Loader2, PieChart, RefreshCcw, ShieldCheck, Search } from "lucide-react";

import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useTheme } from "@/lib/theme";
import { fmtDate } from "@/lib/format";
import type {
  WorkloadCustomerRow,
  WorkloadReport,
  WorkloadSupplierRow,
  WorkloadUserRow,
} from "@/lib/types";
import SignalDonut from "@/components/dashboard/SignalDonut";
import PageHeader from "@/components/layout/PageHeader";
import { ExportButton, Num, signalChip, Tile } from "@/components/reports/WorkloadShared";

type Tab = "overview" | "users" | "suppliers" | "customers";

const TABS: { key: Tab; label: string }[] = [
  { key: "overview", label: "Overview" },
  { key: "users", label: "By user" },
  { key: "suppliers", label: "By supplier" },
  { key: "customers", label: "By customer" },
];

export default function WorkloadReportPage() {
  const router = useRouter();
  const { hasRole } = useAuth();
  const isDark = useTheme((s) => s.isDark);
  const [data, setData] = useState<WorkloadReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("overview");
  const [userQuery, setUserQuery] = useState("");
  const [supQuery, setSupQuery] = useState("");
  const [custQuery, setCustQuery] = useState("");

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

  const customers = useMemo<WorkloadCustomerRow[]>(() => {
    const q = custQuery.trim().toLowerCase();
    const rows = data?.customers ?? [];
    if (!q) return rows;
    return rows.filter((c) => (c.customer_name || "").toLowerCase().includes(q));
  }, [data, custQuery]);

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

  const openUser = (id: number) => router.push(`/reports/workload/user/${id}`);
  const openSupplier = (id: number) => router.push(`/reports/workload/supplier/${id}`);
  const openCustomer = (name: string, signal?: string) =>
    router.push(
      `/reports/workload/customer?name=${encodeURIComponent(name)}${signal ? `&signal=${signal}` : ""}`,
    );

  return (
    <div className="space-y-4">
      <PageHeader
        title="Workload Report"
        description="Per-user, per-supplier and overall workload — click any row for the detailed report."
        icon={PieChart}
        tone="red"
        actions={
          <>
            <ExportButton
              url={api.workloadExportUrl()}
              filename={`workload-report-${new Date().toISOString().slice(0, 10)}.xlsx`}
            />
            <button onClick={load} className="btn-outline h-9" disabled={loading}>
              {loading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCcw size={14} />}
              <span className="hidden sm:inline">Refresh</span>
            </button>
          </>
        }
      />

      {/* Tab switcher: no more scrolling past one list to reach the other. */}
      <div className="flex items-center gap-1 border-b border-brand-border">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`-mb-px border-b-2 px-4 py-2 text-sm font-semibold transition ${
              tab === t.key
                ? "border-signal-red text-signal-red"
                : "border-transparent text-brand-muted hover:text-brand-dark"
            }`}
          >
            {t.label}
            {t.key === "users" && data ? ` (${data.users.length})` : ""}
            {t.key === "suppliers" && data ? ` (${data.suppliers.length})` : ""}
            {t.key === "customers" && data ? ` (${data.customers?.length ?? 0})` : ""}
          </button>
        ))}
      </div>

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

      {data && tab === "overview" && (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-9">
            <Tile label="Internal users" value={data.overall.internal_users} />
            <Tile label="Active suppliers" value={data.overall.suppliers_active} />
            <Tile label="Active customers" value={data.overall.customers_active ?? 0} />
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

            <div className="card p-4">
              <div className="mb-3 text-sm font-semibold">Busiest people — open tasks + pending POs</div>
              {busiest.length === 0 ? (
                <div className="py-8 text-center text-xs text-brand-muted">No open workload right now.</div>
              ) : (
                <ul className="space-y-2">
                  {busiest.map((u) => {
                    const val = u.tasks.open + u.pos.pending;
                    return (
                      <li key={u.user_id}>
                        <button
                          onClick={() => openUser(u.user_id)}
                          className="flex w-full items-center gap-2 rounded px-1 py-0.5 text-left text-xs hover:bg-subtle/60"
                          title={`${u.name}: ${u.tasks.open} open tasks · ${u.pos.pending} pending POs — click for detail`}
                        >
                          <span className="w-36 truncate text-brand-dark">{u.name}</span>
                          <span className="relative h-3.5 flex-1 overflow-hidden rounded bg-subtle">
                            <span
                              className="absolute inset-y-0 left-0 rounded"
                              style={{ width: `${(val / busiestMax) * 100}%`, background: barHue }}
                            />
                          </span>
                          <span className="w-8 text-right font-semibold tabular-nums text-brand-dark">{val}</span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          </div>

          <div className="text-right text-[10px] text-brand-muted">Generated {fmtDate(data.overall.generated_at)}</div>
        </>
      )}

      {data && tab === "users" && (
        <section className="card overflow-hidden">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-brand-border px-4 py-3">
            <p className="text-xs text-brand-muted">Owned POs (via desk code) and assigned tasks — click a row for the detailed report.</p>
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
                  <th className="px-3 py-2 text-right font-semibold">Red POs</th>
                  <th className="px-3 py-2 text-right font-semibold">Black POs</th>
                  <th className="px-3 py-2 text-right font-semibold">Open tasks</th>
                  <th className="px-3 py-2 text-right font-semibold">Overdue tasks</th>
                  <th className="px-3 py-2 text-right font-semibold">Due today</th>
                  <th className="px-3 py-2 text-right font-semibold">Done</th>
                  <th className="px-3 py-2 text-right font-semibold">Last login</th>
                  <th className="w-8 px-2 py-2" aria-hidden />
                </tr>
              </thead>
              <tbody className="divide-y divide-brand-border">
                {users.map((u) => (
                  <tr
                    key={u.user_id}
                    onClick={() => openUser(u.user_id)}
                    className="cursor-pointer hover:bg-subtle/50"
                    title="Open detailed report"
                  >
                    <td className="px-4 py-2">
                      <div className="font-medium text-brand-dark">{u.name}</div>
                      <div className="text-[10px] text-brand-muted">
                        {u.role}
                        {u.emp_code ? ` · ${u.emp_code}` : ""}
                      </div>
                    </td>
                    <td className="px-3 py-2 text-right"><Num v={u.pos.pending} /></td>
                    <td className="px-3 py-2 text-right"><Num v={u.pos.overdue} warn /></td>
                    <td className="px-3 py-2 text-right"><Num v={u.pos.red} warn /></td>
                    <td className="px-3 py-2 text-right"><Num v={u.pos.black} warn /></td>
                    <td className="px-3 py-2 text-right"><Num v={u.tasks.open} /></td>
                    <td className="px-3 py-2 text-right"><Num v={u.tasks.overdue} warn /></td>
                    <td className="px-3 py-2 text-right"><Num v={u.tasks.due_today} /></td>
                    <td className="px-3 py-2 text-right"><Num v={u.tasks.done} /></td>
                    <td className="px-3 py-2 text-right text-brand-muted">{u.last_login_at ? fmtDate(u.last_login_at) : "—"}</td>
                    <td className="px-2 py-2 text-brand-muted"><ChevronRight size={14} /></td>
                  </tr>
                ))}
                {users.length === 0 && (
                  <tr>
                    <td colSpan={11} className="px-4 py-8 text-center text-brand-muted">No users match.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {data && tab === "suppliers" && (
        <section className="card overflow-hidden">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-brand-border px-4 py-3">
            <p className="text-xs text-brand-muted">POs, tasks, mail and shipments per active supplier — click a row for the detailed report.</p>
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
                  <th className="px-3 py-2 text-right font-semibold">ASN in transit</th>
                  <th className="w-8 px-2 py-2" aria-hidden />
                </tr>
              </thead>
              <tbody className="divide-y divide-brand-border">
                {suppliers.map((s) => (
                  <tr
                    key={s.supplier_id}
                    onClick={() => openSupplier(s.supplier_id)}
                    className="cursor-pointer hover:bg-subtle/50"
                    title="Open detailed report"
                  >
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
                    <td className="px-3 py-2 text-right">
                      <span className="tabular-nums text-brand-dark">{s.asns.in_transit}</span>
                      <span className="text-brand-muted"> / {s.asns.total}</span>
                    </td>
                    <td className="px-2 py-2 text-brand-muted"><ChevronRight size={14} /></td>
                  </tr>
                ))}
                {suppliers.length === 0 && (
                  <tr>
                    <td colSpan={10} className="px-4 py-8 text-center text-brand-muted">No suppliers match.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {data && tab === "customers" && (
        <section className="card overflow-hidden">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-brand-border px-4 py-3">
            <p className="text-xs text-brand-muted">
              PO lines grouped by customer — click a row for all its POs, or a signal count for just those (with export).
            </p>
            <div className="relative">
              <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-brand-muted" />
              <input
                value={custQuery}
                onChange={(e) => setCustQuery(e.target.value)}
                placeholder="Filter customers…"
                className="input h-8 w-52 pl-8 text-xs"
              />
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-brand-border bg-subtle/60 text-left text-[10px] uppercase tracking-wider text-brand-muted">
                  <th className="px-4 py-2 font-semibold">Customer</th>
                  <th className="px-3 py-2 font-semibold">Signal</th>
                  <th className="px-3 py-2 text-right font-semibold">Suppliers</th>
                  <th className="px-3 py-2 text-right font-semibold">PO lines</th>
                  <th className="px-3 py-2 text-right font-semibold">Pending POs</th>
                  <th className="px-3 py-2 text-right font-semibold">Green POs</th>
                  <th className="px-3 py-2 text-right font-semibold">Red POs</th>
                  <th className="px-3 py-2 text-right font-semibold">Black POs</th>
                  <th className="w-8 px-2 py-2" aria-hidden />
                </tr>
              </thead>
              <tbody className="divide-y divide-brand-border">
                {customers.map((c) => {
                  // Signal count cells deep-link to the drill-down pre-filtered
                  // to that signal ("the red count shows the red POs").
                  const cell = (v: number, signal?: string, warn?: boolean) => (
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        openCustomer(c.customer_name, signal);
                      }}
                      className="w-full rounded px-1 text-right hover:bg-red-50/60"
                      title={signal ? `Show ${signal} POs for ${c.customer_name}` : `Show all POs for ${c.customer_name}`}
                    >
                      <Num v={v} warn={warn} />
                    </button>
                  );
                  return (
                    <tr
                      key={c.customer_name}
                      onClick={() => openCustomer(c.customer_name)}
                      className="cursor-pointer hover:bg-subtle/50"
                      title="Open all POs for this customer"
                    >
                      <td className="px-4 py-2 font-medium text-brand-dark">{c.customer_name}</td>
                      <td className="px-3 py-2">
                        {c.worst_signal ? (
                          <span className={`badge ${signalChip(c.worst_signal)}`}>{c.worst_signal}</span>
                        ) : (
                          <span className="text-brand-muted">—</span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-right"><Num v={c.suppliers} /></td>
                      <td className="px-3 py-2 text-right">{cell(c.po_lines)}</td>
                      <td className="px-3 py-2 text-right">{cell(c.pos.pending)}</td>
                      <td className="px-3 py-2 text-right">{cell(c.pos.green, "GREEN")}</td>
                      <td className="px-3 py-2 text-right">{cell(c.pos.red, "RED", true)}</td>
                      <td className="px-3 py-2 text-right">{cell(c.pos.black, "BLACK", true)}</td>
                      <td className="px-2 py-2 text-brand-muted"><ChevronRight size={14} /></td>
                    </tr>
                  );
                })}
                {customers.length === 0 && (
                  <tr>
                    <td colSpan={9} className="px-4 py-8 text-center text-brand-muted">
                      No customers yet — customer fields populate on the next CRM ingest.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}

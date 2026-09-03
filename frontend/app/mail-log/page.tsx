"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, Clock, Loader2, ScrollText } from "lucide-react";

import { api, type MailLogParams } from "@/lib/api";
import type { MailLogItem, MailLogResponse } from "@/lib/types";
import PageHeader from "@/components/layout/PageHeader";
import Pager from "@/components/ui/Pager";
import { ExportButton } from "@/components/reports/WorkloadShared";

const STATUS_TILES: { key: string; label: string; tone: string }[] = [
  { key: "SENT", label: "Sent", tone: "text-emerald-700 bg-emerald-50 ring-emerald-100" },
  { key: "READY", label: "Queued", tone: "text-amber-700 bg-amber-50 ring-amber-100" },
  { key: "FAILED", label: "Failed", tone: "text-signal-red bg-red-50 ring-red-100" },
  { key: "DRAFT", label: "Draft", tone: "text-brand-muted bg-subtle ring-brand-border" },
];

const PAGE_SIZE = 50;

function fmtDateTime(d?: string | null) {
  if (!d) return "—";
  const dt = new Date(d);
  return isNaN(dt.getTime()) ? "—" : dt.toLocaleString();
}

function prettyType(t?: string | null) {
  if (!t) return "Compose";
  return t.replace(/^PO_FOLLOWUP_/, "Follow-up · ").replace(/_/g, " ");
}

function StatusChip({ item }: { item: MailLogItem }) {
  const st = (item.status || "").toUpperCase();
  if (item.held) {
    return (
      <span
        className="inline-flex items-center gap-1 rounded-full bg-sky-50 px-2 py-0.5 text-[10px] font-semibold uppercase text-sky-700 ring-1 ring-inset ring-sky-100"
        title={`Waiting for the off-hours send window (opens ${item.held_until})`}
      >
        <Clock size={11} /> Held · {item.held_until}
      </span>
    );
  }
  const tile = STATUS_TILES.find((t) => t.key === st);
  return (
    <span className={`inline-flex rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase ring-1 ring-inset ${tile?.tone ?? "text-brand-muted bg-subtle ring-brand-border"}`}>
      {tile?.label ?? (st || "—")}
    </span>
  );
}

/** Every outgoing mail — who it went to, when, and if not sent, why. */
export default function MailLogPage() {
  const [data, setData] = useState<MailLogResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState("");
  const [mailType, setMailType] = useState("");
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [page, setPage] = useState(1);
  const [openId, setOpenId] = useState<number | null>(null);

  useEffect(() => {
    const t = setTimeout(() => setDebounced(search.trim()), 300);
    return () => clearTimeout(t);
  }, [search]);

  const params = useMemo<MailLogParams>(
    () => ({
      status: status || undefined,
      mail_type: mailType || undefined,
      search: debounced || undefined,
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
      page,
      size: PAGE_SIZE,
    }),
    [status, mailType, debounced, dateFrom, dateTo, page],
  );

  const load = useCallback(() => {
    let cancelled = false;
    setLoading(true);
    api
      .mailLog(params)
      .then((r) => {
        if (cancelled) return;
        setData(r);
        setError(null);
      })
      .catch((e) => !cancelled && setError((e as Error).message))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [params]);

  useEffect(load, [load]);

  // Queued mail changes state as the send worker runs; refresh quietly.
  useEffect(() => {
    const id = setInterval(load, 60_000);
    return () => clearInterval(id);
  }, [load]);

  const resetPage = () => setPage(1);
  const items = data?.items ?? [];

  return (
    <div className="page-stack">
      <PageHeader
        title="Mail Log"
        description="Every outgoing mail: which supplier it went to, when, and if it did not go, why."
        icon={ScrollText}
        actions={<ExportButton url={api.mailLogExportUrl(params)} filename="mail_log.xlsx" />}
      />

      {data && (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          {STATUS_TILES.map((t) => {
            const active = status === t.key;
            return (
              <button
                key={t.key}
                type="button"
                onClick={() => { setStatus(active ? "" : t.key); resetPage(); }}
                className={`card flex items-center justify-between px-4 py-3 text-left ring-1 ring-inset transition ${active ? "ring-signal-red" : "ring-transparent hover:ring-brand-border"}`}
              >
                <div>
                  <div className="text-[11px] font-semibold uppercase tracking-wider text-brand-muted">{t.label}</div>
                  <div className="text-2xl font-semibold text-brand-dark">{data.counts[t.key] ?? 0}</div>
                </div>
                <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase ring-1 ring-inset ${t.tone}`}>{t.key}</span>
              </button>
            );
          })}
        </div>
      )}

      {data && data.window.enabled && !data.window.open && (
        <div className="flex items-center gap-2 rounded-md border border-sky-100 bg-sky-50 px-3 py-2 text-xs text-sky-800">
          <Clock size={14} />
          Office hours: yellow and red auto follow-ups are held until {data.window.next_change} ({data.window.timezone}).
          Green acknowledgements, black escalations, login credentials and staff mail go out immediately.
        </div>
      )}

      <div className="card p-3">
        <div className="flex flex-wrap items-center gap-2">
          <input
            className="input h-9 w-72"
            placeholder="Search supplier / recipient / subject / PO"
            value={search}
            onChange={(e) => { setSearch(e.target.value); resetPage(); }}
          />
          <select className="input h-9" value={mailType} onChange={(e) => { setMailType(e.target.value); resetPage(); }}>
            <option value="">All mail types</option>
            {(data?.mail_types ?? []).map((t) => (
              <option key={t} value={t}>{prettyType(t)}</option>
            ))}
          </select>
          <label className="flex items-center gap-1 text-xs text-brand-muted">
            From
            <input type="date" className="input h-9" value={dateFrom} onChange={(e) => { setDateFrom(e.target.value); resetPage(); }} />
          </label>
          <label className="flex items-center gap-1 text-xs text-brand-muted">
            to
            <input type="date" className="input h-9" value={dateTo} onChange={(e) => { setDateTo(e.target.value); resetPage(); }} />
          </label>
          {loading && <Loader2 size={14} className="ml-auto animate-spin text-brand-muted" />}
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 rounded-md border border-red-100 bg-red-50 px-3 py-2 text-sm text-signal-red">
          <AlertTriangle size={14} /> {error}
        </div>
      )}

      <div className="card overflow-x-auto">
        <table className="w-full min-w-[960px] text-sm">
          <thead className="bg-subtle text-left text-[11px] uppercase tracking-wider text-brand-muted">
            <tr>
              <th className="px-3 py-2">Queued</th>
              <th className="px-3 py-2">Sent</th>
              <th className="px-3 py-2">Status</th>
              <th className="px-3 py-2">Supplier</th>
              <th className="px-3 py-2">To</th>
              <th className="px-3 py-2">Type</th>
              <th className="px-3 py-2">Subject</th>
            </tr>
          </thead>
          <tbody>
            {!loading && items.length === 0 && (
              <tr>
                <td colSpan={7} className="px-3 py-8 text-center text-sm text-brand-muted">
                  No outgoing mail matches these filters.
                </td>
              </tr>
            )}
            {items.map((m) => {
              const open = openId === m.id;
              const to = m.to_emails.length ? m.to_emails : m.receiver_email ? [m.receiver_email] : [];
              return (
                <tr
                  key={m.id}
                  className={`cursor-pointer border-t border-brand-border align-top hover:bg-subtle ${m.status === "FAILED" ? "bg-red-50/40" : ""}`}
                  onClick={() => setOpenId(open ? null : m.id)}
                >
                  <td className="whitespace-nowrap px-3 py-2 text-xs text-brand-muted">{fmtDateTime(m.created_at)}</td>
                  <td className="whitespace-nowrap px-3 py-2 text-xs text-brand-muted">{fmtDateTime(m.sent_at)}</td>
                  <td className="px-3 py-2">
                    <StatusChip item={m} />
                    {m.status === "FAILED" && m.error_message && (
                      <div className={`mt-1 text-[11px] text-signal-red ${open ? "" : "max-w-[220px] truncate"}`} title={m.error_message}>
                        {m.error_message}
                      </div>
                    )}
                  </td>
                  <td className="px-3 py-2 text-brand-dark">
                    <div className="font-medium">{m.supplier_name || "—"}</div>
                    {m.supplier_po_no && <div className="text-[11px] text-brand-muted">PO #{m.supplier_po_no}</div>}
                  </td>
                  <td className="px-3 py-2 text-xs">
                    {to.length ? (
                      <div className={open ? "" : "max-w-[240px] truncate"} title={to.join(", ")}>{to.join(", ")}</div>
                    ) : (
                      <span className="text-signal-red">no recipient</span>
                    )}
                    {open && m.cc_emails.length > 0 && (
                      <div className="mt-0.5 text-brand-muted">cc {m.cc_emails.join(", ")}</div>
                    )}
                  </td>
                  <td className="px-3 py-2 text-xs text-brand-muted">{prettyType(m.mail_type)}</td>
                  <td className="px-3 py-2 text-xs">
                    <div className={open ? "" : "max-w-[320px] truncate"} title={m.subject ?? ""}>{m.subject || "—"}</div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {data && <Pager page={data.page} size={data.size} total={data.total} onPage={setPage} unit="mails" />}
      </div>
    </div>
  );
}

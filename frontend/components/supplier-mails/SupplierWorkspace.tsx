"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Inbox, Loader2, RefreshCcw, Search } from "lucide-react";

import { api } from "@/lib/api";
import type { SupplierMail } from "@/lib/types";

function fmtDate(d?: string | null) {
  if (!d) return "—";
  const dt = new Date(d);
  return isNaN(dt.getTime()) ? "—" : dt.toLocaleString();
}

export default function SupplierWorkspace() {
  const [items, setItems] = useState<SupplierMail[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.listSupplierMails({ search: search || undefined, limit: 200 });
      setItems(res.items);
      setTotal(res.total);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [search]);

  useEffect(() => {
    void load();
  }, [load]);

  const selected = useMemo(() => items.find((m) => m.id === selectedId) ?? null, [items, selectedId]);

  return (
    <div className="page-stack">
      <div className="page-header">
        <div>
          <h1 className="page-title flex items-center gap-2">
            <Inbox size={20} className="text-signal-red" /> Supplier Inbox
          </h1>
          <p className="page-subtitle">Incoming supplier correspondence ({total}).</p>
        </div>
        <button onClick={() => void load()} className="btn-ghost text-xs" disabled={loading}>
          {loading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCcw size={14} />} Refresh
        </button>
      </div>

      <div className="relative max-w-md">
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-brand-muted" />
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search subject, sender, supplier, PO…"
          className="w-full rounded-md border border-brand-border py-2 pl-9 pr-3 text-sm"
        />
      </div>

      {error && <div className="rounded-md bg-red-50 px-3 py-2 text-xs text-signal-red">{error}</div>}

      <div className="grid gap-4 lg:grid-cols-[1fr_1.2fr]">
        {/* List */}
        <div className="card overflow-hidden">
          {loading ? (
            <div className="p-6 text-center text-brand-muted"><Loader2 size={16} className="mx-auto animate-spin" /></div>
          ) : items.length === 0 ? (
            <div className="p-6 text-center text-sm text-brand-muted">No supplier mails yet.</div>
          ) : (
            <ul className="divide-y divide-brand-border">
              {items.map((m) => (
                <li key={m.id}>
                  <button
                    onClick={() => setSelectedId(m.id)}
                    className={`w-full px-4 py-3 text-left hover:bg-gray-50 ${selectedId === m.id ? "bg-red-50" : ""}`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate text-sm font-medium text-brand-dark">{m.supplier_name || m.sender_email || "—"}</span>
                      <span className="shrink-0 text-[11px] text-brand-muted">{fmtDate(m.received_at)}</span>
                    </div>
                    <div className="truncate text-xs text-brand-muted">{m.subject || "(no subject)"}</div>
                    {m.supplier_po_no && <div className="mt-0.5 text-[10px] text-brand-muted">PO {m.supplier_po_no}</div>}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Detail */}
        <div className="card p-5">
          {selected ? (
            <div className="space-y-3">
              <div>
                <div className="text-base font-semibold text-brand-dark">{selected.subject || "(no subject)"}</div>
                <div className="mt-1 text-xs text-brand-muted">
                  From <span className="font-medium text-brand-dark">{selected.sender_email || "—"}</span>
                  {selected.supplier_name ? ` · ${selected.supplier_name}` : ""} · {fmtDate(selected.received_at)}
                </div>
                {selected.supplier_po_no && <div className="text-xs text-brand-muted">PO {selected.supplier_po_no}</div>}
              </div>
              <div className="whitespace-pre-wrap rounded-md border border-brand-border bg-gray-50 p-3 text-sm text-brand-dark">
                {selected.body || "(empty)"}
              </div>
            </div>
          ) : (
            <div className="grid h-full place-items-center text-sm text-brand-muted">Select a mail to read it.</div>
          )}
        </div>
      </div>
    </div>
  );
}

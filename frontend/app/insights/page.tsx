"use client";

import { useCallback, useEffect, useState } from "react";
import { Gauge, Loader2, RefreshCw, Database, TriangleAlert, Trophy } from "lucide-react";

import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { DelayRiskItem, SupplierScorecard, AiMemoryStats } from "@/lib/types";

const BANDS = ["", "HIGH", "MEDIUM", "LOW"] as const;

function bandClasses(band: string): string {
  switch ((band || "").toUpperCase()) {
    case "HIGH":
      return "bg-red-100 text-signal-red";
    case "MEDIUM":
      return "bg-amber-100 text-amber-700";
    case "LOW":
      return "bg-emerald-100 text-emerald-700";
    default:
      return "bg-gray-100 text-brand-muted";
  }
}

function signalDot(signal: string): string {
  switch ((signal || "").toUpperCase()) {
    case "BLACK":
      return "bg-gray-900";
    case "RED":
      return "bg-signal-red";
    case "YELLOW":
      return "bg-amber-400";
    default:
      return "bg-emerald-500";
  }
}

function gradeClasses(grade: string): string {
  switch ((grade || "").toUpperCase()) {
    case "A":
      return "bg-emerald-100 text-emerald-700";
    case "B":
      return "bg-lime-100 text-lime-700";
    case "C":
      return "bg-amber-100 text-amber-700";
    default:
      return "bg-red-100 text-signal-red";
  }
}

export default function InsightsPage() {
  const { hasRole } = useAuth();
  const isManager = hasRole("manager");

  const [tab, setTab] = useState<"risk" | "suppliers">("risk");
  const [band, setBand] = useState<string>("");
  const [risk, setRisk] = useState<DelayRiskItem[]>([]);
  const [suppliers, setSuppliers] = useState<SupplierScorecard[]>([]);
  const [memory, setMemory] = useState<AiMemoryStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    Promise.all([
      api.getDelayRisk({ band: band || undefined, limit: 100 }),
      api.getSupplierScorecards(100),
      api.aiMemoryStats().catch(() => null),
    ])
      .then(([r, s, m]) => {
        setRisk(r.items);
        setSuppliers(s.items);
        setMemory(m);
      })
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }, [band]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 2800);
    return () => clearTimeout(t);
  }, [toast]);

  const rescore = () => {
    setBusy("rescore");
    setError(null);
    api
      .rescoreDelayRisk()
      .then((r) => {
        setToast(`Re-scored ${r.updated} records (HIGH ${r.by_band.HIGH ?? 0}).`);
        load();
      })
      .catch((e) => setError((e as Error).message))
      .finally(() => setBusy(null));
  };

  const backfill = () => {
    setBusy("backfill");
    setError(null);
    api
      .aiMemoryBackfill(1000)
      .then((r) => {
        setToast(`Embedded ${r.indexed} items (${r.skipped} already indexed).`);
        api.aiMemoryStats().then(setMemory).catch(() => {});
      })
      .catch((e) => setError((e as Error).message))
      .finally(() => setBusy(null));
  };

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-red-50 text-signal-red">
            <Gauge size={16} />
          </span>
          <div>
            <h1 className="text-lg font-semibold text-brand-dark">AI Insights</h1>
            <p className="text-xs text-brand-muted">
              Predictive delivery risk, supplier performance and the assistant&apos;s semantic memory.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {toast && <span className="rounded-md bg-brand-dark px-3 py-1.5 text-xs text-white">{toast}</span>}
          {isManager && (
            <button
              onClick={rescore}
              disabled={busy === "rescore"}
              className="inline-flex items-center gap-1.5 rounded-md border border-brand-border px-3 py-1.5 text-xs font-medium text-brand-dark hover:bg-gray-50 disabled:opacity-50"
            >
              {busy === "rescore" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
              Recompute risk
            </button>
          )}
        </div>
      </div>

      {error && <div className="rounded-md bg-red-50 px-3 py-2 text-xs text-signal-red">{error}</div>}

      {/* Memory status strip */}
      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-brand-border bg-white p-3 text-xs">
        <span className="flex items-center gap-1.5 font-medium text-brand-dark">
          <Database className="h-4 w-4 text-brand-muted" /> Semantic memory
        </span>
        {memory?.store?.available ? (
          <span className="rounded bg-emerald-50 px-2 py-0.5 text-emerald-700">
            {memory.store.total} chunks indexed
            {Object.entries(memory.store.by_source).length > 0 &&
              ` · ${Object.entries(memory.store.by_source).map(([k, v]) => `${k}: ${v}`).join(", ")}`}
          </span>
        ) : (
          <span className="rounded bg-gray-100 px-2 py-0.5 text-brand-muted">
            {memory?.indexer_enabled ? "ready (empty)" : "disabled (set RAG_ENABLED on Postgres)"}
          </span>
        )}
        {isManager && memory?.indexer_enabled && (
          <button
            onClick={backfill}
            disabled={busy === "backfill"}
            className="ml-auto inline-flex items-center gap-1.5 rounded-md border border-brand-border px-2.5 py-1 text-brand-dark hover:bg-gray-50 disabled:opacity-50"
          >
            {busy === "backfill" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Database className="h-3.5 w-3.5" />}
            Backfill embeddings
          </button>
        )}
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-1 border-b border-brand-border">
        <button
          onClick={() => setTab("risk")}
          className={`flex items-center gap-1.5 px-3 py-2 text-sm ${
            tab === "risk" ? "border-b-2 border-signal-red font-medium text-signal-red" : "text-brand-muted"
          }`}
        >
          <TriangleAlert className="h-4 w-4" /> Delivery risk
        </button>
        <button
          onClick={() => setTab("suppliers")}
          className={`flex items-center gap-1.5 px-3 py-2 text-sm ${
            tab === "suppliers" ? "border-b-2 border-signal-red font-medium text-signal-red" : "text-brand-muted"
          }`}
        >
          <Trophy className="h-4 w-4" /> Supplier scorecards
        </button>
      </div>

      {loading ? (
        <div className="rounded-xl border border-brand-border bg-white p-10 text-center text-sm text-brand-muted">
          <Loader2 className="mx-auto mb-2 h-5 w-5 animate-spin" /> Loading…
        </div>
      ) : tab === "risk" ? (
        <RiskTable items={risk} band={band} setBand={setBand} />
      ) : (
        <SupplierTable items={suppliers} />
      )}
    </div>
  );
}

function RiskTable({
  items,
  band,
  setBand,
}: {
  items: DelayRiskItem[];
  band: string;
  setBand: (b: string) => void;
}) {
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 text-xs">
        <span className="text-brand-muted">Band:</span>
        {BANDS.map((b) => (
          <button
            key={b || "all"}
            onClick={() => setBand(b)}
            className={`rounded-full px-2.5 py-1 ${
              band === b ? "bg-brand-dark text-white" : "bg-gray-100 text-brand-muted hover:bg-gray-200"
            }`}
          >
            {b || "All"}
          </button>
        ))}
      </div>

      {items.length === 0 ? (
        <div className="rounded-xl border border-brand-border bg-white p-10 text-center text-sm text-brand-muted">
          No scored records yet. {`Click "Recompute risk" to generate scores.`}
        </div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-brand-border bg-white">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-brand-border bg-brand-surface text-left text-xs text-brand-muted">
                <th className="px-3 py-2 font-medium">Risk</th>
                <th className="px-3 py-2 font-medium">Supplier</th>
                <th className="px-3 py-2 font-medium">PO</th>
                <th className="px-3 py-2 font-medium">Signal</th>
                <th className="px-3 py-2 font-medium">Due</th>
                <th className="px-3 py-2 font-medium">Days late</th>
                <th className="px-3 py-2 font-medium">Materials</th>
                <th className="px-3 py-2 font-medium">Why</th>
              </tr>
            </thead>
            <tbody>
              {items.map((it) => (
                <tr key={`${it.supplier_name}-${it.supplier_po_no}`} className="border-b border-brand-border last:border-0">
                  <td className="px-3 py-2">
                    <div className="flex items-center gap-2">
                      <span className={`rounded px-1.5 py-0.5 text-xs font-semibold ${bandClasses(it.risk_band)}`}>
                        {it.risk_score}
                      </span>
                      <span className="text-xs text-brand-muted">{it.risk_band}</span>
                    </div>
                  </td>
                  <td className="px-3 py-2 text-brand-dark">{it.supplier_name || "—"}</td>
                  <td className="px-3 py-2 font-medium text-signal-red">{it.supplier_po_no}</td>
                  <td className="px-3 py-2">
                    <span className="inline-flex items-center gap-1.5 text-xs">
                      <span className={`h-2.5 w-2.5 rounded-full ${signalDot(it.signal)}`} />
                      {it.signal}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-xs text-brand-muted">{it.earliest_due_date?.slice(0, 10) || "—"}</td>
                  <td className="px-3 py-2">
                    {it.days_late === null ? (
                      <span className="text-brand-muted">—</span>
                    ) : it.days_late > 0 ? (
                      <span className="font-medium text-signal-red">+{it.days_late}d</span>
                    ) : (
                      <span className="text-brand-muted">{it.days_late}d</span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-xs text-brand-muted">
                    {it.at_risk_materials}/{it.material_count}
                  </td>
                  <td className="px-3 py-2 text-xs text-brand-muted">{it.risk_reason || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function SupplierTable({ items }: { items: SupplierScorecard[] }) {
  if (items.length === 0) {
    return (
      <div className="rounded-xl border border-brand-border bg-white p-10 text-center text-sm text-brand-muted">
        No supplier data yet.
      </div>
    );
  }
  return (
    <div className="overflow-x-auto rounded-xl border border-brand-border bg-white">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-brand-border bg-brand-surface text-left text-xs text-brand-muted">
            <th className="px-3 py-2 font-medium">Grade</th>
            <th className="px-3 py-2 font-medium">Supplier</th>
            <th className="px-3 py-2 font-medium">Score</th>
            <th className="px-3 py-2 font-medium">POs</th>
            <th className="px-3 py-2 font-medium">RED/BLACK</th>
            <th className="px-3 py-2 font-medium">Overdue</th>
            <th className="px-3 py-2 font-medium">Avg follow-ups</th>
            <th className="px-3 py-2 font-medium">Reply rate</th>
          </tr>
        </thead>
        <tbody>
          {items.map((s) => (
            <tr key={s.supplier_name} className="border-b border-brand-border last:border-0">
              <td className="px-3 py-2">
                <span className={`rounded px-2 py-0.5 text-xs font-bold ${gradeClasses(s.grade)}`}>{s.grade}</span>
              </td>
              <td className="px-3 py-2 text-brand-dark">{s.supplier_name}</td>
              <td className="px-3 py-2">
                <div className="flex items-center gap-2">
                  <div className="h-1.5 w-16 overflow-hidden rounded-full bg-gray-100">
                    <div
                      className={`h-full ${s.score >= 60 ? "bg-emerald-500" : s.score >= 40 ? "bg-amber-400" : "bg-signal-red"}`}
                      style={{ width: `${s.score}%` }}
                    />
                  </div>
                  <span className="text-xs text-brand-muted">{s.score}</span>
                </div>
              </td>
              <td className="px-3 py-2 text-xs text-brand-muted">{s.total_records}</td>
              <td className="px-3 py-2 text-xs">
                {s.red_black > 0 ? <span className="font-medium text-signal-red">{s.red_black}</span> : "0"}
              </td>
              <td className="px-3 py-2 text-xs text-brand-muted">{s.overdue}</td>
              <td className="px-3 py-2 text-xs text-brand-muted">{s.avg_followups}</td>
              <td className="px-3 py-2 text-xs text-brand-muted">
                {s.response_rate === null ? "—" : `${Math.round(s.response_rate * 100)}%`}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

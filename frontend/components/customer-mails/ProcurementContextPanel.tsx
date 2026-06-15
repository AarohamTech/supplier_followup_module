"use client";

import { memo } from "react";
import { Sparkles } from "lucide-react";
import { useRenderCount } from "./hooks";
import { RISK_TONE, formatDate } from "./shared";

export interface ProcurementContext {
  material: string | null;
  customerPo: string | null;
  supplierPo: string | null;
  balanceQty: string | null;
  stockAvailable: string | null;
  receivedQty: string | null;
  status: string | null;
  commitmentDate: string | null;
  risk: string | null;
  latestUpdate: string | null;
  materials: { name: string; stock: string; status: string }[];
}

interface ProcurementContextPanelProps {
  context: ProcurementContext | null;
  loading: boolean;
  aiSuggestion: string;
  onUseSuggestion: () => void;
}

function DataCard({ label, value, tone }: { label: string; value: string | null; tone?: string }) {
  return (
    <div className="rounded-lg border border-brand-border bg-white p-2.5">
      <div className="text-[10px] font-medium uppercase tracking-wide text-brand-muted">
        {label}
      </div>
      <div className={`mt-0.5 truncate text-sm font-semibold ${tone || "text-brand-dark"}`}>
        {value || "—"}
      </div>
    </div>
  );
}

function ProcurementContextPanelBase({
  context,
  loading,
  aiSuggestion,
  onUseSuggestion,
}: ProcurementContextPanelProps) {
  useRenderCount("ProcurementContextPanel");

  if (loading) {
    return (
      <div className="p-4 text-xs text-brand-muted">Loading procurement context…</div>
    );
  }

  const c = context;
  const riskTone = c?.risk ? RISK_TONE[c.risk] || "" : "";

  return (
    <div className="space-y-3 p-3">
      <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-signal-red">
        <Sparkles className="h-3.5 w-3.5" />
        Auto Procurement Summary
      </div>

      {/* Primary material */}
      <div className="rounded-xl border border-red-200 bg-red-50/50 p-3">
        <div className="flex items-center justify-between gap-2">
          <div className="text-[10px] font-medium uppercase tracking-wide text-brand-muted">
            Primary Material
          </div>
          {c?.risk && (
            <span className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold ${riskTone}`}>
              {c.risk} Risk
            </span>
          )}
        </div>
        <div className="mt-0.5 text-sm font-semibold text-brand-dark">
          {c?.material || "No linked material"}
        </div>
      </div>

      {/* Compact data cards */}
      <div className="grid grid-cols-2 gap-2">
        <DataCard label="Customer PO" value={c?.customerPo ?? null} />
        <DataCard label="Supplier PO" value={c?.supplierPo ?? null} />
        <DataCard label="Balance Qty" value={c?.balanceQty ?? null} />
        <DataCard label="Stock Available" value={c?.stockAvailable ?? null} tone="text-signal-red" />
        <DataCard label="Received Qty" value={c?.receivedQty ?? null} />
        <DataCard label="Status" value={c?.status ?? null} />
      </div>

      <DataCard label="Supplier Commitment Date" value={formatDate(c?.commitmentDate)} />

      <div className="rounded-lg border border-brand-border bg-white p-2.5">
        <div className="text-[10px] font-medium uppercase tracking-wide text-brand-muted">
          Latest Supplier Update
        </div>
        <p className="mt-1 text-xs italic leading-relaxed text-brand-dark">
          {c?.latestUpdate ? `“${c.latestUpdate}”` : "No supplier update yet."}
        </p>
      </div>

      {/* Linked materials */}
      {c && c.materials.length > 0 && (
        <div className="rounded-lg border border-brand-border bg-white p-2.5">
          <div className="mb-1.5 text-[10px] font-medium uppercase tracking-wide text-brand-muted">
            Linked Materials (PO Items)
          </div>
          <div className="space-y-1">
            {c.materials.map((m, i) => (
              <div key={i} className="flex items-center justify-between gap-2 text-xs">
                <span className="truncate text-brand-dark">{m.name}</span>
                <span className="shrink-0 text-brand-muted">{m.stock}</span>
                <span className="shrink-0 font-medium text-signal-red">{m.status}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* AI Suggested Reply */}
      <div className="rounded-xl border border-violet-200 bg-violet-50/60 p-3">
        <div className="flex items-center gap-1.5 text-[11px] font-semibold text-violet-700">
          <Sparkles className="h-3.5 w-3.5" />
          AI Suggested Reply
        </div>
        <p className="mt-1.5 text-xs leading-relaxed text-brand-dark">{aiSuggestion}</p>
        <button
          type="button"
          onClick={onUseSuggestion}
          className="mt-2 w-full rounded-md border border-violet-300 bg-white py-1.5 text-xs font-medium text-violet-700 hover:bg-violet-50"
        >
          Use this reply
        </button>
      </div>
    </div>
  );
}

export const ProcurementContextPanel = memo(ProcurementContextPanelBase);

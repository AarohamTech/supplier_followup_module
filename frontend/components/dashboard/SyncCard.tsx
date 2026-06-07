"use client";
import { useState } from "react";
import { Database, Loader2, RefreshCw, Upload } from "lucide-react";
import api from "@/lib/api";
import { useStore } from "@/lib/store";
import type { ProcurementSyncSummary } from "@/lib/types";

const SAMPLE_ROWS = [
  {
    "CRM no.": "2526-014222",
    "Material Name": "TAP M10 X 1.25 (HSS)",
    Uom: "NOS",
    "Lead T": 25,
    "Shipment Date": "05-06-2026 11:00",
    Signal: "YELLOW",
    Stock: 5,
    Qty: 80,
    "PO Status": "APPROVED",
    "Adv. Status": "PENDING",
    "Supplier Po No": "TM-2526-0245",
    "Supplier Date": "12-05-2026",
    "Supplier Name": "TECHNOMECH ENGINEERING PRIVATE LIMITED",
    Quantity: 80,
    Rate: 245,
  },
];

function summaryText(result: ProcurementSyncSummary | null) {
  if (!result) return "Idle - upload Excel or load sample data";
  return `${result.created_count} created, ${result.updated_count} updated, ${result.skipped_count} skipped, ${result.error_count} errors`;
}

export default function SyncCard() {
  const refresh = useStore((s) => s.refresh);
  const loadSuppliers = useStore((s) => s.loadSuppliers);
  const kpis = useStore((s) => s.kpis);
  const [busy, setBusy] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<ProcurementSyncSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = async (action: () => Promise<ProcurementSyncSummary>) => {
    setBusy(true);
    setError(null);
    try {
      const next = await action();
      setResult(next);
      await refresh();
      await loadSuppliers();
    } catch (e: any) {
      setError(e.message ?? "Sync failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <div className="h-8 w-8 rounded-md bg-emerald-50 grid place-content-center">
            <Database size={16} className="text-emerald-600" />
          </div>
          <div>
            <div className="text-sm font-medium">Data Intake</div>
            <div className="text-[11px] text-brand-muted">Excel now, ERP API later</div>
          </div>
        </div>
        <span className="chip text-emerald-600 border-emerald-100 bg-emerald-50">DB Sync</span>
      </div>

      <div className="mt-3 text-xs text-brand-muted">Records in DB</div>
      <div className="text-2xl font-semibold">{kpis?.total_records ?? "-"}</div>

      <div className="mt-2 text-xs text-brand-muted">Last result</div>
      <div className={error ? "text-sm text-signal-red" : "text-sm"}>{error ?? summaryText(result)}</div>
      {result?.errors?.[0] && (
        <div className="mt-1 text-[11px] text-signal-red truncate" title={result.errors[0].error}>
          Row {result.errors[0].row_index}: {result.errors[0].error}
        </div>
      )}

      <div className="mt-3 space-y-2">
        <label className="block">
          <span className="sr-only">Choose Excel file</span>
          <input
            type="file"
            accept=".xlsx"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="block w-full text-xs text-brand-muted file:mr-2 file:rounded-md file:border-0 file:bg-gray-100 file:px-3 file:py-1.5 file:text-xs file:font-medium file:text-brand-dark hover:file:bg-gray-200"
          />
        </label>
        <button
          onClick={() => file && run(() => api.uploadProcurementExcel(file))}
          disabled={busy || !file}
          className="w-full bg-emerald-50 text-emerald-700 text-sm font-medium py-2 rounded-md flex items-center justify-center gap-2 hover:bg-emerald-100 disabled:opacity-50"
        >
          {busy ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
          Upload Excel
        </button>
        <div className="grid grid-cols-2 gap-2">
          <button
            onClick={() => run(() => api.loadSampleProcurement())}
            disabled={busy}
            className="bg-gray-50 text-brand-dark text-sm font-medium py-2 rounded-md flex items-center justify-center gap-2 hover:bg-gray-100 disabled:opacity-50"
          >
            {busy ? <Loader2 size={14} className="animate-spin" /> : <Database size={14} />}
            Load Sample
          </button>
          <button
            onClick={() => run(() => api.syncProcurement(SAMPLE_ROWS))}
            disabled={busy}
            className="bg-gray-50 text-brand-dark text-sm font-medium py-2 rounded-md flex items-center justify-center gap-2 hover:bg-gray-100 disabled:opacity-50"
          >
            {busy ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
            JSON Sync
          </button>
        </div>
      </div>
    </div>
  );
}

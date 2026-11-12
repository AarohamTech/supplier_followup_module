"use client";

// Supplier portal "Acknowledge PO" button. Uses the same backend service as the
// signed mail link; once acknowledged it shows when.

import { useEffect, useState } from "react";
import { CheckCircle2, Loader2, ThumbsUp } from "lucide-react";

import { api } from "@/lib/api";
import type { PoAckStatus } from "@/lib/types";

function label(s: PoAckStatus): string {
  if (s.acknowledged_at_label) return s.acknowledged_at_label;
  return s.acknowledged_at ? new Date(s.acknowledged_at).toLocaleString() : "";
}

export default function PoAckButton({ supplierPoNo }: { supplierPoNo: string }) {
  const [status, setStatus] = useState<PoAckStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .portalPoAckStatus(supplierPoNo)
      .then((s) => !cancelled && setStatus(s))
      // Status unknown → still offer the button (the POST is idempotent).
      .catch(() => !cancelled && setStatus({ acknowledged: false, acknowledged_at: null, via: null }));
    return () => {
      cancelled = true;
    };
  }, [supplierPoNo]);

  const acknowledge = async () => {
    setBusy(true);
    setError(null);
    try {
      setStatus(await api.portalPoAck(supplierPoNo));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  if (status?.acknowledged) {
    return (
      <span
        className="inline-flex items-center gap-1.5 rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs font-semibold text-emerald-700"
        title={status.via === "link" ? "Acknowledged from the email link" : "Acknowledged in the portal"}
      >
        <CheckCircle2 size={13} /> Acknowledged on {label(status)}
      </span>
    );
  }

  return (
    <span className="inline-flex flex-col items-start gap-1">
      <button
        onClick={() => void acknowledge()}
        disabled={busy || status === null}
        className="btn-outline border-emerald-300 text-emerald-700 hover:bg-emerald-50"
        title="Confirm that you have received this purchase order"
      >
        {busy ? <Loader2 size={15} className="animate-spin" /> : <ThumbsUp size={15} />} Acknowledge PO
      </button>
      {error && <span className="text-[11px] text-signal-red">{error}</span>}
    </span>
  );
}

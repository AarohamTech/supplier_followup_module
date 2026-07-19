"use client";

import { useState } from "react";
import { FileDown, Loader2 } from "lucide-react";

import { getToken } from "@/lib/auth-token";

/**
 * Download button for the official CRM PO PDF. Renders nothing when the line
 * has no PO transaction number. `endpoint` picks the proxy for the caller's
 * user type: staff use /api/procurement/po-pdf, employees /api/eportal/po-pdf.
 */
export default function PoPdfButton({
  trnNo,
  fileLabel,
  endpoint = "/api/procurement/po-pdf",
  className,
}: {
  trnNo?: string | null;
  fileLabel: string;
  endpoint?: string;
  className?: string;
}) {
  const [busy, setBusy] = useState(false);
  if (!trnNo) return null;
  const trn = trnNo;

  async function download(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    setBusy(true);
    try {
      const token = getToken();
      const res = await fetch(`${endpoint}?trn_no=${encodeURIComponent(trn)}&amend_no=0`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error("PDF download failed");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `PO-${fileLabel}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      window.alert("PO PDF download failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <button
      type="button"
      title="Download PO PDF"
      disabled={busy}
      onClick={download}
      className={className ?? "rounded p-0.5 text-brand-muted hover:bg-subtle hover:text-brand-dark disabled:opacity-50"}
    >
      {busy ? <Loader2 size={13} className="animate-spin" /> : <FileDown size={13} />}
    </button>
  );
}

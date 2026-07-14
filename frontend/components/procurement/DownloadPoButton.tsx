"use client";

import { useState } from "react";
import { Download, Loader2 } from "lucide-react";

import { useStore } from "@/lib/store";
import { getToken } from "@/lib/auth-token";

/** Download the currently-filtered PO lines as an Excel workbook. */
export default function DownloadPoButton() {
  const filters = useStore((s) => s.filters);
  const [busy, setBusy] = useState(false);

  async function download() {
    setBusy(true);
    try {
      const q = new URLSearchParams();
      Object.entries(filters || {}).forEach(([k, v]) => {
        if (k === "page" || k === "size") return;
        if (v !== undefined && v !== null && v !== "") q.set(k, String(v));
      });
      const token = getToken();
      const res = await fetch(`/api/procurement/export.xlsx${q.toString() ? `?${q}` : ""}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error("Download failed");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "po-lines.xlsx";
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      /* surfaced by button state only */
    } finally {
      setBusy(false);
    }
  }

  return (
    <button type="button" onClick={download} disabled={busy} className="btn-outline text-xs inline-flex items-center gap-1">
      {busy ? <Loader2 size={13} className="animate-spin" /> : <Download size={13} />}
      Download PO
    </button>
  );
}

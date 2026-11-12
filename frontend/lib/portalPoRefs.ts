"use client";

/**
 * Supplier-facing PO numbers.
 *
 * The portal routes and APIs key POs on `supplier_po_no` — the CRM PoNo, a
 * recycled customer-order counter (e.g. 002180) that means nothing to the
 * supplier. The number on the supplier's PO document is the vendor ref
 * (`po_ref` = CRM PoShortRefTrnNo, e.g. 2627-019035). Everything a supplier
 * reads shows the vendor ref and falls back to the counter only when the
 * feed gave no ref; the counter stays the routing key.
 */
import { useEffect, useState } from "react";

import { api } from "@/lib/api";

/** The number to show a supplier for a PO row that carries both values. */
export function supplierPoNo(p: { po_ref?: string | null; supplier_po_no?: string | null }): string {
  return (p.po_ref || p.supplier_po_no || "").trim();
}

/**
 * For screens that only hold the counter (ASNs, tasks): loads the supplier's
 * PO list once and returns a counter → display-number function.
 */
export function usePortalPoLabel(): (counter?: string | null) => string {
  const [refs, setRefs] = useState<Record<string, string>>({});
  useEffect(() => {
    let cancelled = false;
    api
      .portalPos()
      .then((res) => {
        if (cancelled) return;
        const map: Record<string, string> = {};
        for (const p of res.items) if (p.po_ref) map[p.supplier_po_no] = p.po_ref;
        setRefs(map);
      })
      .catch(() => {
        /* fall back to counters */
      });
    return () => {
      cancelled = true;
    };
  }, []);
  return (counter) => (counter ? refs[counter] || counter : "");
}

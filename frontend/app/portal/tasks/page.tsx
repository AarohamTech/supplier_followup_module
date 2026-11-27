"use client";

import { api } from "@/lib/api";
import PortalTaskWorkspace, { type PortalTaskAdapter } from "@/components/portal/PortalTaskWorkspace";

// Supplier portal is strictly read-only: list + dashboard only. The backend
// already nulls internal fields (assignee, watchers, ai_summary) server-side.
const supplierAdapter: PortalTaskAdapter = {
  // Tasks carry the internal PO counter; suppliers know the vendor PO number
  // (po_ref), so swap it in for display. Read-only view: the value is never
  // sent back to the API.
  listTasks: async () => {
    const [tasks, pos] = await Promise.all([api.portalTasks(), api.portalPos().catch(() => null)]);
    const refs = new Map<string, string>();
    for (const p of pos?.items ?? []) {
      if (!p.po_ref) continue;
      for (const c of p.supplier_po_nos?.length ? p.supplier_po_nos : [p.supplier_po_no]) refs.set(c, p.po_ref);
    }
    return tasks.map((t) =>
      t.supplier_po_no && refs.has(t.supplier_po_no) ? { ...t, supplier_po_no: refs.get(t.supplier_po_no)! } : t,
    );
  },
  dashboard: () => api.portalTasksDashboard(),
  boardColumns: () => api.portalTaskBoardColumns(),
};

export default function SupplierTasksPage() {
  return (
    <PortalTaskWorkspace
      adapter={supplierAdapter}
      permissions={{ canCreate: false, canEdit: false, canAssign: false, canDelete: false, canComment: false, readOnly: true }}
      scopeLabel="Tasks"
    />
  );
}

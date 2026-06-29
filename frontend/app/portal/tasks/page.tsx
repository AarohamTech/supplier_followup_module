"use client";

import { api } from "@/lib/api";
import PortalTaskWorkspace, { type PortalTaskAdapter } from "@/components/portal/PortalTaskWorkspace";

// Supplier portal is strictly read-only: list + dashboard only. The backend
// already nulls internal fields (assignee, watchers, ai_summary) server-side.
const supplierAdapter: PortalTaskAdapter = {
  listTasks: () => api.portalTasks(),
  dashboard: () => api.portalTasksDashboard(),
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

"use client";

import { api } from "@/lib/api";
import PortalCommHub, { type CommHubAdapter, type CommHubPoRow } from "@/components/portal/PortalCommHub";

const employeeAdapter: CommHubAdapter = {
  listPos: async (): Promise<CommHubPoRow[]> => {
    const res = await api.eportalPos();
    return res.items.map((p) => ({
      supplier_po_no: p.supplier_po_no,
      counterparty: p.supplier_name || "—",
      crm_no: p.crm_no,
      signal: p.overall_signal,
      material_count: p.material_count,
      unread_inbound: p.unread_inbound,
      escalated: p.escalated,
    }));
  },
  listMessages: (po) => api.eportalPoMessages(po),
  sendMessage: (po, body) => api.eportalSendMessage(po, body),
  markRead: (po) => api.eportalMarkPoRead(po),
  listMaterials: async (po) => {
    const mats = await api.eportalPoMaterials(po);
    return mats.map((m) => ({
      material_name: m.material_name,
      signal: m.signal,
      commitment_date: m.commitment_date,
    }));
  },
};

export default function EmployeeCommunicationPage() {
  return <PortalCommHub adapter={employeeAdapter} mode="employee" />;
}

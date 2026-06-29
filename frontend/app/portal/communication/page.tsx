"use client";

import { api } from "@/lib/api";
import PortalCommHub, { type CommHubAdapter, type CommHubPoRow } from "@/components/portal/PortalCommHub";

const supplierAdapter: CommHubAdapter = {
  listPos: async (): Promise<CommHubPoRow[]> => {
    const res = await api.portalPos();
    return res.items.map((p) => ({
      supplier_po_no: p.supplier_po_no,
      counterparty: "Your buyer",
      crm_no: p.crm_no,
      signal: p.overall_signal,
      material_count: p.material_count,
      unread_inbound: p.unread_inbound,
      escalated: p.escalated,
    }));
  },
  listMessages: (po) => api.portalPoMessages(po),
  sendMessage: (po, body) => api.sendPortalPoMessage(po, body),
  markRead: (po) => api.portalMarkPoRead(po),
  listMaterials: async (po) => {
    const mats = await api.portalPoMaterials(po);
    return mats.map((m) => ({
      material_name: m.material_name,
      signal: m.signal,
      commitment_date: m.commitment_date,
    }));
  },
  listTasks: (po) => api.portalPoTasks(po),
};

export default function CommunicationHubPage() {
  return <PortalCommHub adapter={supplierAdapter} mode="supplier" />;
}

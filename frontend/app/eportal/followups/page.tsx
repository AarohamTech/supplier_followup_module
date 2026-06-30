"use client";

import { api } from "@/lib/api";
import { BlackFollowupsPanel, type BlackFollowupsAdapter } from "@/components/black-followups/BlackFollowupsPanel";

/**
 * Employee "Black Follow-ups" — the EXACT admin Black Follow-ups panel
 * (Active/History, detail drawer with the AI conversation thread + draft→send
 * composer), but every call hits the employee-scoped /api/eportal/ai/insights/*
 * endpoints (restricted to the employee's owned POs). Employees may send on a PO
 * they own, so canSend is true.
 */
const employeeAdapter: BlackFollowupsAdapter = {
  list: (limit = 100) => api.eportalGetBlackFollowups(limit),
  history: (params) => api.eportalGetFollowupHistory(params),
  command: (po, instruction, send = false) => api.eportalBlackFollowupCommand(po, instruction, send),
  canSend: true,
};

export default function EmployeeFollowupsPage() {
  return <BlackFollowupsPanel adapter={employeeAdapter} />;
}

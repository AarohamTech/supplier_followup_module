"use client";

import api from "@/lib/api";
import CommunicationHub, { type CommHubAdapter } from "@/components/communication/CommunicationHub";

// Employee Communication Hub — the EXACT same experience as the admin hub, but
// every call hits the employee-scoped /api/eportal/hub/* endpoints (scoped to the
// employee's owned POs). Employees have no customer inbox, so showCustomers=false
// hides the Suppliers/Customers toggle + CustomerWorkspace entirely.
const employeeHub: CommHubAdapter = {
  dashboard: () => api.eportalHubDashboard(),
  suppliers: () => api.eportalHubSuppliers(),
  posByName: (supplierName) => api.eportalHubPos({ supplier_name: supplierName }),
  posById: (supplierId) => api.eportalHubPos({ supplier_id: supplierId }),
  thread: (params) => api.eportalHubThread(params),
  markThreadRead: (params) => api.eportalHubMarkThreadRead(params),
  tasks: (params) => api.eportalHubTasks(params),
  createTask: (body) => api.eportalHubCreateTask(body),
  updateTask: (id, body) => api.eportalHubUpdateTask(id, body),
  aiReply: (id) => api.eportalHubAiReply(id),
  reply: (body) => api.eportalHubReply(body),
  escalate: (id) => api.eportalHubEscalate(id),
  agent: (body) => api.eportalHubAgent(body),
  agentConfirm: (body) => api.eportalHubAgentConfirm(body),
  sendMail: (id) => api.eportalHubSendMail(id),
  assignees: () => api.eportalHubAssignees(),
  mentionTargets: () => api.eportalHubMentionTargets(),
  commitments: (params) => api.eportalHubCommitments(params),
  approveMessage: (id) => api.eportalHubApproveMessage(id),
  discardMessage: (id) => api.eportalHubDiscardMessage(id),
};

export default function EmployeeCommunicationPage() {
  return <CommunicationHub hub={employeeHub} showCustomers={false} />;
}

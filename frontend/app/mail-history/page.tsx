"use client";

import api from "@/lib/api";
import CommunicationHub, { type CommHubAdapter } from "@/components/communication/CommunicationHub";

// Admin Communication Hub — talks to the staff /api/communication-hub/* endpoints
// and exposes the Suppliers/Customers toggle. The shared <CommunicationHub />
// renders the entire experience; this page only wires the data source.
const adminHub: CommHubAdapter = {
  dashboard: () => api.hubDashboard(),
  suppliers: () => api.hubSuppliers(),
  posByName: (supplierName) => api.hubPosByName(supplierName),
  posById: (supplierId) => api.hubPosById(supplierId),
  thread: (params) => api.hubThread(params),
  markThreadRead: (params) => api.hubMarkThreadRead(params),
  tasks: (params) => api.hubTasks(params),
  createTask: (body) => api.hubCreateTask(body),
  updateTask: (id, body) => api.hubUpdateTask(id, body),
  aiReply: (id) => api.hubAiReply(id),
  reply: (body) => api.hubReply(body),
  escalate: (id) => api.hubEscalate(id),
  agent: (body) => api.hubAgent(body),
  agentConfirm: (body) => api.hubAgentConfirm(body),
  sendMail: (id) => api.hubSendMail(id),
  assignees: () => api.listAssignees(),
  mentionTargets: () => api.listMentionTargets(),
  commitments: (params) => api.listCommitments(params),
  approveMessage: (id) => api.approveMessage(id),
  discardMessage: (id) => api.discardMessage(id),
};

export default function Page() {
  return <CommunicationHub hub={adminHub} showCustomers={true} />;
}

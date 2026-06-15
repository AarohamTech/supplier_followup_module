// Centralized API client and typed helpers.
// Calls go through Next.js rewrites (/api/* → backend /api/*).
import type {
  ProcurementRecord,
  ProcurementListResponse,
  DashboardKpis,
  SupplierMaster,
  SupplierEmail,
  MailDraft,
  MailDraftPo,
  MailHistory,
  MailHistoryFilters,
  OutlookComposeRequest,
  OutlookComposeResult,
  ProcurementFilters,
  ProcurementSyncSummary,
  CommunicationTask,
  CommunicationTaskCreate,
  CommunicationTaskUpdate,
  CommunicationTaskFilters,
  TaskComment,
  TaskActivity,
  CommunicationDashboard,
  CommHubDashboard,
  CommHubSupplier,
  CommHubPO,
  CommHubThread,
  CommHubTasksGrouped,
  CommHubTaskFilters,
  PoFollowupGroup,
  PoFollowupListResponse,
  SupplierMaterialCommitment,
  MailEngineSnapshot,
  MailEngineHealth,
  DraftRule,
  CronJobRow,
  CronJobLog,
  CronJobRunResult,
  CustomerMail,
  CustomerMailListResponse,
  CustomerMailAssignPayload,
  CustomerMailTaskPayload,
  CustomerMailMetaOptions,
} from "./types";

const API = ""; // same-origin, rewritten by next.config.mjs

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const isFormData = init?.body instanceof FormData;
  const res = await fetch(`${API}${path}`, {
    ...init,
    headers: isFormData ? init?.headers : { "Content-Type": "application/json", ...(init?.headers || {}) },
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = "";
    try { detail = (await res.json()).detail || ""; } catch { /* ignore */ }
    throw new Error(`${res.status} ${res.statusText} ${detail}`);
  }
  if (res.status === 204) return undefined as unknown as T;
  return (await res.json()) as T;
}

export const api = {
  dashboard: () => http<DashboardKpis>("/api/procurement/dashboard"),

  listProcurement: (filters: ProcurementFilters = {}) => {
    const q = new URLSearchParams();
    Object.entries(filters).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "") q.append(k, String(v));
    });
    const qs = q.toString();
    return http<ProcurementListResponse>(`/api/procurement${qs ? `?${qs}` : ""}`);
  },

  getProcurement: (id: number) => http<ProcurementRecord>(`/api/procurement/${id}`),

  updateProcurement: (id: number, body: Partial<ProcurementRecord>) =>
    http<ProcurementRecord>(`/api/procurement/${id}`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),

  syncProcurement: (rows: any[]) =>
    http<ProcurementSyncSummary>(
      "/api/procurement/sync",
      { method: "POST", body: JSON.stringify(rows) },
    ),

  uploadProcurementExcel: (file: File) => {
    const body = new FormData();
    body.append("file", file);
    return http<ProcurementSyncSummary>("/api/procurement/upload-excel", {
      method: "POST",
      body,
    });
  },

  loadSampleProcurement: () =>
    http<ProcurementSyncSummary>("/api/procurement/load-sample-data", { method: "POST" }),

  listSuppliers: () => http<SupplierMaster[]>("/api/suppliers"),
  getSupplier: (id: number) => http<SupplierMaster>(`/api/suppliers/${id}`),
  updateSupplier: (id: number, body: Partial<SupplierMaster>) =>
    http<SupplierMaster>(`/api/suppliers/${id}`, { method: "PUT", body: JSON.stringify(body) }),

  listSupplierEmails: () => http<SupplierEmail[]>("/api/supplier-emails"),
  createSupplierEmail: (body: Partial<SupplierEmail>) =>
    http<SupplierEmail>("/api/supplier-emails", { method: "POST", body: JSON.stringify(body) }),
  updateSupplierEmail: (id: number, body: Partial<SupplierEmail>) =>
    http<SupplierEmail>(`/api/supplier-emails/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  deleteSupplierEmail: (id: number) =>
    http<void>(`/api/supplier-emails/${id}`, { method: "DELETE" }),

  generateMailDraft: (procurement_record_id: number) =>
    http<MailDraft>("/api/mail-drafts/generate", {
      method: "POST",
      body: JSON.stringify({ procurement_record_id }),
    }),

  generatePoMailDraft: (
    body: { supplier_name: string; supplier_po_no: string; mail_type?: string; force_new?: boolean },
  ) =>
    http<MailDraftPo>("/api/mail-drafts/generate-po", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  listPoGroups: (params: {
    signal?: string;
    supplier_name?: string;
    supplier_po_no?: string;
    search?: string;
    page?: number;
    size?: number;
  } = {}) => {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "") q.append(k, String(v));
    });
    const qs = q.toString();
    return http<PoFollowupListResponse>(`/api/po-followups/groups${qs ? `?${qs}` : ""}`);
  },

  getPoGroup: (supplier_name: string, supplier_po_no: string) => {
    const q = new URLSearchParams({ supplier_name, supplier_po_no });
    return http<PoFollowupGroup>(`/api/po-followups/groups/by-key?${q.toString()}`);
  },

  listCommitments: (params: { supplier_po_no?: string; supplier_name?: string } = {}) => {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "") q.append(k, String(v));
    });
    const qs = q.toString();
    return http<SupplierMaterialCommitment[]>(`/api/po-followups/commitments${qs ? `?${qs}` : ""}`);
  },

  listMailHistory: (filters: MailHistoryFilters = {}) => {
    const q = new URLSearchParams();
    Object.entries(filters).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "") q.append(k, String(v));
    });
    const qs = q.toString();
    return http<MailHistory[]>(`/api/mail-history${qs ? `?${qs}` : ""}`);
  },

  getMailHistory: (id: number) => http<MailHistory>(`/api/mail-history/${id}`),
  listMailHistoryByRecord: (id: number) => http<MailHistory[]>(`/api/mail-history/by-record/${id}`),
  listMailHistoryBySubject: (subject: string) =>
    http<MailHistory[]>(`/api/mail-history/by-subject?subject=${encodeURIComponent(subject)}`),
  updateMailHistoryStatus: (id: number, sent_status: string, remarks?: string) =>
    http<MailHistory>(`/api/mail-history/${id}/status`, {
      method: "PUT",
      body: JSON.stringify({ sent_status, remarks }),
    }),

  openOutlookDraft: (body: OutlookComposeRequest) =>
    http<OutlookComposeResult>("/api/mail-drafts/open-outlook", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  // ─── Communication Tasks ───────────────────────────────────────────────
  commDashboard: () => http<CommunicationDashboard>("/api/communication/dashboard"),

  listTasks: (filters: CommunicationTaskFilters = {}) => {
    const q = new URLSearchParams();
    Object.entries(filters).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "") q.append(k, String(v));
    });
    const qs = q.toString();
    return http<CommunicationTask[]>(`/api/communication/tasks${qs ? `?${qs}` : ""}`);
  },

  createTask: (body: CommunicationTaskCreate) =>
    http<CommunicationTask>("/api/communication/tasks", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  updateTask: (id: number, body: CommunicationTaskUpdate) =>
    http<CommunicationTask>(`/api/communication/tasks/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  deleteTask: (id: number) =>
    http<void>(`/api/communication/tasks/${id}`, { method: "DELETE" }),

  // ─── Communication Hub (real-data aggregation layer) ──────────────────────
  hubDashboard: () =>
    http<CommHubDashboard>("/api/communication-hub/dashboard"),

  hubSuppliers: () =>
    http<CommHubSupplier[]>("/api/communication-hub/suppliers"),

  hubPosById: (supplierId: number) =>
    http<CommHubPO[]>(`/api/communication-hub/suppliers/${supplierId}/purchase-orders`),

  hubPosByName: (supplierName: string) =>
    http<CommHubPO[]>(
      `/api/communication-hub/purchase-orders?supplier_name=${encodeURIComponent(supplierName)}`,
    ),

  hubThread: (params: { supplier_id?: number | null; procurement_record_id?: number | null; supplier_po_no?: string | null }) => {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null) q.append(k, String(v));
    });
    return http<CommHubThread>(`/api/communication-hub/thread?${q.toString()}`);
  },

  hubMarkThreadRead: (params: { supplier_po_no?: string | null; procurement_record_id?: number | null }) => {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "") q.append(k, String(v));
    });
    return http<{ marked: number; at: string }>(
      `/api/communication-hub/thread/mark-read?${q.toString()}`,
      { method: "POST" },
    );
  },

  hubTasks: (params: CommHubTaskFilters = {}) => {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null) q.append(k, String(v));
    });
    const qs = q.toString();
    return http<CommHubTasksGrouped>(`/api/communication-hub/tasks${qs ? `?${qs}` : ""}`);
  },

  hubCreateTask: (body: CommunicationTaskCreate) =>
    http<CommunicationTask>("/api/communication-hub/tasks", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  hubUpdateTask: (id: number, body: CommunicationTaskUpdate) =>
    http<CommunicationTask>(`/api/communication-hub/tasks/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  hubAiReply: (procurementRecordId: number) =>
    http<{ subject: string; body: string; mail_type: string }>(
      `/api/communication-hub/ai-reply?procurement_record_id=${procurementRecordId}`,
      { method: "POST" },
    ),

  hubEscalate: (procurementRecordId: number) =>
    http<{ message: string; mail_draft_id: number; task_id: number; subject: string }>(
      `/api/communication-hub/escalate?procurement_record_id=${procurementRecordId}`,
      { method: "POST" },
    ),

  getSchedulerSettings: () =>
    http<{
      scheduler_intervals_minutes: Record<string, number>;
      followup_intervals_hours: Record<string, number>;
    }>(`/api/settings/scheduler`),

  updateSchedulerIntervals: (values: Record<string, number>) =>
    http<{ scheduler_intervals_minutes: Record<string, number> }>(
      `/api/settings/scheduler`,
      { method: "PUT", body: JSON.stringify(values) },
    ),

  updateFollowupIntervals: (intervals: Record<string, number>) =>
    http<{ followup_intervals_hours: Record<string, number> }>(
      `/api/settings/followup`,
      { method: "PUT", body: JSON.stringify({ intervals }) },
    ),

  listDraftRules: () =>
    http<{ rules: DraftRule[]; followup_intervals_hours: Record<string, number> }>(
      `/api/settings/draft-rules`,
    ),

  updateDraftRule: (
    id: number,
    body: {
      subject_template?: string;
      body_template?: string;
      active?: boolean;
      interval_hours?: number;
    },
  ) =>
    http<{ rule: DraftRule }>(
      `/api/settings/draft-rules/${id}`,
      { method: "PUT", body: JSON.stringify(body) },
    ),

  // ─── Mail Engine (SMTP/IMAP/Cron/Health) ───────────────────────────────
  getMailEngineSnapshot: () =>
    http<MailEngineSnapshot>(`/api/settings/mail-engine`),

  testSmtp: () =>
    http<MailEngineHealth["smtp"]>(`/api/settings/test-smtp`, { method: "POST" }),

  testImap: () =>
    http<MailEngineHealth["imap"]>(`/api/settings/test-imap`, { method: "POST" }),

  listCronJobs: () =>
    http<{ jobs: CronJobRow[] }>(`/api/settings/cron-jobs`),

  updateCronJob: (job_name: string, body: { enabled?: boolean; interval_minutes?: number }) =>
    http<{ job_name: string; enabled: boolean; interval_minutes: number }>(
      `/api/settings/cron-jobs/${encodeURIComponent(job_name)}`,
      { method: "PUT", body: JSON.stringify(body) },
    ),

  runCronJobNow: (job_name: string) =>
    http<CronJobRunResult>(
      `/api/settings/cron-jobs/${encodeURIComponent(job_name)}/run`,
      { method: "POST" },
    ),

  runAllCronJobs: () =>
    http<{ ran: number; results: CronJobRunResult[] }>(
      `/api/settings/cron-jobs/run-all`,
      { method: "POST" },
    ),

  getCronJobLogs: (params: { job_name?: string; limit?: number } = {}) => {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "") q.append(k, String(v));
    });
    const qs = q.toString();
    return http<{ logs: CronJobLog[] }>(`/api/settings/cron-jobs/logs${qs ? `?${qs}` : ""}`);
  },

  startEngine: () =>
    http<{ ok: boolean; running: boolean; jobs: string[] }>(
      `/api/settings/engine/start`,
      { method: "POST" },
    ),
  stopEngine: () =>
    http<{ ok: boolean; running: boolean; stopped_at: string }>(
      `/api/settings/engine/stop`,
      { method: "POST" },
    ),
  restartEngine: () =>
    http<{ ok: boolean; jobs?: string[]; started_at?: string; reason?: string }>(
      `/api/settings/engine/restart`,
      { method: "POST" },
    ),
  getEngineHealth: () =>
    http<MailEngineHealth>(`/api/settings/engine/health`),

  // ─── Customer Mail Inbox ───────────────────────────────────────────────
  listCustomerMails: (params: {
    status?: string;
    mail_type?: string;
    assigned_to?: string;
    search?: string;
    limit?: number;
    offset?: number;
  } = {}) => {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "") q.append(k, String(v));
    });
    const qs = q.toString();
    return http<CustomerMailListResponse>(`/api/customer-mails${qs ? `?${qs}` : ""}`);
  },
  getCustomerMail: (id: number) =>
    http<CustomerMail>(`/api/customer-mails/${id}`),
  assignCustomerMail: (id: number, body: CustomerMailAssignPayload) =>
    http<CustomerMail>(`/api/customer-mails/${id}/assign`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  resolveCustomerMail: (id: number, resolution_note?: string) =>
    http<CustomerMail>(`/api/customer-mails/${id}/resolve`, {
      method: "POST",
      body: JSON.stringify({ resolution_note }),
    }),
  createTaskForCustomerMail: (id: number, body: CustomerMailTaskPayload) =>
    http<{ ok: boolean; task_id: number; customer_mail_id: number; linked_task_id: number }>(
      `/api/customer-mails/${id}/create-task`,
      { method: "POST", body: JSON.stringify(body) },
    ),
  getCustomerMailMeta: () =>
    http<CustomerMailMetaOptions>(`/api/customer-mails/meta/options`),

  // ─── Unified Tasks ────────────────────────────────────────────────────
  getTasksDashboard: () =>
    http<CommunicationDashboard & {
      due_today?: number;
      supplier_tasks?: number;
      customer_tasks?: number;
      internal_tasks?: number;
      escalation_tasks?: number;
    }>(`/api/tasks/dashboard`),

  listUnifiedTasks: (params: {
    task_source?: string;
    status?: string;
    assigned_to?: string;
    supplier_name?: string;
    supplier_po_no?: string;
    customer_mail_id?: number;
    overdue?: boolean;
    limit?: number;
  } = {}) => {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "" && v !== false) q.append(k, String(v));
    });
    const qs = q.toString();
    return http<CommunicationTask[]>(`/api/tasks${qs ? `?${qs}` : ""}`);
  },

  hubSendMail: (mail_history_id: number) =>
    http<{ mail_history_id: number; send_result: any }>(
      `/api/communication-hub/send-mail?mail_history_id=${mail_history_id}`,
      { method: "POST" },
    ),

  // ─── Task collaboration ──────────────────────────────────────────────
  listTaskComments: (taskId: number) =>
    http<TaskComment[]>(`/api/tasks/${taskId}/comments`),

  addTaskComment: (taskId: number, comment: string, created_by?: string) =>
    http<TaskComment>(`/api/tasks/${taskId}/comments`, {
      method: "POST",
      body: JSON.stringify({ comment, created_by }),
    }),

  listTaskActivity: (taskId: number) =>
    http<TaskActivity[]>(`/api/tasks/${taskId}/activity`),
};

export default api;

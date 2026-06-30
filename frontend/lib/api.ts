// Centralized API client and typed helpers.
// Calls go through Next.js rewrites (/api/* → backend /api/*).
import type {
  SentFeedItem,
  ProcurementRecord,
  ProcurementListResponse,
  DashboardKpis,
  SupplierMaster,
  SupplierEmail,
  SupplierEmailAudit,
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
  TaskAssignee,
  TaskAnalytics,
  CommunicationDashboard,
  PortalTaskDashboard,
  CommHubDashboard,
  CommHubSupplier,
  CommHubPO,
  CommHubThread,
  CommHubTasksGrouped,
  CommHubTaskFilters,
  OtherMailThread,
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
  CustomerReply,
  CustomerDraftReply,
  OutboxDraft,
  ChatMessage,
  AiChatResponse,
  AiHealth,
  DelayRiskResponse,
  SupplierScorecard,
  AiMemoryStats,
  BlackFollowupResponse,
  FollowupHistoryResponse,
  BlackFollowupCommandResult,
  AiPromptsMap,
  AiFeedbackInput,
  AuthUser,
  LoginResponse,
  UserCreatePayload,
  UserUpdatePayload,
  SupplierLogin,
  Asn,
  AsnListResponse,
  AsnSummary,
  AsnCreatePayload,
  AsnEventPayload,
  PortalSummary,
  PortalPoListResponse,
  PortalPoMaterial,
  PortalCommitmentItem,
  PortalTask,
  PortalMessage,
  PortalMe,
  EmployeeSummary,
  EmployeePoListResponse,
  EmployeePoMaterial,
  EmployeeProvisionResult,
  EmployeeCreatePayload,
  CrmIngestLog,
  AppNotification,
  AdminDigestConfig,
} from "./types";
import { getToken, setToken, LOGIN_PATH } from "./auth-token";

const API = ""; // same-origin, rewritten by next.config.mjs

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const isFormData = init?.body instanceof FormData;
  const token = getToken();
  const headers: Record<string, string> = {
    ...(isFormData ? {} : { "Content-Type": "application/json" }),
    ...((init?.headers as Record<string, string>) || {}),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${API}${path}`, { ...init, headers, cache: "no-store" });

  if (res.status === 401) {
    // Session expired or missing → drop token and bounce to login.
    setToken(null);
    if (typeof window !== "undefined" && window.location.pathname !== LOGIN_PATH) {
      window.location.href = LOGIN_PATH;
      // Suppress the error toast while the redirect navigation is in flight.
      return new Promise<T>(() => {});
    }
  }
  if (!res.ok) {
    let detail = "";
    try { detail = (await res.json()).detail || ""; } catch { /* ignore */ }
    throw new Error(`${res.status} ${res.statusText} ${detail}`.trim());
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

  // Manually trigger a live CRM ingestion run (manager+).
  crmSyncNow: () =>
    http<{ ok?: boolean; status?: string; created?: number; updated?: number; skipped?: number; errors?: number; fetched?: number; generated?: number }>(
      "/api/procurement/crm-sync",
      { method: "POST" },
    ),

  // Admin-only CRM fetch history (added/changed per fetch).
  crmIngestionLogs: (limit = 50) =>
    http<CrmIngestLog[]>(`/api/procurement/crm-ingestion-logs?limit=${limit}`),

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
  supplierEmailAudit: (limit = 200) =>
    http<SupplierEmailAudit[]>(`/api/supplier-emails/audit?limit=${limit}`),

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

  // Recently-sent feed — powers the global "mail sent" toasts.
  sentFeed: (since?: string) =>
    http<{ items: SentFeedItem[]; server_time: string }>(
      `/api/communication-hub/sent-feed${since ? `?since=${encodeURIComponent(since)}` : ""}`,
    ),

  hubSuppliers: () =>
    http<CommHubSupplier[]>("/api/communication-hub/suppliers"),

  hubPosById: (supplierId: number) =>
    http<CommHubPO[]>(`/api/communication-hub/suppliers/${supplierId}/purchase-orders`),

  hubPosByName: (supplierName: string) =>
    http<CommHubPO[]>(
      `/api/communication-hub/purchase-orders?supplier_name=${encodeURIComponent(supplierName)}`,
    ),

  hubOtherMails: (params: { supplier_id?: number | null; supplier_name?: string | null }) => {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "") q.append(k, String(v));
    });
    return http<OtherMailThread[]>(`/api/communication-hub/other-mails?${q.toString()}`);
  },

  hubThread: (params: { supplier_id?: number | null; procurement_record_id?: number | null; supplier_po_no?: string | null; supplier_name?: string | null; non_po_subject?: string | null }) => {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null) q.append(k, String(v));
    });
    return http<CommHubThread>(`/api/communication-hub/thread?${q.toString()}`);
  },

  hubMarkThreadRead: (params: { supplier_po_no?: string | null; procurement_record_id?: number | null; supplier_id?: number | null; supplier_name?: string | null; non_po_subject?: string | null }) => {
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

  hubReply: (body: {
    procurement_record_id?: number | null;
    supplier_po_no?: string | null;
    supplier_id?: number | null;
    supplier_name?: string | null;
    subject?: string;
    non_po_subject?: string | null;
    body: string;
    send_email: boolean;
  }) =>
    http<{ ok: boolean; message_id: number; channel: "email" | "portal"; sent: boolean; emailed_to: string[]; no_email_on_file: boolean }>(
      "/api/communication-hub/reply",
      { method: "POST", body: JSON.stringify(body) },
    ),

  hubEscalate: (procurementRecordId: number) =>
    http<{ message: string; mail_draft_id: number; task_id: number; subject: string }>(
      `/api/communication-hub/escalate?procurement_record_id=${procurementRecordId}`,
      { method: "POST" },
    ),

  hubAgent: (body: {
    message: string;
    supplier_id?: number | null;
    procurement_record_id?: number | null;
    supplier_po_no?: string | null;
    customer_mail_id?: number | null;
  }) =>
    http<{
      reply: string;
      pending_actions: Array<{
        type: "draft" | "subscription";
        message_id?: number;
        subscription_id?: number;
        recipient?: string;
        subject?: string;
        kind?: string;
        schedule?: string | null;
      }>;
      tools_used: Array<{ name: string }>;
    }>("/api/communication-hub/agent", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  hubAgentConfirm: (body: { action_type: "draft" | "subscription"; id: number }) =>
    http<{ ok: boolean; status?: string; sent?: boolean }>(
      "/api/communication-hub/agent/confirm",
      { method: "POST", body: JSON.stringify(body) },
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

  getAdminDigest: () =>
    http<{ admin_digest: AdminDigestConfig }>("/api/settings/admin-digest"),

  updateAdminDigest: (values: Partial<AdminDigestConfig>) =>
    http<{ admin_digest: AdminDigestConfig }>("/api/settings/admin-digest", {
      method: "PUT",
      body: JSON.stringify(values),
    }),

  sendAdminDigestTest: () =>
    http<{ sent: boolean; recipients: number; reason?: string }>(
      "/api/settings/admin-digest/test",
      { method: "POST" },
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

  // Customer reply (Phase 1) + smart draft (Phase 2)
  replyToCustomerMail: (id: number, body: string, subject?: string) =>
    http<{ ok: boolean; message_id: number; status: string; mail_status: string; queued: boolean; sent: boolean }>(
      `/api/customer-mails/${id}/reply`,
      { method: "POST", body: JSON.stringify({ body, subject }) },
    ),
  getCustomerMailReplies: (id: number) =>
    http<CustomerReply[]>(`/api/customer-mails/${id}/replies`),
  // `instruction` is the agent's typed notes, used as the AI prompt when ai=true.
  draftCustomerReply: (id: number, ai = false, instruction?: string) =>
    http<CustomerDraftReply>(
      `/api/customer-mails/${id}/draft-reply${ai ? "?ai=true" : ""}`,
      { method: "POST", body: JSON.stringify({ instruction }) },
    ),

  // Outbound draft approvals (e.g. auto-reply acknowledgements)
  listOutboxDrafts: () => http<OutboxDraft[]>(`/api/communication-hub/drafts`),
  approveMessage: (id: number) =>
    http<{ ok: boolean; message_id: number; status: string }>(
      `/api/communication-hub/messages/${id}/approve`,
      { method: "POST" },
    ),
  discardMessage: (id: number) =>
    http<{ ok: boolean; discarded_id: number }>(
      `/api/communication-hub/messages/${id}/discard`,
      { method: "POST" },
    ),

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

  listAssignees: () => http<TaskAssignee[]>("/api/communication/assignees"),

  // Mention candidates for /hi: assignable users + recent customers.
  // NOT for assignee/watcher pickers (use listAssignees for those).
  listMentionTargets: () => http<TaskAssignee[]>("/api/communication/mention-targets"),

  generateTaskAiSummary: (taskId: number) =>
    http<CommunicationTask>(`/api/tasks/${taskId}/ai-summary`, { method: "POST" }),

  taskAnalytics: () => http<TaskAnalytics>("/api/communication/analytics"),

  taskAnalyticsExportUrl: () => `/api/communication/analytics/export`,

  // ─── Auth ─────────────────────────────────────────────────────────────
  login: (identifier: string, password: string) => {
    // Staff/suppliers sign in by email; employees by username (no '@').
    const body = identifier.includes("@")
      ? { email: identifier, password }
      : { username: identifier, password };
    return http<LoginResponse>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  me: () => http<AuthUser>("/api/auth/me"),

  changePassword: (current_password: string, new_password: string) =>
    http<{ ok: boolean }>("/api/auth/change-password", {
      method: "POST",
      body: JSON.stringify({ current_password, new_password }),
    }),

  // ─── User management (admin) ──────────────────────────────────────────
  listUsers: (params: { role?: string; is_active?: boolean; search?: string } = {}) => {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "") q.append(k, String(v));
    });
    const qs = q.toString();
    return http<AuthUser[]>(`/api/users${qs ? `?${qs}` : ""}`);
  },

  createUser: (body: UserCreatePayload) =>
    http<AuthUser>("/api/users", { method: "POST", body: JSON.stringify(body) }),

  updateUser: (id: number, body: UserUpdatePayload) =>
    http<AuthUser>(`/api/users/${id}`, { method: "PATCH", body: JSON.stringify(body) }),

  resetUserPassword: (id: number, new_password: string) =>
    http<{ ok: boolean; user_id: number }>(`/api/users/${id}/reset-password`, {
      method: "POST",
      body: JSON.stringify({ new_password }),
    }),

  deleteUser: (id: number) =>
    http<{ ok: boolean; deleted_id: number }>(`/api/users/${id}`, { method: "DELETE" }),

  listRoles: () => http<{ roles: string[] }>("/api/users/meta/roles"),

  // ─── AI assistant ─────────────────────────────────────────────────────
  aiChat: (messages: ChatMessage[], use_tools?: boolean) =>
    http<AiChatResponse>("/api/ai/chat", {
      method: "POST",
      body: JSON.stringify({ messages, use_tools }),
    }),
  aiHealth: () => http<AiHealth>("/api/ai/health"),
  aiTools: () => http<{ agent_enabled: boolean; tools: string[] }>("/api/ai/tools"),

  // Triage + summarize a customer mail
  triageCustomerMail: (id: number) =>
    http<{ ok: boolean; mail_id: number; category: string; urgency: string; action: string; summary: string }>(
      `/api/ai/triage/customer-mail/${id}`,
      { method: "POST" },
    ),
  summarizeCustomerMail: (id: number) =>
    http<{ ok: boolean; mail_id: number; summary: string }>(
      `/api/ai/summary/customer-mail/${id}`,
      { method: "POST" },
    ),

  // Semantic memory (RAG)
  aiMemoryStats: () => http<AiMemoryStats>("/api/ai/memory/stats"),
  aiMemoryBackfill: (limit = 500) =>
    http<{ enabled: boolean; indexed: number; skipped: number }>(
      `/api/ai/memory/backfill?limit=${limit}`,
      { method: "POST" },
    ),

  // ─── AI insights: delay risk + supplier scorecards ────────────────────
  getDelayRisk: (params: { band?: string; limit?: number } = {}) => {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "") q.append(k, String(v));
    });
    const qs = q.toString();
    return http<DelayRiskResponse>(`/api/ai/insights/delay-risk${qs ? `?${qs}` : ""}`);
  },
  rescoreDelayRisk: () =>
    http<{ updated: number; by_band: Record<string, number>; ran_at: string }>(
      "/api/ai/insights/delay-risk/rescore",
      { method: "POST" },
    ),
  getSupplierScorecards: (limit = 100) =>
    http<{ count: number; items: SupplierScorecard[] }>(
      `/api/ai/insights/suppliers?limit=${limit}`,
    ),
  getSupplierScorecard: (name: string) =>
    http<SupplierScorecard>(`/api/ai/insights/suppliers/${encodeURIComponent(name)}`),
  getBlackFollowups: (limit = 100) =>
    http<BlackFollowupResponse>(`/api/ai/insights/black-followups?limit=${limit}`),
  getFollowupHistory: (params: { signal?: string; outcome?: string; supplier_po_no?: string; limit?: number } = {}) => {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "") q.append(k, String(v));
    });
    const qs = q.toString();
    return http<FollowupHistoryResponse>(`/api/ai/insights/followup-history${qs ? `?${qs}` : ""}`);
  },
  // Editable system prompts (manager)
  getAiPrompts: () => http<{ prompts: AiPromptsMap }>("/api/ai/prompts"),
  saveAiPrompts: (prompts: Record<string, string | null>) =>
    http<{ prompts: AiPromptsMap }>("/api/ai/prompts", {
      method: "PUT",
      body: JSON.stringify({ prompts }),
    }),
  // AI feedback capture (tuning dataset)
  submitAiFeedback: (f: AiFeedbackInput) =>
    http<{ ok: boolean; id: number }>("/api/ai/feedback", {
      method: "POST",
      body: JSON.stringify(f),
    }),
  // Tell the AI what to follow up on for a PO. send=false → preview only;
  // send=true → queue + send to the supplier (manager only).
  blackFollowupCommand: (supplier_po_no: string, instruction: string, send = false) =>
    http<BlackFollowupCommandResult>("/api/ai/insights/black-followups/command", {
      method: "POST",
      body: JSON.stringify({ supplier_po_no, instruction, send }),
    }),

  // Employee-scoped Black Follow-ups — mirror of the three admin endpoints above,
  // restricted to the employee's owned POs (byte-identical response shapes). The
  // employee may send on their own PO (ownership is the authorization).
  eportalGetBlackFollowups: (limit = 100) =>
    http<BlackFollowupResponse>(`/api/eportal/ai/insights/black-followups?limit=${limit}`),
  eportalGetFollowupHistory: (params: { signal?: string; outcome?: string; supplier_po_no?: string; limit?: number } = {}) => {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "") q.append(k, String(v));
    });
    const qs = q.toString();
    return http<FollowupHistoryResponse>(`/api/eportal/ai/insights/followup-history${qs ? `?${qs}` : ""}`);
  },
  eportalBlackFollowupCommand: (supplier_po_no: string, instruction: string, send = false) =>
    http<BlackFollowupCommandResult>("/api/eportal/ai/insights/black-followups/command", {
      method: "POST",
      body: JSON.stringify({ supplier_po_no, instruction, send }),
    }),

  // ─── Supplier login management (admin) ────────────────────────────────
  listSupplierLogins: (supplierId?: number) =>
    http<SupplierLogin[]>(
      `/api/supplier-accounts${supplierId != null ? `?supplier_id=${supplierId}` : ""}`,
    ),
  resetSupplierLogin: (userId: number) =>
    http<{ ok: boolean; email: string; temp_password: string; emailed: boolean }>(
      `/api/supplier-accounts/${userId}/reset-password`,
      { method: "POST" },
    ),
  activateSupplierLogin: (userId: number) =>
    http<SupplierLogin>(`/api/supplier-accounts/${userId}/activate`, { method: "POST" }),
  deactivateSupplierLogin: (userId: number) =>
    http<SupplierLogin>(`/api/supplier-accounts/${userId}/deactivate`, { method: "POST" }),

  // ─── Internal ASN view (staff) ────────────────────────────────────────
  listAsns: (params: { tab?: string; status?: string; search?: string } = {}) => {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "") q.append(k, String(v));
    });
    const qs = q.toString();
    return http<AsnListResponse>(`/api/asns${qs ? `?${qs}` : ""}`);
  },
  asnSummary: () => http<AsnSummary>("/api/asns/summary"),
  getAsn: (id: number) => http<Asn>(`/api/asns/${id}`),
  updateAsn: (id: number, body: Partial<AsnCreatePayload> & { alert?: boolean; alert_reason?: string; submit?: boolean }) =>
    http<Asn>(`/api/asns/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  addAsnEvent: (id: number, body: AsnEventPayload) =>
    http<Asn>(`/api/asns/${id}/events`, { method: "POST", body: JSON.stringify(body) }),
  // Pull fresh courier checkpoints on demand (drawer open). Fail-safe server-side.
  refreshAsnTracking: (id: number) =>
    http<Asn>(`/api/asns/${id}/refresh-tracking`, { method: "POST" }),

  // ─── Supplier portal (supplier accounts only) ─────────────────────────
  portalMe: () => http<PortalMe>("/api/portal/me"),
  portalSummary: () => http<PortalSummary>("/api/portal/summary"),
  portalPos: () => http<PortalPoListResponse>("/api/portal/pos"),
  portalPoMaterials: (supplierPoNo: string) =>
    http<PortalPoMaterial[]>(`/api/portal/pos/${encodeURIComponent(supplierPoNo)}/materials`),
  submitPortalCommitments: (supplierPoNo: string, items: PortalCommitmentItem[]) =>
    http<PortalPoMaterial[]>(`/api/portal/pos/${encodeURIComponent(supplierPoNo)}/commitments`, {
      method: "POST",
      body: JSON.stringify({ items }),
    }),
  portalPoTasks: (supplierPoNo: string) =>
    http<PortalTask[]>(`/api/portal/pos/${encodeURIComponent(supplierPoNo)}/tasks`),
  // Read-only Task Manager view (backend nulls internal fields server-side).
  portalTasks: () => http<CommunicationTask[]>("/api/portal/tasks"),
  portalTasksDashboard: () => http<PortalTaskDashboard>("/api/portal/tasks/dashboard"),
  portalPoMessages: (supplierPoNo: string) =>
    http<PortalMessage[]>(`/api/portal/pos/${encodeURIComponent(supplierPoNo)}/messages`),
  sendPortalPoMessage: (supplierPoNo: string, body: string, subject?: string) =>
    http<PortalMessage>(`/api/portal/pos/${encodeURIComponent(supplierPoNo)}/messages`, {
      method: "POST",
      body: JSON.stringify({ body, subject }),
    }),
  // Clear the unread-inbound badge for a supplier's PO thread.
  portalMarkPoRead: (supplierPoNo: string) =>
    http<{ marked: number }>(
      `/api/portal/pos/${encodeURIComponent(supplierPoNo)}/messages/mark-read`,
      { method: "POST" },
    ),
  portalAsnSummary: () => http<AsnSummary>("/api/portal/asns/summary"),
  portalAsns: (params: { tab?: string; search?: string } = {}) => {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "") q.append(k, String(v));
    });
    const qs = q.toString();
    return http<AsnListResponse>(`/api/portal/asns${qs ? `?${qs}` : ""}`);
  },
  getPortalAsn: (id: number) => http<Asn>(`/api/portal/asns/${id}`),
  createPortalAsn: (body: AsnCreatePayload) =>
    http<Asn>("/api/portal/asns", { method: "POST", body: JSON.stringify(body) }),
  updatePortalAsn: (id: number, body: Partial<AsnCreatePayload> & { alert?: boolean; alert_reason?: string; submit?: boolean }) =>
    http<Asn>(`/api/portal/asns/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  addPortalAsnEvent: (id: number, body: AsnEventPayload) =>
    http<Asn>(`/api/portal/asns/${id}/events`, { method: "POST", body: JSON.stringify(body) }),
  refreshPortalAsnTracking: (id: number) =>
    http<Asn>(`/api/portal/asns/${id}/refresh-tracking`, { method: "POST" }),

  // Supplier assistant (Harmony Intelligent, scoped to this supplier's data).
  portalAssistantHealth: () => http<{ enabled: boolean }>("/api/portal/assistant/health"),
  portalAssistantChat: (messages: ChatMessage[]) =>
    http<AiChatResponse>("/api/portal/assistant/chat", {
      method: "POST",
      body: JSON.stringify({ messages }),
    }),

  // ─── Employee portal (employee accounts only) ─────────────────────────
  eportalMe: () =>
    http<{ id: number; username: string | null; full_name: string | null; emp_code: string | null; must_change_password: boolean }>(
      "/api/eportal/me",
    ),
  eportalSummary: () => http<EmployeeSummary>("/api/eportal/summary"),

  // PO Follow-ups (mirrors the staff /api/procurement endpoints, scoped to the
  // employee's owned records — IDENTICAL response shapes + query building so the
  // staff store/components can be reused verbatim).
  eportalDashboard: () => http<DashboardKpis>("/api/eportal/procurement/dashboard"),
  eportalProcurement: (filters: ProcurementFilters = {}) => {
    const q = new URLSearchParams();
    Object.entries(filters).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "") q.append(k, String(v));
    });
    const qs = q.toString();
    return http<ProcurementListResponse>(`/api/eportal/procurement${qs ? `?${qs}` : ""}`);
  },

  eportalPos: () => http<EmployeePoListResponse>("/api/eportal/pos"),
  eportalPoMaterials: (supplierPoNo: string) =>
    http<EmployeePoMaterial[]>(`/api/eportal/pos/${encodeURIComponent(supplierPoNo)}/materials`),
  eportalPoMessages: (supplierPoNo: string) =>
    http<PortalMessage[]>(`/api/eportal/pos/${encodeURIComponent(supplierPoNo)}/messages`),
  eportalSendMessage: (supplierPoNo: string, body: string, subject?: string) =>
    http<PortalMessage>(`/api/eportal/pos/${encodeURIComponent(supplierPoNo)}/messages`, {
      method: "POST",
      body: JSON.stringify({ body, subject }),
    }),
  // Clear the unread-inbound badge for an employee's PO thread.
  eportalMarkPoRead: (supplierPoNo: string) =>
    http<{ marked: number }>(
      `/api/eportal/pos/${encodeURIComponent(supplierPoNo)}/messages/mark-read`,
      { method: "POST" },
    ),

  // Full-parity Task Manager (scoped to the employee's owned POs).
  eportalTasks: (filters: {
    status?: string;
    task_source?: string;
    supplier_po_no?: string;
    overdue?: boolean;
  } = {}) => {
    const q = new URLSearchParams();
    Object.entries(filters).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "" && v !== false) q.append(k, String(v));
    });
    const qs = q.toString();
    return http<CommunicationTask[]>(`/api/eportal/tasks${qs ? `?${qs}` : ""}`);
  },
  eportalTasksDashboard: () => http<PortalTaskDashboard>("/api/eportal/tasks/dashboard"),
  eportalAssignees: () => http<TaskAssignee[]>("/api/eportal/assignees"),
  eportalCreateTask: (body: CommunicationTaskCreate) =>
    http<CommunicationTask>("/api/eportal/tasks", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  eportalUpdateTask: (id: number, patch: CommunicationTaskUpdate) =>
    http<CommunicationTask>(`/api/eportal/tasks/${id}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),
  eportalDeleteTask: (id: number) =>
    http<void>(`/api/eportal/tasks/${id}`, { method: "DELETE" }),
  eportalTaskComments: (id: number) =>
    http<TaskComment[]>(`/api/eportal/tasks/${id}/comments`),
  eportalAddTaskComment: (id: number, comment: string) =>
    http<TaskComment>(`/api/eportal/tasks/${id}/comments`, {
      method: "POST",
      body: JSON.stringify({ comment }),
    }),

  // ─── Employee Communication Hub (mirrors /api/communication-hub/*, ──────
  // scoped to the employee's owned POs — BYTE-IDENTICAL response shapes).
  eportalHubDashboard: () =>
    http<CommHubDashboard>("/api/eportal/hub/dashboard"),

  eportalHubSuppliers: () =>
    http<CommHubSupplier[]>("/api/eportal/hub/suppliers"),

  eportalHubPos: (params: { supplier_name?: string; supplier_id?: number } = {}) => {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "") q.append(k, String(v));
    });
    const qs = q.toString();
    return http<CommHubPO[]>(`/api/eportal/hub/pos${qs ? `?${qs}` : ""}`);
  },

  eportalHubOtherMails: (params: { supplier_id?: number | null; supplier_name?: string | null }) => {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "") q.append(k, String(v));
    });
    return http<OtherMailThread[]>(`/api/eportal/hub/other-mails?${q.toString()}`);
  },

  eportalHubThread: (params: { supplier_id?: number | null; procurement_record_id?: number | null; supplier_po_no?: string | null; supplier_name?: string | null; non_po_subject?: string | null }) => {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null) q.append(k, String(v));
    });
    return http<CommHubThread>(`/api/eportal/hub/thread?${q.toString()}`);
  },

  eportalHubMarkThreadRead: (params: { supplier_po_no?: string | null; procurement_record_id?: number | null; supplier_id?: number | null; supplier_name?: string | null; non_po_subject?: string | null }) => {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "") q.append(k, String(v));
    });
    return http<{ marked: number; at: string }>(
      `/api/eportal/hub/thread/mark-read?${q.toString()}`,
      { method: "POST" },
    );
  },

  eportalHubTasks: (params: CommHubTaskFilters = {}) => {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null) q.append(k, String(v));
    });
    const qs = q.toString();
    return http<CommHubTasksGrouped>(`/api/eportal/hub/tasks${qs ? `?${qs}` : ""}`);
  },

  eportalHubCreateTask: (body: CommunicationTaskCreate) =>
    http<CommunicationTask>("/api/eportal/hub/tasks", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  eportalHubUpdateTask: (id: number, body: CommunicationTaskUpdate) =>
    http<CommunicationTask>(`/api/eportal/hub/tasks/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  eportalHubAiReply: (procurementRecordId: number) =>
    http<{ subject: string; body: string; mail_type: string }>(
      `/api/eportal/hub/ai-reply?procurement_record_id=${procurementRecordId}`,
      { method: "POST" },
    ),

  eportalHubReply: (body: {
    procurement_record_id?: number | null;
    supplier_po_no?: string | null;
    supplier_id?: number | null;
    supplier_name?: string | null;
    subject?: string;
    non_po_subject?: string | null;
    body: string;
    send_email: boolean;
  }) =>
    http<{ ok: boolean; message_id: number; channel: "email" | "portal"; sent: boolean; emailed_to: string[]; no_email_on_file: boolean }>(
      "/api/eportal/hub/reply",
      { method: "POST", body: JSON.stringify(body) },
    ),

  eportalHubEscalate: (procurementRecordId: number) =>
    http<{ message: string; mail_draft_id: number; task_id: number; subject: string }>(
      `/api/eportal/hub/escalate?procurement_record_id=${procurementRecordId}`,
      { method: "POST" },
    ),

  eportalHubAgent: (body: {
    message: string;
    supplier_id?: number | null;
    procurement_record_id?: number | null;
    supplier_po_no?: string | null;
    customer_mail_id?: number | null;
  }) =>
    http<{
      reply: string;
      pending_actions: Array<{
        type: "draft" | "subscription";
        message_id?: number;
        subscription_id?: number;
        recipient?: string;
        subject?: string;
        kind?: string;
        schedule?: string | null;
      }>;
      tools_used: Array<{ name: string }>;
    }>("/api/eportal/hub/agent", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  eportalHubAgentConfirm: (body: { action_type: "draft" | "subscription"; id: number }) =>
    http<{ ok: boolean; status?: string; sent?: boolean }>(
      "/api/eportal/hub/agent/confirm",
      { method: "POST", body: JSON.stringify(body) },
    ),

  eportalHubSendMail: (mail_history_id: number) =>
    http<{ mail_history_id: number; send_result: any }>(
      `/api/eportal/hub/send-mail?mail_history_id=${mail_history_id}`,
      { method: "POST" },
    ),

  eportalHubAssignees: () => http<TaskAssignee[]>("/api/eportal/hub/assignees"),

  eportalHubMentionTargets: () => http<TaskAssignee[]>("/api/eportal/hub/mention-targets"),

  eportalHubCommitments: (params: { supplier_po_no: string; supplier_name?: string }) => {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "") q.append(k, String(v));
    });
    return http<SupplierMaterialCommitment[]>(`/api/eportal/hub/commitments?${q.toString()}`);
  },

  eportalHubApproveMessage: (id: number) =>
    http<{ ok: boolean; message_id: number; status: string }>(
      `/api/eportal/hub/messages/${id}/approve`,
      { method: "POST" },
    ),

  eportalHubDiscardMessage: (id: number) =>
    http<{ ok: boolean; discarded_id: number }>(
      `/api/eportal/hub/messages/${id}/discard`,
      { method: "POST" },
    ),

  // ─── Employee login management (admin) ────────────────────────────────
  listEmployeeLogins: () => http<AuthUser[]>("/api/employee-accounts"),
  importEmployeeSheet: (file: File) => {
    const body = new FormData();
    body.append("file", file);
    return http<EmployeeProvisionResult>("/api/employee-accounts/import-sheet", { method: "POST", body });
  },
  createEmployeeLogin: (body: EmployeeCreatePayload) =>
    http<{ ok: boolean; id: number; username: string; full_name?: string | null; emp_code?: string | null; temp_password: string }>(
      "/api/employee-accounts",
      { method: "POST", body: JSON.stringify(body) },
    ),
  updateEmployeeLogin: (userId: number, body: { email?: string; full_name?: string | null }) =>
    http<AuthUser>(`/api/employee-accounts/${userId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  resetEmployeeLogin: (userId: number) =>
    http<{ ok: boolean; id: number; username: string | null; full_name: string | null; temp_password: string }>(
      `/api/employee-accounts/${userId}/reset-password`,
      { method: "POST" },
    ),
  activateEmployeeLogin: (userId: number) =>
    http<AuthUser>(`/api/employee-accounts/${userId}/activate`, { method: "POST" }),
  deactivateEmployeeLogin: (userId: number) =>
    http<AuthUser>(`/api/employee-accounts/${userId}/deactivate`, { method: "POST" }),
  deleteEmployeeLogin: (userId: number) =>
    http<{ ok: boolean; deleted: number }>(`/api/employee-accounts/${userId}`, { method: "DELETE" }),
  downloadEmployeeCredentials: async (
    items: { full_name?: string | null; username?: string | null; temp_password?: string | null }[],
  ) => {
    const token = getToken();
    const res = await fetch("/api/employee-accounts/credentials.xlsx", {
      method: "POST",
      headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: JSON.stringify(items),
    });
    if (!res.ok) throw new Error("Could not download credentials");
    return res.blob();
  },

  // ─── Notifications (staff + supplier) ─────────────────────────────────
  listNotifications: (limit = 30) =>
    http<AppNotification[]>(`/api/notifications?limit=${limit}`),
  notificationsUnreadCount: () =>
    http<{ count: number }>("/api/notifications/unread-count"),
  markNotificationRead: (id: number) =>
    http<{ ok: boolean }>(`/api/notifications/${id}/read`, { method: "POST" }),
  markAllNotificationsRead: () =>
    http<{ ok: boolean; updated: number }>("/api/notifications/read-all", { method: "POST" }),
};

export default api;

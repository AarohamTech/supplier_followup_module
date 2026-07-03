export type Signal = "GREEN" | "YELLOW" | "RED" | "BLACK";

export interface SentFeedItem {
  id: number;
  subject: string | null;
  supplier_name: string | null;
  to: string | null;
  mail_type: string | null;
  sent_at: string | null;
}

export interface ProcurementRecord {
  id: number;
  crm_no: string;
  material_name: string;
  uom?: string | null;
  lead_time?: number | null;
  shipment_date?: string | null;
  signal?: Signal | null;
  stock?: number | null;
  qty?: number | null;
  po_status?: string | null;
  adv_status?: string | null;
  supplier_po_no: string;
  supplier_date?: string | null;
  supplier_name?: string | null;
  quantity?: number | null;
  rate?: number | null;
  po_no?: string | null; // end-customer PO number (distinct from supplier_po_no)
  customer_name?: string | null;
  customer_po_no?: string | null; // mirror of po_no exposed by the API
  po_date?: string | null; // end-customer PO date

  followup_status: string;
  mail_status: string;
  followup_count: number;
  last_followup_date?: string | null;
  last_supplier_reply?: string | null;
  commitment_date?: string | null;
  delay_reason?: string | null;
  escalation_level: string;
  ai_required: boolean;
  next_followup_date?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProcurementListResponse {
  total: number;
  page: number;
  size: number;
  items: ProcurementRecord[];
}

export interface DashboardKpis {
  total_records: number;
  green_count: number;
  yellow_count: number;
  red_count: number;
  black_count: number;
  overdue_count: number;
  due_today_count: number;
  ai_required_count: number;
}

export interface SupplierSlice {
  name: string;
  count: number;
}

export interface ProcurementBreakdown {
  total: number;
  green_count: number;
  yellow_count: number;
  red_count: number;
  black_count: number;
  pending_count: number;
  by_supplier: SupplierSlice[];
}

export interface CreatedLogin {
  email: string;
  temp_password: string;
}

export interface LoginConflict {
  email: string;
  reason: string;
}

export interface LoginProvisioningSummary {
  created: CreatedLogin[];
  reactivated: string[];
  deactivated: string[];
  conflicts: LoginConflict[];
  emailed: string[];
}

export interface SupplierEmail {
  id: number;
  supplier_id: number;
  supplier_name: string;
  to_emails: string[];
  cc_emails: string[];
  bcc_emails: string[];
  escalation_emails: string[];
  contact_person?: string | null;
  phone?: string | null;
  remarks?: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  // Present only on create/update responses (login provisioning result).
  provisioning?: LoginProvisioningSummary | null;
}

export interface SupplierEmailAudit {
  id: number;
  supplier_email_id: number | null;
  supplier_id: number | null;
  supplier_name: string | null;
  action: "CREATE" | "UPDATE" | "DELETE";
  changed_by_id: number | null;
  changed_by: string | null;
  changes: Record<string, { old: unknown; new: unknown }> | null;
  created_at: string;
}

export interface SupplierLogin {
  id: number;
  email: string;
  supplier_id?: number | null;
  is_active: boolean;
  must_change_password: boolean;
  last_login_at?: string | null;
  created_at: string;
}

export interface SupplierMaster {
  id: number;
  supplier_name: string;
  latest_supplier_po_no?: string | null;
  latest_signal?: Signal | string | null;
  is_active: boolean;
  email_mapped: boolean;
  primary_email?: string | null;
  created_at: string;
  updated_at: string;
}

export interface MailDraft {
  history_id: number;
  procurement_record_id: number;
  to_emails: string[];
  cc_emails: string[];
  bcc_emails: string[];
  escalation_emails: string[];
  subject: string;
  body: string;
  mail_type: string;
  ai_required: boolean;
  notes?: string | null;
}

export interface SupplierMaterialCommitment {
  id: number;
  material_code?: string | null;
  material_name: string;
  commitment_qty?: number | null;
  commitment_date?: string | null;
  supplier_status: string;
  supplier_remark?: string | null;
  reply_mail_id?: number | null;
  updated_at?: string | null;
}

export interface PoFollowupMaterial {
  procurement_record_id: number;
  crm_no: string;
  material_code?: string | null;
  material_name: string;
  po_qty?: number | null;
  pending_qty?: number | null;
  uom?: string | null;
  due_date?: string | null;
  current_status?: string | null;
  signal: Signal | string;
  followup_status?: string | null;
  ai_required?: boolean;
  last_supplier_reply?: string | null;
  commitment?: SupplierMaterialCommitment | null;
}

export interface PoFollowupGroup {
  supplier_id?: number | null;
  supplier_name?: string | null;
  supplier_po_no: string;
  material_count: number;
  overall_signal: Signal | string;
  earliest_due_date?: string | null;
  latest_followup_date?: string | null;
  escalation_levels: string[];
  ai_required: boolean;
  mapping_active: boolean;
  to_emails: string[];
  cc_emails: string[];
  bcc_emails: string[];
  escalation_emails: string[];
  procurement_record_ids: number[];
  anchor_record_id: number;
  materials: PoFollowupMaterial[];
}

export interface PoFollowupListResponse {
  total: number;
  page: number;
  size: number;
  items: PoFollowupGroup[];
}

export interface MailDraftPo {
  history_id: number;
  procurement_record_id: number;
  supplier_name?: string | null;
  supplier_po_no: string;
  to_emails: string[];
  cc_emails: string[];
  bcc_emails: string[];
  escalation_emails: string[];
  subject: string;
  body: string;
  body_html: string;
  mail_type: string;
  overall_signal: Signal | string;
  material_count: number;
  materials: PoFollowupMaterial[];
  reused_existing: boolean;
  notes?: string | null;
}

export interface OutlookComposeRequest {
  history_id: number;
  procurement_record_id: number;
  supplier_po_no?: string | null;
  to_emails: string[];
  cc_emails: string[];
  bcc_emails: string[];
  escalation_emails: string[];
  subject: string;
  body: string;
  body_html?: string | null;
}

export interface OutlookComposeResult {
  ok: boolean;
  message: string;
}

export interface MailHistory {
  id: number;
  procurement_record_id: number;
  supplier_id?: number | null;
  supplier_name?: string | null;
  supplier_po_no: string;
  material_name: string;
  to_emails: string[];
  cc_emails: string[];
  bcc_emails: string[];
  escalation_emails: string[];
  subject: string;
  body: string;
  mail_type: string;
  sent_status: "DRAFT" | "COPIED" | "MAILTO_OPENED" | "SENT_MANUALLY" | string;
  created_at: string;
  sent_at?: string | null;
  remarks?: string | null;
}

export interface MailHistoryFilters {
  supplier?: string;
  po_no?: string;
  supplier_po_no?: string;
  subject?: string;
  mail_type?: string;
  status?: string;
  limit?: number;
}

export interface ProcurementSyncError {
  row_index: number;
  error: string;
}

export interface ProcurementSyncSummary {
  source: string;
  created_count: number;
  updated_count: number;
  skipped_count: number;
  error_count: number;
  errors: ProcurementSyncError[];
}

export interface ProcurementFilters {
  signal?: string;
  supplier_name?: string;
  supplier_po_no?: string;
  crm_no?: string;
  po_status?: string;
  owner_emp_code?: string;
  search?: string;
  page?: number;
  size?: number;
}

// ─── Communication Tasks ─────────────────────────────────────────────────────
export type TaskStatus =
  | "BACKLOG"
  | "TODO"
  | "IN_PROGRESS"
  | "WAITING_SUPPLIER"
  | "WAITING_CUSTOMER"
  | "BLOCKED"
  | "DONE";
export type TaskPriority = "P0" | "P1" | "P2" | "P3";
export type TaskSignal = "GREEN" | "YELLOW" | "RED" | "BLACK";
export type TaskSource = "SUPPLIER" | "CUSTOMER" | "INTERNAL" | "ESCALATION";

export interface TaskComment {
  id: number;
  task_id: number;
  comment: string;
  created_by?: string | null;
  created_by_id?: number | null;
  created_at: string;
}

export interface TaskActivity {
  id: number;
  task_id: number;
  activity_type: string;
  old_value?: string | null;
  new_value?: string | null;
  created_by?: string | null;
  created_by_id?: number | null;
  created_at: string;
}

export interface TaskAssignee {
  id: number;
  label: string;
  role: string;
  type: "staff" | "employee" | "customer";
  email?: string;
}

// ─── Admin workload report (per-user / per-supplier / overall) ───────────────
export interface WorkloadPoStats {
  total: number;
  pending: number;
  overdue: number;
  green: number;
  yellow: number;
  red: number;
  black: number;
  avg_followups: number;
}

export interface WorkloadTaskStats {
  total: number;
  open: number;
  overdue: number;
  done: number;
  due_today: number;
  escalations: number;
}

export interface WorkloadUserRow {
  user_id: number;
  name: string;
  role: string;
  emp_code?: string | null;
  last_login_at?: string | null;
  pos: WorkloadPoStats;
  tasks: WorkloadTaskStats;
}

export interface WorkloadSupplierRow {
  supplier_id: number;
  supplier_name: string;
  worst_signal?: string | null;
  pos: WorkloadPoStats;
  tasks: WorkloadTaskStats;
  mails: { incoming: number; outgoing: number; unread: number };
  asns: { total: number; in_transit: number; delivered: number };
}

export interface WorkloadCustomerRow {
  customer_name: string;
  worst_signal?: string | null;
  pos: WorkloadPoStats;
  suppliers: number;
  po_lines: number;
}

export interface WorkloadReport {
  overall: {
    pos: WorkloadPoStats;
    tasks: WorkloadTaskStats;
    suppliers_active: number;
    customers_active?: number;
    internal_users: number;
    unassigned_open_tasks: number;
    unread_inbound: number;
    asns_in_transit: number;
    generated_at: string;
  };
  users: WorkloadUserRow[];
  suppliers: WorkloadSupplierRow[];
  customers: WorkloadCustomerRow[];
}

export interface WorkloadPendingPo {
  procurement_record_id: number;
  supplier_po_no: string;
  supplier_name?: string | null;
  material_name: string;
  qty?: number | null;
  uom?: string | null;
  signal?: string | null;
  po_status?: string | null;
  shipment_date?: string | null;
  days_overdue?: number | null;
  followup_count: number;
  commitment_date?: string | null;
  escalation_level?: string | null;
}

export interface WorkloadOpenTask {
  id: number;
  title: string;
  priority: string;
  status: string;
  signal?: string | null;
  task_source?: string | null;
  supplier_name?: string | null;
  supplier_po_no?: string | null;
  due_date?: string | null;
  days_overdue?: number | null;
  progress_percent: number;
}

export interface WorkloadThroughputDay {
  day: string;
  created: number;
  completed: number;
}

export interface WorkloadDetailCommon {
  pos: WorkloadPoStats;
  tasks: WorkloadTaskStats;
  by_status: Record<string, number>;
  by_priority: Record<string, number>;
  avg_cycle_hours: number | null;
  throughput: WorkloadThroughputDay[];
  pending_pos: WorkloadPendingPo[];
  open_tasks: WorkloadOpenTask[];
}

export interface WorkloadUserDetail extends WorkloadDetailCommon {
  user: {
    user_id: number;
    name: string;
    role: string;
    emp_code?: string | null;
    email?: string | null;
    last_login_at?: string | null;
  };
}

export interface WorkloadSupplierDetail extends WorkloadDetailCommon {
  supplier: { supplier_id: number; supplier_name: string; is_active: boolean };
  worst_signal?: string | null;
  mails: { incoming: number; outgoing: number; unread: number; response_rate: number | null };
  asns: Array<{
    id: number;
    asn_no: string;
    supplier_po_no?: string | null;
    status: string;
    status_label?: string | null;
    progress_percent: number;
    carrier_name?: string | null;
    tracking_no?: string | null;
    eta?: string | null;
    alert: boolean;
  }>;
}

export interface TaskAnalytics {
  totals: { total: number; open: number; overdue: number; done: number; due_today: number };
  by_status: Record<string, number>;
  by_priority: Record<string, number>;
  by_source: Record<string, number>;
  by_assignee: { user_id: number; name: string; open: number; overdue: number; done: number }[];
  avg_cycle_hours: number | null;
  throughput: { date: string; created: number; completed: number }[];
}

export interface CommunicationTask {
  id: number;
  title: string;
  description?: string | null;
  supplier_id?: number | null;
  supplier_name?: string | null;
  supplier_po_no?: string | null;
  procurement_record_id?: number | null;
  linked_mail_id?: number | null;
  customer_mail_id?: number | null;
  material_name?: string | null;
  task_source?: TaskSource;
  created_from_mail_id?: number | null;
  assigned_to?: string | null;
  assigned_by?: string | null;
  assigned_to_user_id?: number | null;
  assigned_at?: string | null;
  watchers: number[];
  progress_percent?: number;
  ai_summary?: string | null;
  ai_summary_at?: string | null;
  ai_summary_by?: string | null;
  priority: TaskPriority;
  status: TaskStatus;
  signal: TaskSignal;
  escalation_level?: number;
  due_date?: string | null;
  reminder_at?: string | null;
  closed_at?: string | null;
  comments_count: number;
  attachment_count: number;
  created_at: string;
  updated_at: string;
}

export interface CommunicationTaskCreate {
  title: string;
  description?: string | null;
  supplier_id?: number | null;
  supplier_name?: string | null;
  supplier_po_no?: string | null;
  procurement_record_id?: number | null;
  linked_mail_id?: number | null;
  customer_mail_id?: number | null;
  material_name?: string | null;
  task_source?: TaskSource;
  assigned_to?: string | null;
  assigned_by?: string | null;
  assigned_to_user_id?: number | null;
  watchers?: number[];
  progress_percent?: number;
  priority?: TaskPriority;
  status?: TaskStatus;
  signal?: TaskSignal;
  due_date?: string | null;
  reminder_at?: string | null;
}

export interface CommunicationTaskUpdate {
  title?: string;
  description?: string | null;
  assigned_to?: string | null;
  assigned_to_user_id?: number | null;
  watchers?: number[];
  progress_percent?: number;
  priority?: TaskPriority;
  status?: TaskStatus;
  signal?: TaskSignal;
  task_source?: TaskSource;
  material_name?: string | null;
  escalation_level?: number;
  due_date?: string | null;
  reminder_at?: string | null;
}

export interface CommunicationTaskFilters {
  supplier_name?: string;
  supplier_po_no?: string;
  linked_mail_id?: number;
  status?: TaskStatus;
  assigned_to?: string;
  limit?: number;
}

export interface CommunicationDashboard {
  total_tasks: number;
  todo: number;
  waiting: number;
  in_progress: number;
  done: number;
  overdue: number;
  critical: number;
}

// Portal/eportal task dashboard — same shape the backend returns for
// /api/eportal/tasks/dashboard and /api/portal/tasks/dashboard.
export interface PortalTaskDashboard {
  total_tasks: number;
  todo: number;
  in_progress: number;
  waiting: number;
  done: number;
  overdue: number;
  due_today: number;
  critical: number;
  supplier_tasks: number;
  customer_tasks: number;
  internal_tasks: number;
  escalation_tasks: number;
}

// ─── Communication Hub (aggregation layer) ────────────────────────────────────
export interface CommHubDashboard {
  active_suppliers: number;
  active_pos: number;
  draft_mails: number;
  sent_mails: number;
  open_tasks: number;
  critical_escalations: number;
  delayed_pos: number;
  waiting_supplier: number;
  unread_inbound?: number;
}

export interface CommHubSupplier {
  supplier_id: number | null;
  supplier_name: string;
  last_subject: string | null;
  last_activity_at: string | null;
  open_po_count: number;
  mail_count: number;
  draft_mail_count: number;
  task_count: number;
  unread_inbound?: number;
  non_po_count?: number;
  highest_signal: string;
  health_score: number;
  mapping_status: string;
}

// A non-PO ("Other Mails") conversation, grouped by normalized subject.
export interface OtherMailThread {
  thread_key: string;
  subject: string;
  supplier_id: number | null;
  supplier_name: string | null;
  sender_email: string | null;
  message_count: number;
  unread_inbound: number;
  last_activity_at: string | null;
}

export interface CommHubPO {
  procurement_record_id: number;
  supplier_id: number | null;
  supplier_name: string;
  supplier_po_no: string;
  material_name: string;
  qty: number | null;
  shipment_date: string | null;
  signal: string;
  risk_level: string;
  mail_count: number;
  task_count: number;
  unread_inbound?: number;
  latest_inbound_at?: string | null;
  last_activity_at: string | null;
  material_count?: number;
  materials?: PoFollowupMaterial[];
  procurement_record_ids?: number[];
}

export interface ThreadTableRow {
  crm_no?: string | null;
  material_name?: string | null;
  qty?: number | null;
  uom?: string | null;
  due_date?: string | null;
  status?: string | null;
  commitment_date?: string | null;
  remark?: string | null;
}

export interface CommHubMessage {
  id: number | string;
  procurement_record_id: number | null;
  supplier_id?: number | null;
  supplier_name?: string | null;
  supplier_po_no?: string | null;
  material_name?: string | null;
  to_emails: string[];
  cc_emails: string[];
  bcc_emails: string[];
  escalation_emails?: string[];
  subject: string | null;
  body: string | null;
  mail_type: string | null;
  sent_status: string;
  created_at: string;
  sent_at?: string | null;
  received_at?: string | null;
  remarks?: string | null;
  signal: string;
  source?: string;
  direction?: string;
  sender_email?: string | null;
  receiver_email?: string | null;
  parsed?: {
    status?: string | null;
    qty?: number | null;
    date?: string | null;
  } | null;
  error_message?: string | null;
  table_format?: string | null;
  table_rows?: ThreadTableRow[];
}

export interface CommHubThread {
  thread_id: string;
  supplier_id: number | null;
  supplier_name: string | null;
  procurement_record_id: number | null;
  supplier_po_no: string | null;
  non_po_subject?: string | null;
  signal: string;
  risk_level: string;
  messages: CommHubMessage[];
}

export interface HiAgentAction {
  type: "draft" | "subscription";
  message_id?: number;
  subscription_id?: number;
  recipient?: string;
  subject?: string;
  kind?: string;
  schedule?: string | null;
}

export interface HiChatMessage {
  id?: number;
  role: "user" | "assistant";
  text: string;
  actions?: HiAgentAction[];
  created_at?: string;
}

export interface HiAgentHistory {
  thread_id: string;
  messages: HiChatMessage[];
}

export interface HiAgentResponse {
  reply: string;
  pending_actions: HiAgentAction[];
  tools_used: Array<{ name: string }>;
  thread_id?: string;
  messages?: HiChatMessage[];
}

export interface CommHubTasksGrouped {
  todo: CommunicationTask[];
  waiting_supplier: CommunicationTask[];
  in_progress: CommunicationTask[];
  done: CommunicationTask[];
}

export interface CommHubTaskFilters {
  supplier_id?: number;
  procurement_record_id?: number;
  supplier_po_no?: string;
}

// ─── Mail Engine ─────────────────────────────────────────────────────────────
export interface MailEngineSnapshot {
  smtp: {
    enabled: boolean;
    host: string;
    port: number;
    user: string;
    password_masked: string;
    from: string;
  };
  imap: {
    enabled: boolean;
    protocol: string;
    use_ssl: boolean;
    host: string;
    port: number;
    user: string;
    password_masked: string;
    folder: string;
  };
  auto_po_followup_enabled: boolean;
  scheduler_enabled: boolean;
}

export interface DraftRule {
  id: number;
  template_name: string;
  signal: Signal | string;
  day_no: number;
  followup_status: string | null;
  interval_hours: number | null;
  subject_template: string;
  body_template: string;
  active: boolean;
  updated_at: string | null;
}

export interface MailEngineHealth {
  ok: boolean;
  scheduler_running: boolean;
  smtp: {
    enabled?: boolean;
    ok?: boolean;
    host?: string;
    port?: number;
    authenticated?: boolean;
    error?: string;
    reason?: string;
  };
  imap: {
    enabled?: boolean;
    ok?: boolean;
    protocol?: string;
    host?: string;
    port?: number;
    folder?: string;
    mailbox_count?: number;
    error?: string;
    reason?: string;
  };
  queue: {
    pending_outbox: number;
    failed_outbox: number;
    sent_today: number;
  };
  last_error: {
    job_name: string | null;
    at: string | null;
    message: string | null;
  };
  jobs: Array<{
    job_name: string;
    enabled: boolean;
    interval_minutes: number;
    last_status: string | null;
    last_run_at: string | null;
    total_runs: number;
    failed_runs: number;
  }>;
  checked_at: string;
}

export interface CronJobRow {
  job_name: string;
  display_name: string;
  description: string | null;
  enabled: boolean;
  interval_minutes: number;
  last_run_at: string | null;
  next_run_at: string | null;
  last_status: string | null;
  last_message: string | null;
  total_runs: number;
  failed_runs: number;
}

export interface CronJobLog {
  id: number;
  job_name: string;
  started_at: string | null;
  finished_at: string | null;
  status: string;
  message: string | null;
  records_processed: number;
  records_success: number;
  records_failed: number;
  error_detail: string | null;
}

export interface CronJobRunResult {
  ok: boolean;
  status: string;
  message?: string | null;
  started_at?: string;
  finished_at?: string;
  records_processed?: number;
  records_success?: number;
  records_failed?: number;
  result?: Record<string, unknown> | null;
}

// ─── Customer Mail Inbox ─────────────────────────────────────────────────────
export interface CustomerMail {
  id: number;
  from_email: string | null;
  from_name: string | null;
  to_email: string | null;
  cc_email: string | null;
  subject: string | null;
  body: string | null;
  received_at: string | null;
  mail_type: string;
  customer_name: string | null;
  status: string;
  assigned_to: string | null;
  priority: string;
  linked_task_id: number | null;
  linked_supplier_po_no: string | null;
  message_uid: string | null;
  ai_category?: string | null;
  ai_urgency?: string | null;
  ai_action?: string | null;
  ai_summary?: string | null;
  ai_triaged_at?: string | null;
  task_count?: number;
  open_task_count?: number;
  created_at: string;
  updated_at: string;
}

export interface CustomerMailListResponse {
  total: number;
  items: CustomerMail[];
  stats: Record<string, number>;
  allowed_types: string[];
  allowed_statuses: string[];
}

export interface CustomerMailAssignPayload {
  assigned_to?: string | null;
  priority?: string | null;
  status?: string | null;
  customer_name?: string | null;
  mail_type?: string | null;
}

export interface CustomerMailTaskPayload {
  title?: string | null;
  description?: string | null;
  assigned_to?: string | null;
  priority?: string | null;
  due_date?: string | null;
}

export interface CustomerMailMetaOptions {
  types: string[];
  statuses: string[];
  priorities: string[];
}

// ─── Auth / Users ───────────────────────────────────────────────────────────
export type Role = "admin" | "manager" | "user" | "viewer";

export interface AuthUser {
  id: number;
  email: string;
  // Login id for accounts without an email (internal employees).
  username?: string | null;
  full_name: string | null;
  role: Role | "supplier" | "employee";
  is_active: boolean;
  // Supplier portal accounts carry a supplier_id (null → internal staff account).
  supplier_id?: number | null;
  // Employee portal accounts carry an emp_code (their CRM EmpCode).
  emp_code?: string | null;
  must_change_password?: boolean;
  supplier_name?: string | null;
  last_login_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: AuthUser;
}

export interface UserCreatePayload {
  email: string;
  password: string;
  full_name?: string | null;
  role?: Role;
}

export interface UserUpdatePayload {
  full_name?: string | null;
  role?: Role;
  is_active?: boolean;
}

// ─── Customer replies / outbox approvals ─────────────────────────────────────
export interface CustomerReply {
  id: number;
  direction: string;
  subject: string | null;
  body: string | null;
  status: string;
  mail_type: string | null;
  to_emails: string[];
  sent_at: string | null;
  created_at: string;
  error_message: string | null;
}

export interface CustomerDraftReply {
  subject: string;
  body: string;
  source: "ai" | "order-data" | "generic";
  supplier_po_no: string | null;
}

export interface OutboxDraft {
  id: number;
  subject: string | null;
  body: string | null;
  mail_type: string | null;
  status: string;
  supplier_name: string | null;
  supplier_po_no: string | null;
  customer_mail_id: number | null;
  to_emails: string[];
  receiver_email: string | null;
  in_reply_to: string | null;
  created_at: string;
}

// ─── AI assistant ────────────────────────────────────────────────────────────
export interface ChatMessage {
  role: "user" | "assistant" | "system";
  content: string;
}

export interface AiToolUse {
  name: string;
  args: Record<string, unknown>;
}

export interface AiChatResponse {
  reply: string;
  model: string;
  tools_used?: AiToolUse[];
}

export interface AiRagHealth {
  enabled: boolean;
  model: string;
  dim: number;
  base_url: string;
  has_key: boolean;
}

export interface AiHealth {
  enabled: boolean;
  model: string;
  base_url: string;
  has_key: boolean;
  agent_enabled?: boolean;
  triage_enabled?: boolean;
  po_followup_ai?: boolean;
  rag?: AiRagHealth;
}

// ─── AI insights (delay risk + supplier scorecards + memory) ─────────────────
export interface DelayRiskItem {
  supplier_name: string | null;
  supplier_po_no: string;
  risk_score: number;
  risk_band: "LOW" | "MEDIUM" | "HIGH" | string;
  risk_reason: string | null;
  signal: string;
  earliest_due_date: string | null;
  material_count: number;
  at_risk_materials: number;
  days_late: number | null;
}

export interface DelayRiskResponse {
  count: number;
  band: string | null;
  items: DelayRiskItem[];
}

export interface SupplierScorecard {
  supplier_name: string;
  by_signal: Record<string, number>;
  total_records: number;
  overdue: number;
  avg_followups: number;
  incoming_msgs: number;
  outgoing_msgs: number;
  high_risk: number;
  red_black: number;
  response_rate: number | null;
  score: number;
  grade: "A" | "B" | "C" | "D" | string;
}

export interface AiMemoryStats {
  embeddings: AiRagHealth | null;
  store: {
    available: boolean;
    total: number;
    by_source: Record<string, number>;
  };
  indexer_enabled: boolean;
}

export interface BlackFollowupThreadItem {
  id: number;
  direction: "INCOMING" | "OUTGOING" | string;
  status: string;
  mail_type: string | null;
  subject: string | null;
  snippet: string | null;
  parsed_status: string | null;
  at: string | null;
}

export interface BlackFollowupCommitment {
  material_name: string | null;
  commitment_date: string | null;
  supplier_status: string | null;
}

export interface BlackFollowup {
  supplier_name: string | null;
  supplier_po_no: string;
  overall_signal: string;
  material_count: number;
  earliest_due_date: string | null;
  days_late: number | null;
  latest_followup_date: string | null;
  escalation_levels: string[];
  mapping_active: boolean;
  commitment_captured: boolean;
  committed_count: number;
  commitments: BlackFollowupCommitment[];
  message_count: number;
  outgoing_count: number;
  incoming_count: number;
  thread: BlackFollowupThreadItem[];
  status_label: string;
}

export interface BlackFollowupResponse {
  count: number;
  chasing: number;
  items: BlackFollowup[];
}

export interface FollowupAttempt {
  id: number;
  created_at: string;
  supplier_po_no: string | null;
  supplier_name: string | null;
  signal: string | null;
  mail_type: string | null;
  source: string; // auto | manual | command
  outcome: string; // QUEUED | SKIPPED | FAILED
  detail: string | null;
  ai_used: boolean;
  ai_error: string | null;
  history_id: number | null;
  send_status: string | null;
  sent_at: string | null;
  send_error: string | null;
  to_emails: string[];
  cc_emails: string[];
  subject: string | null;
}

export interface FollowupHistoryResponse {
  count: number;
  items: FollowupAttempt[];
}

export interface AiPrompt {
  label: string;
  value: string;
  default: string;
  is_custom: boolean;
}
export type AiPromptsMap = Record<string, AiPrompt>;

export interface AiFeedbackInput {
  feature: string;
  rating: "up" | "down";
  instruction?: string;
  ai_output?: string;
  edited_output?: string;
  context_ref?: string;
  note?: string;
}

export interface BlackFollowupCommandResult {
  found: boolean;
  sent: boolean;
  queued?: boolean;
  subject: string;
  body: string;
  body_html?: string;
  source: string;
  mapping_active?: boolean;
  skipped_reason?: string | null;
  message_id?: number | null;
}

// ─── ASN (Advance Shipping Notice) ───────────────────────────────────────────
export type AsnStatus =
  | "DRAFT"
  | "SUBMITTED"
  | "DISPATCHED"
  | "IN_TRANSIT"
  | "AT_CUSTOMS"
  | "INBOUND_HUB"
  | "OUT_FOR_DELIVERY"
  | "DELIVERED"
  | "CANCELLED";

export type TransportMode = "SEA" | "AIR" | "ROAD" | "RAIL";

export interface AsnItem {
  id: number;
  procurement_record_id?: number | null;
  material_name: string;
  material_code?: string | null;
  po_qty?: number | null;
  qty_shipped?: number | null;
  uom?: string | null;
  invoice_no?: string | null;
}

export interface AsnEvent {
  id: number;
  stage: string;
  status_label?: string | null;
  location?: string | null;
  note?: string | null;
  lat?: number | null;
  lng?: number | null;
  source?: string | null;
  occurred_at: string;
  created_by?: string | null;
}

export interface Asn {
  id: number;
  asn_no: string;
  supplier_id: number;
  supplier_name?: string | null;
  supplier_po_no: string;
  crm_no?: string | null;
  carrier_name?: string | null;
  courier_code?: string | null;
  tracking_no?: string | null;
  transport_mode?: string | null;
  origin?: string | null;
  destination?: string | null;
  dispatch_date?: string | null;
  eta?: string | null;
  delivered_at?: string | null;
  status: AsnStatus;
  status_label?: string | null;
  alert: boolean;
  alert_reason?: string | null;
  progress_percent: number;
  remarks?: string | null;
  created_by_email?: string | null;
  created_at: string;
  updated_at: string;
  items: AsnItem[];
  events: AsnEvent[];
}

export interface AsnSummary {
  active: number;
  pending: number;
  urgent: number;
  finalized: number;
  total: number;
  drafts: number;
}

export interface AsnListResponse {
  count: number;
  items: Asn[];
}

export interface AsnItemInput {
  procurement_record_id?: number | null;
  material_name: string;
  material_code?: string | null;
  po_qty?: number | null;
  qty_shipped?: number | null;
  uom?: string | null;
  invoice_no?: string | null;
}

export interface AsnCreatePayload {
  supplier_po_no: string;
  crm_no?: string | null;
  carrier_name?: string | null;
  courier_code?: string | null;
  tracking_no?: string | null;
  transport_mode?: string | null;
  origin?: string | null;
  destination?: string | null;
  dispatch_date?: string | null;
  eta?: string | null;
  remarks?: string | null;
  items: AsnItemInput[];
  submit: boolean;
}

export interface AsnEventPayload {
  stage: string;
  location?: string | null;
  note?: string | null;
  label?: string | null;
  alert?: boolean | null;
  alert_reason?: string | null;
  occurred_at?: string | null;
}

// ─── Supplier portal ─────────────────────────────────────────────────────────
export interface PortalSummary {
  supplier_name?: string | null;
  total_pos: number;
  pending_pos: number;
  completed_pos: number;
  blocked_count: number;
  asn: AsnSummary;
}

export interface PortalPo {
  supplier_po_no: string;
  crm_no?: string | null;
  material_count: number;
  overall_signal?: string | null;
  po_status?: string | null;
  earliest_shipment_date?: string | null;
  completed: boolean;
  asn_count: number;
  message_count: number;
  unread_inbound?: number;
  escalated: boolean;
}

// ─── Employee portal (internal employee accounts, scoped to their POs) ────────
export interface EmployeeSummary {
  emp_code?: string | null;
  full_name?: string | null;
  total_pos: number;
  total_materials: number;
  green: number;
  yellow: number;
  red: number;
  black: number;
  escalated_pos: number;
  overdue_pos: number;
}

export interface EmployeePo {
  supplier_po_no: string;
  crm_no?: string | null;
  supplier_name?: string | null;
  material_count: number;
  overall_signal?: string | null;
  po_status?: string | null;
  earliest_shipment_date?: string | null;
  unread_inbound?: number;
  escalated: boolean;
}

export interface EmployeePoListResponse {
  count: number;
  items: EmployeePo[];
}

export interface EmployeePoMaterial {
  procurement_record_id: number;
  crm_no?: string | null;
  material_name: string;
  uom?: string | null;
  qty?: number | null;
  supplier_name?: string | null;
  shipment_date?: string | null;
  signal?: string | null;
  po_status?: string | null;
  rate?: number | null;
  lead_time?: number | null;
  commitment_date?: string | null;
}

export interface EmployeeCredential {
  username?: string | null;
  full_name?: string | null;
  temp_password?: string | null;
  emp_code?: string | null;
}

export interface EmployeeProvisionResult {
  ok?: boolean;
  created: EmployeeCredential[];
  reactivated: string[];
  conflicts: { username?: string; reason?: string }[];
  skipped: { row?: string; reason?: string }[];
}

export interface EmployeeCreatePayload {
  username: string;
  full_name?: string | null;
  emp_code?: string | null;
}

// ─── CRM ingestion fetch history (admin-only) ─────────────────────────────────
export interface CrmIngestLog {
  id: number;
  ran_at: string;
  status: string; // OK | ERROR | DISABLED
  trigger: string; // auto | manual
  desk?: string | null;
  fetched: number;
  generated: number;
  created: number;
  updated: number;
  skipped: number;
  errors: number;
  duration_ms?: number | null;
  message?: string | null;
}

export interface PortalMessage {
  id: number;
  direction: "INCOMING" | "OUTGOING" | string;
  mine: boolean;
  author: string;
  subject?: string | null;
  body: string;
  mail_type?: string | null;
  status: string;
  at?: string | null;
}

export interface PortalPoListResponse {
  count: number;
  items: PortalPo[];
}

export interface PortalPoMaterial {
  procurement_record_id: number;
  crm_no: string;
  material_name: string;
  uom?: string | null;
  qty?: number | null;
  po_date?: string | null;
  shipment_date?: string | null;
  signal?: string | null;
  po_status?: string | null;
  commitment_date?: string | null;
  commitment_qty?: number | null;
  commitment_status?: string | null;
  commitment_remark?: string | null;
}

export interface PortalCommitmentItem {
  procurement_record_id: number;
  commitment_date?: string | null; // YYYY-MM-DD
  commitment_qty?: number | null;
  supplier_status?: string | null;
  supplier_remark?: string | null;
}

export interface PortalTask {
  id: number;
  title: string;
  description?: string | null;
  material_name?: string | null;
  status: string;
  priority: string;
  signal?: string | null;
  progress_percent?: number;
  due_date?: string | null;
  created_at: string;
  closed_at?: string | null;
}

export interface PortalMe {
  id: number;
  email: string;
  supplier_id: number | null;
  supplier_name: string | null;
  must_change_password: boolean;
}

// ─── Admin Digest ────────────────────────────────────────────────────────────
export interface AdminDigestConfig {
  enabled: boolean;
  recipients: string[];
  send_hour: number;
  timezone: string;
  sections: Record<string, boolean>;
  limits: Record<string, number>;
  last_sent_date: string | null;
}

// ─── Notifications ───────────────────────────────────────────────────────────
export interface AppNotification {
  id: number;
  type: string;
  title: string;
  body?: string | null;
  link?: string | null;
  supplier_id?: number | null;
  supplier_po_no?: string | null;
  is_read: boolean;
  created_at: string;
}

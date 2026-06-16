export type Signal = "GREEN" | "YELLOW" | "RED" | "BLACK";

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
  po_no?: string | null; // deprecated source column, still referenced by some views

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
  created_at: string;
}

export interface TaskActivity {
  id: number;
  task_id: number;
  activity_type: string;
  old_value?: string | null;
  new_value?: string | null;
  created_by?: string | null;
  created_at: string;
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
  watchers: string[];
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
  watchers?: string[];
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
  watchers?: string[];
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
  highest_signal: string;
  health_score: number;
  mapping_status: string;
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
  signal: string;
  risk_level: string;
  messages: CommHubMessage[];
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
  full_name: string | null;
  role: Role;
  is_active: boolean;
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

export interface AiChatResponse {
  reply: string;
  model: string;
}

export interface AiHealth {
  enabled: boolean;
  model: string;
  base_url: string;
  has_key: boolean;
}

"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import api from "@/lib/api";
import { useStore } from "@/lib/store";
import TaskCreateForm from "@/components/tasks/TaskCreateForm";
import CustomerWorkspace from "@/components/customer-mails/CustomerWorkspace";
import type {
  CommHubDashboard,
  CommHubMessage,
  CommHubPO,
  CommHubSupplier,
  CommHubTasksGrouped,
  CommHubThread,
  CommunicationTask,
  CommunicationTaskCreate,
  OtherMailThread,
  PoFollowupMaterial,
  SupplierMaterialCommitment,
  TaskAssignee,
  TaskPriority,
  TaskSignal,
  TaskStatus,
  ThreadTableRow,
} from "@/lib/types";
import {
  AlertTriangle,
  Bell,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Inbox,
  Loader2,
  Mail,
  MessagesSquare,
  MoreHorizontal,
  Package,
  Plus,
  RefreshCcw,
  Search,
  Send,
  Sparkles,
  UserPlus,
  X,
} from "lucide-react";

// ─────────────────────────────────────────────────────────────────────────────
// Hub data adapter — every data dependency the Hub needs, so the same component
// can talk to the admin (/api/communication-hub/*) or the employee-scoped
// (/api/eportal/hub/*) backend. The two backends return BYTE-IDENTICAL shapes,
// so the types below are derived 1:1 from the admin api methods.
// ─────────────────────────────────────────────────────────────────────────────
export interface CommHubAdapter {
  dashboard: () => Promise<CommHubDashboard>;
  suppliers: () => Promise<CommHubSupplier[]>;
  posByName: (supplierName: string) => Promise<CommHubPO[]>;
  posById: (supplierId: number) => Promise<CommHubPO[]>;
  otherMails: typeof api.hubOtherMails;
  thread: typeof api.hubThread;
  markThreadRead: typeof api.hubMarkThreadRead;
  tasks: typeof api.hubTasks;
  createTask: typeof api.hubCreateTask;
  updateTask: typeof api.hubUpdateTask;
  aiReply: typeof api.hubAiReply;
  reply: typeof api.hubReply;
  escalate: typeof api.hubEscalate;
  agent: typeof api.hubAgent;
  agentConfirm: typeof api.hubAgentConfirm;
  sendMail: typeof api.hubSendMail;
  assignees: () => Promise<TaskAssignee[]>;
  mentionTargets: () => Promise<TaskAssignee[]>;
  commitments: (params: { supplier_po_no: string; supplier_name?: string }) => Promise<SupplierMaterialCommitment[]>;
  approveMessage: typeof api.approveMessage;
  discardMessage: typeof api.discardMessage;
}

export interface CommunicationHubProps {
  hub: CommHubAdapter;
  // Whether to expose the Suppliers/Customers toggle + CustomerWorkspace.
  showCustomers?: boolean;
}

// ─────────────────────────────────────────────────────────────────────────────
// Constants
// ─────────────────────────────────────────────────────────────────────────────

const TEMPLATES: { label: string; body: string }[] = [
  {
    label: "Professional",
    body: "Dear Team,\n\nKindly share the latest status on the referenced PO at your earliest convenience.\n\nBest regards,",
  },
  {
    label: "Reminder",
    body: "Dear Team,\n\nThis is a gentle reminder regarding the pending dispatch for the referenced PO. Please share an updated commitment.\n\nRegards,",
  },
  {
    label: "Strong Follow-up",
    body: "Dear Team,\n\nWe have not received an update on the referenced PO despite multiple follow-ups. Please confirm dispatch status today.\n\nRegards,",
  },
  {
    label: "Escalation",
    body: "Dear Team,\n\nThe delay on the referenced PO is now critical and will impact our line. We are escalating this matter to leadership.\n\nRegards,",
  },
];

const SIGNAL_DOT: Record<string, string> = {
  GREEN: "bg-emerald-500",
  YELLOW: "bg-amber-500",
  RED: "bg-signal-red",
  BLACK: "bg-ink",
};

const SIGNAL_LABEL: Record<string, string> = {
  GREEN: "On Track",
  YELLOW: "Reminder",
  RED: "Delayed",
  BLACK: "Critical",
};

const SIGNAL_CHIP: Record<string, string> = {
  GREEN: "bg-emerald-50 text-emerald-700",
  YELLOW: "bg-amber-50 text-amber-700",
  RED: "bg-red-50 text-signal-red",
  BLACK: "bg-ink text-white",
};

const STATUS_GROUPS: { key: TaskStatus; label: string }[] = [
  { key: "TODO", label: "To Do" },
  { key: "WAITING_SUPPLIER", label: "Waiting Supplier" },
  { key: "IN_PROGRESS", label: "In Progress" },
  { key: "DONE", label: "Done" },
];

const PRIORITY_CHIP: Record<TaskPriority, string> = {
  P0: "bg-red-100 text-signal-red",
  P1: "bg-orange-100 text-orange-700",
  P2: "bg-amber-100 text-amber-700",
  P3: "bg-subtle text-brand-muted",
};

type QueueFilter = "needs_reply" | "drafts" | "delayed" | "tasks" | "all";

const QUEUE_FILTERS: { key: QueueFilter; label: string; description: string }[] = [
  { key: "needs_reply", label: "Needs Reply", description: "Drafts, red flags, and open work" },
  { key: "drafts", label: "Drafts", description: "Generated mails waiting to send" },
  { key: "delayed", label: "Delayed", description: "RED and BLACK signals" },
  { key: "tasks", label: "Tasks", description: "Suppliers with open actions" },
  { key: "all", label: "All", description: "Full supplier queue" },
];

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────
function signalRank(s: string): number {
  return ({ GREEN: 0, YELLOW: 1, RED: 2, BLACK: 3 } as Record<string, number>)[s] ?? 0;
}

function relTime(value: string | null | undefined): string {
  if (!value) return "—";
  const d = new Date(value);
  if (isNaN(d.getTime())) return "—";
  const diffMs = Date.now() - d.getTime();
  const min = Math.floor(diffMs / 60000);
  if (min < 1) return "just now";
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const day = Math.floor(hr / 24);
  if (day < 30) return `${day}d ago`;
  return d.toLocaleDateString("en-IN", { day: "2-digit", month: "short" });
}

function fmtTime(value: string | null | undefined): string {
  if (!value) return "";
  const d = new Date(value);
  if (isNaN(d.getTime())) return "";
  return d.toLocaleString("en-IN", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function fmtDueDate(value: string | null | undefined): { text: string; overdue: boolean } {
  if (!value) return { text: "No due date", overdue: false };
  const d = new Date(value);
  if (isNaN(d.getTime())) return { text: value, overdue: false };
  const overdue = d.getTime() < Date.now();
  return {
    text: d.toLocaleString("en-IN", {
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    }),
    overdue,
  };
}

function truncate(s: string, n: number) {
  if (!s) return "";
  return s.length > n ? s.slice(0, n) + "…" : s;
}

function toDatetimeLocal(iso: string): string {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function numericMailId(value: number | string | null | undefined): number | null {
  return typeof value === "number" ? value : null;
}

function stripTableText(body: string | null | undefined): string {
  if (!body) return "";
  const cleaned: string[] = [];
  let skippingTableBlock = false;

  for (const line of body.split("\n")) {
    const trimmed = line.trim();
    if (/^On .+ wrote:\s*$/i.test(trimmed) || trimmed.startsWith(">") || trimmed === "-----Original Message-----") {
      break;
    }
    if (!trimmed) {
      skippingTableBlock = false;
      cleaned.push("");
      continue;
    }

    const startsTableBlock =
      /^sr\s*no\b/i.test(trimmed) ||
      /^crm\s*no\b/i.test(trimmed) ||
      trimmed.includes("\t") ||
      trimmed.includes("|");

    if (startsTableBlock) {
      if (/please reply by filling/i.test(trimmed) && trimmed.includes("|")) {
        cleaned.push(trimmed.split("|")[0].trim());
      }
      skippingTableBlock = true;
      continue;
    }

    if (skippingTableBlock) {
      continue;
    }

    if (/^[\-: ]+$/.test(trimmed)) {
      continue;
    }

    cleaned.push(line);
  }

  return cleaned
    .join("\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function fmtTableDate(value: string | null | undefined): string {
  if (!value) return "-";
  const d = new Date(value);
  if (isNaN(d.getTime())) return value;
  return d.toLocaleDateString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

function fmtTableQty(value: number | null | undefined): string {
  if (value == null || Number.isNaN(Number(value))) return "-";
  return Number(value).toLocaleString("en-IN", { maximumFractionDigits: 3 });
}

function supplierMatchesFilter(s: CommHubSupplier, filter: QueueFilter): boolean {
  const signal = (s.highest_signal || "").toUpperCase();
  if (filter === "all") return true;
  if (filter === "drafts") return s.draft_mail_count > 0;
  if (filter === "delayed") return signal === "RED" || signal === "BLACK";
  if (filter === "tasks") return s.task_count > 0;
  return s.draft_mail_count > 0 || s.task_count > 0 || signal === "RED" || signal === "BLACK";
}

function recommendedAction(signal: TaskSignal, draftCount: number, openTasks: number): string {
  if (signal === "BLACK") return "Escalate now";
  if (signal === "RED") return draftCount > 0 ? "Send strong follow-up" : "Generate HI reply";
  if (draftCount > 0) return "Review and send draft";
  if (openTasks > 0) return "Close open actions";
  if (signal === "YELLOW") return "Send reminder";
  return "Monitor";
}

function actionDescription(signal: TaskSignal, lastSubject?: string | null): string {
  if (signal === "BLACK") return "Critical PO. Create escalation pressure and keep leadership visible.";
  if (signal === "RED") return "Delayed PO. Push for a firm commitment date before this slips further.";
  if (signal === "YELLOW") return "Follow up before this becomes late.";
  return lastSubject ? `Latest thread: ${lastSubject}` : "No urgent action detected.";
}

// ─────────────────────────────────────────────────────────────────────────────
// Component
// ─────────────────────────────────────────────────────────────────────────────
export default function CommunicationHub({ hub, showCustomers = false }: CommunicationHubProps) {
  // ── API-driven state ──
  const [hubKpis, setHubKpis] = useState<CommHubDashboard | null>(null);
  const [supplierList, setSupplierList] = useState<CommHubSupplier[]>([]);
  const [poList, setPoList] = useState<CommHubPO[]>([]);
  const [thread, setThread] = useState<CommHubThread | null>(null);
  const [taskGroups, setTaskGroups] = useState<CommHubTasksGrouped | null>(null);

  // ── Selection state ──
  const [selectedSupplierName, setSelectedSupplierName] = useState<string | null>(null);
  const [selectedSupplierId, setSelectedSupplierId] = useState<number | null>(null);
  const [selectedProcurementId, setSelectedProcurementId] = useState<number | null>(null);
  // Non-PO "Other Mails": the toggle, the loaded list, and the selected thread key.
  const [showOtherMails, setShowOtherMails] = useState(false);
  const [otherMails, setOtherMails] = useState<OtherMailThread[]>([]);
  const [selectedOtherKey, setSelectedOtherKey] = useState<string | null>(null);

  // ── UI state ──
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [queueFilter, setQueueFilter] = useState<QueueFilter>("needs_reply");
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [headerMatsOpen, setHeaderMatsOpen] = useState(false);
  const [composer, setComposer] = useState("");
  const [sendAsEmail, setSendAsEmail] = useState(true);
  const [replying, setReplying] = useState(false);
  const [agentBusy, setAgentBusy] = useState(false);
  const [agentReply, setAgentReply] = useState<string | null>(null);
  const [agentActions, setAgentActions] = useState<
    Array<{ type: "draft" | "subscription"; message_id?: number; subscription_id?: number; recipient?: string; subject?: string; kind?: string; schedule?: string | null }>
  >([]);
  const [mentionList, setMentionList] = useState<TaskAssignee[]>([]);
  const [taskAssignees, setTaskAssignees] = useState<TaskAssignee[]>([]);
  const [mentionIdx, setMentionIdx] = useState(0);
  const composerRef = useRef<HTMLTextAreaElement | null>(null);
  const threadEndRef = useRef<HTMLDivElement | null>(null);
  const [assignOpen, setAssignOpen] = useState(false);
  const [assignSeed, setAssignSeed] = useState<Partial<CommunicationTaskCreate>>({});
  const [toasts, setToasts] = useState<{ id: number; tone: "ok" | "err"; msg: string }[]>([]);
  const [commitments, setCommitments] = useState<SupplierMaterialCommitment[]>([]);
  const [showMaterials, setShowMaterials] = useState(false);
  const selectPoGroup = useStore((s) => s.selectPoGroup);

  // ── @mention autocomplete (assignable users + recent customers) ──
  useEffect(() => {
    hub.mentionTargets().then(setMentionList).catch(() => setMentionList([]));
  }, [hub]);

  // Clean assignable-user directory for the Create Task pickers (kept separate
  // from mentionList, which may also include customers for @-mentions).
  useEffect(() => {
    hub.assignees().then(setTaskAssignees).catch(() => setTaskAssignees([]));
  }, [hub]);

  // Active "@query" token at the end of the composer (only while typing a /hi command).
  const mentionQuery = useMemo(() => {
    if (!/^\/hi\b/i.test(composer)) return null;
    const m = composer.match(/@([^\s@]*)$/);
    return m ? m[1] : null;
  }, [composer]);

  const mentionMatches = useMemo(() => {
    if (mentionQuery === null) return [];
    const q = mentionQuery.toLowerCase();
    return mentionList
      .filter((a) => !q || a.label.toLowerCase().includes(q) || (a.email ?? "").toLowerCase().includes(q))
      .slice(0, 6);
  }, [mentionQuery, mentionList]);

  useEffect(() => setMentionIdx(0), [mentionQuery]);

  const insertMention = useCallback((label: string) => {
    setComposer((prev) => prev.replace(/@([^\s@]*)$/, `@${label} `));
    // Refocus so the user keeps typing in the textarea.
    requestAnimationFrame(() => composerRef.current?.focus());
  }, []);

  // ── Derived ──
  const activeSupplier = supplierList.find((s) => s.supplier_name === selectedSupplierName) ?? null;
  const activePo = poList.find((p) => p.procurement_record_id === selectedProcurementId) ?? null;
  // Non-PO "Other Mails" conversation in focus (no PO selected).
  const inOther = selectedOtherKey !== null;
  const activeOther = otherMails.find((t) => t.thread_key === selectedOtherKey) ?? null;
  const otherSubject =
    activeOther?.subject ?? thread?.messages?.[0]?.subject ?? thread?.non_po_subject ?? "Other mail";
  const otherSupplierName =
    activeOther?.supplier_name ?? thread?.supplier_name ?? selectedSupplierName ?? "";
  const threadMessages: CommHubMessage[] = thread?.messages ?? [];
  const draftCount = threadMessages.filter((m) => m.sent_status === "DRAFT").length;
  const sentCount = threadMessages.filter((m) => m.sent_status !== "DRAFT").length;
  const threadSignal = (thread?.signal ?? activePo?.signal ?? "GREEN") as TaskSignal;

  // Jump to the latest message whenever the thread loads/changes.
  useEffect(() => {
    if (threadMessages.length) threadEndRef.current?.scrollIntoView({ block: "end" });
  }, [thread, threadMessages.length]);
  const lastMessage = threadMessages[threadMessages.length - 1] ?? null;
  const lastMessageId = numericMailId(lastMessage?.id);

  const contextTasks = useMemo((): CommunicationTask[] => {
    if (!taskGroups) return [];
    return [
      ...(taskGroups.todo || []),
      ...(taskGroups.waiting_supplier || []),
      ...(taskGroups.in_progress || []),
      ...(taskGroups.done || []),
    ];
  }, [taskGroups]);

  const kpis = {
    drafts: hubKpis?.draft_mails ?? 0,
    waiting: hubKpis?.waiting_supplier ?? 0,
    delayed: hubKpis?.delayed_pos ?? 0,
    openTasks: hubKpis?.open_tasks ?? 0,
  };

  // ── Toast helper ──
  const pushToast = useCallback((tone: "ok" | "err", msg: string) => {
    const id = Date.now() + Math.random();
    setToasts((prev) => [...prev, { id, tone, msg }]);
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 3000);
  }, []);

  // ── Search filter (supplier name + last subject) ──
  const filteredSuppliers = useMemo(() => {
    const q = search.trim().toLowerCase();
    return supplierList
      .filter((s) => supplierMatchesFilter(s, queueFilter))
      .filter(
        (s) =>
          !q ||
          s.supplier_name.toLowerCase().includes(q) ||
          (s.last_subject || "").toLowerCase().includes(q),
      )
      .sort((a, b) => {
        // Unread (new) suppliers always float to the top.
        const aUnread = (a.unread_inbound || 0) > 0 ? 1 : 0;
        const bUnread = (b.unread_inbound || 0) > 0 ? 1 : 0;
        if (aUnread !== bUnread) return bUnread - aUnread;
        const priority =
          signalRank((b.highest_signal || "GREEN").toUpperCase()) -
          signalRank((a.highest_signal || "GREEN").toUpperCase());
        if (priority !== 0) return priority;
        if (b.draft_mail_count !== a.draft_mail_count) return b.draft_mail_count - a.draft_mail_count;
        if (b.task_count !== a.task_count) return b.task_count - a.task_count;
        return new Date(b.last_activity_at || 0).getTime() - new Date(a.last_activity_at || 0).getTime();
      });
  }, [supplierList, search, queueFilter]);

  // ── Data loaders ──
  const loadKpis = useCallback(async () => {
    try {
      setHubKpis(await hub.dashboard());
    } catch {}
  }, [hub]);

  const loadTasks = useCallback(
    async (opts: { supplier_id?: number | null; procurement_record_id?: number | null }) => {
      try {
        const params: Record<string, number> = {};
        if (opts.procurement_record_id != null) params.procurement_record_id = opts.procurement_record_id;
        else if (opts.supplier_id != null) params.supplier_id = opts.supplier_id;
        setTaskGroups(await hub.tasks(params));
      } catch {}
    },
    [hub],
  );

  const loadThread = useCallback(async (procurementRecordId: number) => {
    try {
      setThread(await hub.thread({ procurement_record_id: procurementRecordId }));
    } catch {}
  }, [hub]);

  const loadCommitments = useCallback(
    async (supplierName: string, supplierPoNo: string) => {
      try {
        const rows = await hub.commitments({
          supplier_name: supplierName,
          supplier_po_no: supplierPoNo,
        });
        setCommitments(rows);
      } catch {
        setCommitments([]);
      }
    },
    [hub],
  );

  const loadPos = useCallback(
    async (supplierName: string, supplierId: number | null): Promise<CommHubPO[]> => {
      const pos = supplierId != null
        ? await hub.posById(supplierId)
        : await hub.posByName(supplierName);
      setPoList(pos);
      return pos;
    },
    [hub],
  );

  const loadOtherMails = useCallback(
    async (supplierName: string | null, supplierId: number | null) => {
      if (!supplierName && supplierId == null) {
        setOtherMails([]);
        return;
      }
      try {
        setOtherMails(
          await hub.otherMails({ supplier_id: supplierId, supplier_name: supplierName }),
        );
      } catch {
        setOtherMails([]);
      }
    },
    [hub],
  );

  // ── Select a non-PO "Other Mails" thread ──
  const handleSelectOther = useCallback(
    async (t: OtherMailThread) => {
      if (t.thread_key === selectedOtherKey) return;
      setSelectedProcurementId(null);
      setSelectedOtherKey(t.thread_key);
      setThread(null);
      setTaskGroups(null);
      setCommitments([]);
      setDetailsOpen(false);
      setHeaderMatsOpen(false);
      const params = {
        supplier_id: t.supplier_id ?? selectedSupplierId,
        supplier_name: t.supplier_name ?? selectedSupplierName,
        non_po_subject: t.thread_key,
      };
      try {
        setThread(await hub.thread(params));
        // Clear the unread badge for this non-PO thread, then refresh the list
        // + supplier rail so the counters update.
        try {
          await hub.markThreadRead(params);
          await loadOtherMails(selectedSupplierName, selectedSupplierId);
          setSupplierList(await hub.suppliers());
        } catch {
          /* non-fatal */
        }
      } catch {
        /* non-fatal */
      }
    },
    [selectedOtherKey, selectedSupplierId, selectedSupplierName, hub, loadOtherMails],
  );

  // ── Select supplier ──
  const handleSelectSupplier = useCallback(
    async (supplierName: string, supplierId: number | null) => {
      if (supplierName === selectedSupplierName) return;
      setSelectedSupplierName(supplierName);
      setSelectedSupplierId(supplierId);
      setSelectedProcurementId(null);
      setSelectedOtherKey(null);
      setOtherMails([]);
      setPoList([]);
      setThread(null);
      setTaskGroups(null);
      try {
        const pos = await loadPos(supplierName, supplierId);
        if (pos.length > 0) {
          const first = pos[0];
          setSelectedProcurementId(first.procurement_record_id);
          await Promise.all([
            loadThread(first.procurement_record_id),
            loadTasks({ procurement_record_id: first.procurement_record_id }),
            loadCommitments(first.supplier_name, first.supplier_po_no),
          ]);
        } else {
          await loadTasks({ supplier_id: supplierId });
        }
      } catch {}
    },
    [selectedSupplierName, loadPos, loadThread, loadTasks, loadCommitments],
  );

  // ── Select PO ──
  const handleSelectPo = useCallback(
    async (procurementRecordId: number, supplierName?: string, supplierPoNo?: string) => {
      if (procurementRecordId === selectedProcurementId) return;
      setSelectedProcurementId(procurementRecordId);
      setSelectedOtherKey(null);
      setThread(null);
      setCommitments([]);
      try {
        await Promise.all([
          loadThread(procurementRecordId),
          loadTasks({ procurement_record_id: procurementRecordId }),
          supplierName && supplierPoNo
            ? loadCommitments(supplierName, supplierPoNo)
            : Promise.resolve(),
        ]);
        // Clear WhatsApp-style unread badge for this PO and refresh the PO list
        // so the counter disappears in the sidebar.
        if (supplierPoNo) {
          try {
            await hub.markThreadRead({
              supplier_po_no: supplierPoNo,
              procurement_record_id: procurementRecordId,
            });
            if (selectedSupplierName) {
              await loadPos(selectedSupplierName, selectedSupplierId);
            }
            // Refresh the supplier list so its unread dot/badge clears too.
            try {
              setSupplierList(await hub.suppliers());
            } catch {
              /* non-fatal */
            }
          } catch {
            /* non-fatal */
          }
        }
      } catch {}
    },
    [
      selectedProcurementId,
      loadThread,
      loadTasks,
      loadCommitments,
      loadPos,
      selectedSupplierName,
      selectedSupplierId,
      hub,
    ],
  );

  // ── Full refresh ──
  const loadAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      await loadKpis();
      const suppliers = await hub.suppliers();
      setSupplierList(suppliers);
      if (suppliers.length > 0) {
        const first = suppliers[0];
        setSelectedSupplierName(first.supplier_name);
        setSelectedSupplierId(first.supplier_id);
        const pos = await loadPos(first.supplier_name, first.supplier_id);
        if (pos.length > 0) {
          const firstPo = pos[0];
          setSelectedProcurementId(firstPo.procurement_record_id);
          await Promise.all([
            loadThread(firstPo.procurement_record_id),
            loadTasks({ procurement_record_id: firstPo.procurement_record_id }),
            loadCommitments(firstPo.supplier_name, firstPo.supplier_po_no),
          ]);
        } else {
          await loadTasks({ supplier_id: first.supplier_id });
        }
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Unable to load communication data. Retry.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [loadKpis, loadPos, loadThread, loadTasks, loadCommitments, hub]);

  // Suppliers (PO threads) vs Customers (customer inbox) — one Hub, two sources.
  // Customers are only available when the consuming surface enables them.
  const [source, setSource] = useState<"suppliers" | "customers">("suppliers");
  useEffect(() => {
    if (showCustomers && new URLSearchParams(window.location.search).get("source") === "customers") {
      setSource("customers");
    }
  }, [showCustomers]);

  useEffect(() => {
    if (source === "suppliers") void loadAll();
  }, [loadAll, source]);

  // Lazy-load the active supplier's non-PO "Other Mails" when the toggle is on.
  useEffect(() => {
    if (source === "suppliers" && showOtherMails && selectedSupplierName) {
      void loadOtherMails(selectedSupplierName, selectedSupplierId);
    }
  }, [source, showOtherMails, selectedSupplierName, selectedSupplierId, loadOtherMails]);

  useEffect(() => {
    const handleMailHistoryUpdated = () => {
      void (async () => {
        await loadKpis();
        if (selectedSupplierName) {
          await loadPos(selectedSupplierName, selectedSupplierId);
        }
        if (selectedProcurementId != null) {
          await Promise.all([
            loadThread(selectedProcurementId),
            loadTasks({ procurement_record_id: selectedProcurementId }),
            activePo?.supplier_po_no
              ? loadCommitments(activePo.supplier_name, activePo.supplier_po_no)
              : Promise.resolve(),
          ]);
        } else if (selectedSupplierId != null) {
          await loadTasks({ supplier_id: selectedSupplierId });
        }
      })();
    };

    window.addEventListener("mail-history-updated", handleMailHistoryUpdated);
    return () => {
      window.removeEventListener("mail-history-updated", handleMailHistoryUpdated);
    };
  }, [
    activePo?.supplier_name,
    activePo?.supplier_po_no,
    loadCommitments,
    loadKpis,
    loadPos,
    loadTasks,
    loadThread,
    selectedProcurementId,
    selectedSupplierId,
    selectedSupplierName,
  ]);

  // ── Actions ──
  const openAssign = (seed: Partial<CommunicationTaskCreate>) => {
    setAssignSeed(seed);
    setAssignOpen(true);
  };

  const handleCreateTask = async (payload: CommunicationTaskCreate) => {
    try {
      const created = await hub.createTask(payload);
      pushToast("ok", `Task assigned to ${created.assigned_to ?? "—"}`);
      setAssignOpen(false);
      if (selectedProcurementId != null) {
        await loadTasks({ procurement_record_id: selectedProcurementId });
      } else if (selectedSupplierId != null) {
        await loadTasks({ supplier_id: selectedSupplierId });
      }
      await loadKpis();
    } catch (e: unknown) {
      pushToast("err", e instanceof Error ? e.message : "Failed to create task");
    }
  };

  const handleToggleDone = async (task: CommunicationTask) => {
    try {
      const next: TaskStatus = task.status === "DONE" ? "TODO" : "DONE";
      await hub.updateTask(task.id, { status: next });
      if (selectedProcurementId != null) {
        await loadTasks({ procurement_record_id: selectedProcurementId });
      } else if (selectedSupplierId != null) {
        await loadTasks({ supplier_id: selectedSupplierId });
      }
      pushToast("ok", next === "DONE" ? "Task closed" : "Task reopened");
    } catch (e: unknown) {
      pushToast("err", e instanceof Error ? e.message : "Failed to update task");
    }
  };

  const handleEscalate = async () => {
    if (!activePo) return;
    try {
      await hub.escalate(activePo.procurement_record_id);
      pushToast("ok", "Escalation triggered. Draft mail + task created.");
      await Promise.all([
        loadThread(activePo.procurement_record_id),
        loadTasks({ procurement_record_id: activePo.procurement_record_id }),
        loadKpis(),
      ]);
    } catch (e: unknown) {
      pushToast("err", e instanceof Error ? e.message : "Escalation failed");
    }
  };

  const handleSendMailNow = async () => {
    if (!activePo) return;
    const targetId = lastMessageId;
    if (!targetId) {
      pushToast("err", "No mail draft available to send.");
      return;
    }
    try {
      const result = await hub.sendMail(targetId);
      const sendResult = result?.send_result || {};
      const enabled = sendResult.enabled !== false;
      if (!enabled) {
        pushToast("err", `SMTP disabled: ${sendResult.reason || "check settings"}`);
      } else {
        const summary = sendResult.results?.[0] || {};
        const status = summary.status || "QUEUED";
        pushToast(
          status === "SENT" ? "ok" : "err",
          status === "SENT"
            ? "Mail dispatched via SMTP."
            : `Mail status: ${status}${summary.error ? ` — ${summary.error}` : ""}`,
        );
      }
      await Promise.all([
        loadThread(activePo.procurement_record_id),
        loadKpis(),
      ]);
    } catch (e: unknown) {
      pushToast("err", e instanceof Error ? e.message : "Send mail failed");
    }
  };

  const handleAiReply = async () => {
    if (!activePo) return;
    try {
      const result = await hub.aiReply(activePo.procurement_record_id);
      setComposer(result.body);
      pushToast("ok", "HI reply generated");
    } catch (e: unknown) {
      pushToast("err", e instanceof Error ? e.message : "HI reply failed");
    }
  };

  const handleAgent = async (message: string) => {
    if (!activePo || agentBusy) return;
    setAgentBusy(true);
    setAgentReply(null);
    setAgentActions([]);
    try {
      const res = await hub.agent({
        message,
        supplier_id: activePo.supplier_id,
        procurement_record_id: activePo.procurement_record_id,
        supplier_po_no: activePo.supplier_po_no,
      });
      setAgentReply(res.reply || "(no response)");
      setAgentActions(res.pending_actions ?? []);
      setComposer("");
    } catch (e: unknown) {
      setAgentReply(e instanceof Error ? e.message : "HI agent could not respond.");
    } finally {
      setAgentBusy(false);
    }
  };

  const handleSendReply = async () => {
    const text = composer.trim();
    if (!text || replying) return;
    if (!activePo && !inOther) return;

    // Non-PO "Other Mails" reply — threads under the supplier's no-PO conversation.
    if (inOther) {
      if (/^\/hi\b/i.test(text)) {
        pushToast("err", "The HI agent isn't available on non-PO mails yet.");
        return;
      }
      if (!selectedOtherKey) return;
      const params = {
        supplier_id: thread?.supplier_id ?? selectedSupplierId,
        supplier_name: thread?.supplier_name ?? selectedSupplierName,
        non_po_subject: selectedOtherKey,
      };
      setReplying(true);
      try {
        const res = await hub.reply({ ...params, body: text, send_email: sendAsEmail });
        setComposer("");
        if (res.no_email_on_file) {
          pushToast("ok", "Saved (no email on file — add one in Email Master)");
        } else if (res.channel === "email") {
          pushToast("ok", res.sent ? "Sent by email" : "Queued for email");
        } else {
          pushToast("ok", "Saved");
        }
        try {
          setThread(await hub.thread(params));
        } catch {
          /* non-fatal */
        }
      } catch (e: unknown) {
        pushToast("err", e instanceof Error ? e.message : "Send failed");
      } finally {
        setReplying(false);
      }
      return;
    }

    if (!activePo) return;
    // /hi → route to the HI agent instead of posting a supplier message.
    if (/^\/hi\b/i.test(text)) {
      const message = text.replace(/^\/hi\b/i, "").trim() || "help";
      await handleAgent(message);
      return;
    }
    setReplying(true);
    try {
      const res = await hub.reply({
        procurement_record_id: activePo.procurement_record_id,
        supplier_po_no: activePo.supplier_po_no,
        supplier_id: activePo.supplier_id,
        supplier_name: activePo.supplier_name,
        body: text,
        send_email: sendAsEmail,
      });
      setComposer("");
      if (res.no_email_on_file) {
        pushToast("ok", "Posted to supplier portal (no email on file — add one in Email Master)");
      } else if (res.channel === "email") {
        pushToast("ok", res.sent ? "Sent by email + portal" : "Queued for email + posted to portal");
      } else {
        pushToast("ok", "Posted to supplier portal");
      }
      await loadThread(activePo.procurement_record_id);
    } catch (e: unknown) {
      pushToast("err", e instanceof Error ? e.message : "Send failed");
    } finally {
      setReplying(false);
    }
  };

  const onPoMail = () => {
    if (!activePo) return;
    selectPoGroup({ supplier_name: activePo.supplier_name, supplier_po_no: activePo.supplier_po_no });
  };

  const seedAssign = () =>
    openAssign({
      supplier_name: activeSupplier?.supplier_name ?? null,
      supplier_po_no: activePo?.supplier_po_no ?? null,
      procurement_record_id: activePo?.procurement_record_id ?? null,
      linked_mail_id: lastMessageId,
    });

  const seedReminder = () => {
    if (!activePo || !activeSupplier) return seedAssign();
    openAssign({
      title: `Reminder: PO ${activePo.supplier_po_no}`,
      supplier_name: activeSupplier.supplier_name,
      supplier_po_no: activePo.supplier_po_no,
      procurement_record_id: activePo.procurement_record_id,
      linked_mail_id: lastMessageId,
      task_source: "SUPPLIER",
      reminder_at: new Date(Date.now() + 86400000).toISOString(),
    });
  };

  const noPo = !activePo || !activeSupplier;

  const sourceToggle = showCustomers ? (
    <div className="inline-flex shrink-0 rounded-lg border border-brand-border bg-subtle p-0.5 text-xs font-semibold">
      <button
        onClick={() => setSource("suppliers")}
        className={`rounded-md px-3 py-1.5 transition ${source === "suppliers" ? "bg-card text-signal-red shadow-sm" : "text-brand-muted hover:text-brand-dark"}`}
      >
        Suppliers
      </button>
      <button
        onClick={() => setSource("customers")}
        className={`rounded-md px-3 py-1.5 transition ${source === "customers" ? "bg-card text-signal-red shadow-sm" : "text-brand-muted hover:text-brand-dark"}`}
      >
        Customers
      </button>
    </div>
  ) : null;

  if (showCustomers && source === "customers") {
    return (
      <div>
        <div className="mb-3">{sourceToggle}</div>
        <CustomerWorkspace />
      </div>
    );
  }

  return (
    <div className="-m-5 flex h-[calc(100vh-65px)] flex-col bg-brand-surface sm:-m-6 lg:-m-8">
      {/* ── Header ───────────────────────────────────────────────────────── */}
      <header className="flex flex-wrap items-center gap-3 border-b border-brand-border bg-card px-6 py-3">
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-red-50 text-signal-red">
          <MessagesSquare size={17} />
        </span>
        <div className="min-w-0">
          <h1 className="truncate text-base font-semibold text-brand-dark">Communication Hub</h1>
          <p className="hidden text-xs text-brand-muted sm:block">
            Triage replies, PO risk and next actions in one place.
          </p>
        </div>

        {sourceToggle}

        <div className="relative ml-auto w-full min-w-[200px] max-w-sm flex-1">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-brand-muted" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search supplier or subject…"
            className="input h-9 pl-9"
          />
        </div>
        <button onClick={loadAll} className="btn-outline h-9" disabled={loading}>
          {loading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCcw size={14} />}
          <span className="hidden sm:inline">Refresh</span>
        </button>
        <button className="btn-primary h-9" onClick={seedAssign}>
          <Plus size={14} />
          <span className="hidden sm:inline">Compose Task</span>
        </button>
      </header>

      {/* ── Filter tabs (slim) ───────────────────────────────────────────── */}
      <div className="flex items-center gap-1 overflow-x-auto border-b border-brand-border bg-card px-6 py-2">
        {QUEUE_FILTERS.map((f) => {
          const count =
            f.key === "drafts"
              ? kpis.drafts
              : f.key === "delayed"
                ? kpis.delayed
                : f.key === "tasks"
                  ? kpis.openTasks
                  : f.key === "all"
                    ? supplierList.length
                    : kpis.drafts + kpis.delayed + kpis.openTasks;
          const active = queueFilter === f.key;
          return (
            <button
              key={f.key}
              onClick={() => setQueueFilter(f.key)}
              title={f.description}
              className={`inline-flex shrink-0 items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold transition ${
                active
                  ? "bg-red-50 text-signal-red ring-1 ring-signal-red/30"
                  : "text-brand-muted hover:bg-subtle"
              }`}
            >
              {f.label}
              <span
                className={`rounded-full px-1.5 text-[10px] font-bold ${
                  active ? "bg-signal-red text-white" : "bg-subtle text-brand-muted"
                }`}
              >
                {count}
              </span>
            </button>
          );
        })}
      </div>

      {error && (
        <div className="mx-6 mt-3 rounded-md border border-red-100 bg-red-50 px-3 py-2 text-sm text-signal-red">
          {error}
        </div>
      )}

      {/* ── Workspace ────────────────────────────────────────────────────── */}
      <div className="flex flex-1 gap-4 overflow-hidden p-4">
        {/* LEFT — conversation list */}
        <aside className="flex w-[340px] min-w-[300px] shrink-0 flex-col overflow-hidden rounded-xl border border-brand-border bg-card shadow-sm">
          <div className="flex items-center justify-between px-4 py-2.5">
            <span className="text-xs font-semibold uppercase tracking-wide text-brand-muted">Suppliers</span>
            <span className="text-[11px] text-brand-muted">{filteredSuppliers.length}</span>
          </div>

          <div className="max-h-[44%] overflow-y-auto border-y border-brand-border">
            {loading && supplierList.length === 0 ? (
              <EmptyState icon={<Loader2 className="animate-spin" size={18} />}>Loading…</EmptyState>
            ) : filteredSuppliers.length === 0 ? (
              <EmptyState icon={<Inbox size={20} />}>Nothing in this queue.</EmptyState>
            ) : (
              filteredSuppliers.map((s) => (
                <SupplierRow
                  key={s.supplier_name}
                  s={s}
                  active={s.supplier_name === selectedSupplierName}
                  onClick={() => void handleSelectSupplier(s.supplier_name, s.supplier_id)}
                />
              ))
            )}
          </div>

          <div className="flex items-center justify-between gap-2 px-4 py-2.5">
            <div className="min-w-0">
              <div className="text-xs font-semibold uppercase tracking-wide text-brand-muted">Purchase Orders</div>
              <div className="truncate text-[11px] text-brand-muted">
                {activeSupplier ? activeSupplier.supplier_name : "Select a supplier"}
              </div>
            </div>
            {activeSupplier && (
              <div className="flex shrink-0 items-center gap-1.5">
                <span className="rounded-full bg-subtle px-2 py-0.5 text-[10px] font-semibold text-brand-muted">
                  {poList.length}
                </span>
                {/* Toggle: reveal incoming supplier mails that have no PO number. */}
                <button
                  onClick={() => setShowOtherMails((v) => !v)}
                  title="Show mails with no PO number"
                  className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[10px] font-semibold transition ${
                    showOtherMails
                      ? "border-signal-red/30 bg-red-50 text-signal-red"
                      : "border-brand-border text-brand-muted hover:bg-subtle"
                  }`}
                >
                  Other
                  {(activeSupplier.non_po_count ?? 0) > 0 && (
                    <span className="rounded-full bg-signal-red px-1.5 text-[9px] font-bold leading-4 text-white">
                      {activeSupplier.non_po_count}
                    </span>
                  )}
                  <ChevronRight size={11} className={`transition-transform ${showOtherMails ? "rotate-90" : ""}`} />
                </button>
              </div>
            )}
          </div>

          <div className="flex-1 overflow-y-auto border-t border-brand-border">
            {!activeSupplier ? (
              <EmptyState icon={<Inbox size={18} />}>Pick a supplier to see its POs.</EmptyState>
            ) : (
              <>
                {poList.length === 0 && !loading ? (
                  <EmptyState icon={<Inbox size={18} />}>No POs for this supplier.</EmptyState>
                ) : (
                  poList.map((p) => (
                    <PoRow
                      key={p.procurement_record_id}
                      p={p}
                      active={p.procurement_record_id === selectedProcurementId && !inOther}
                      onClick={() => void handleSelectPo(p.procurement_record_id, p.supplier_name, p.supplier_po_no)}
                    />
                  ))
                )}

                {showOtherMails && (
                  <div className="border-t border-brand-border">
                    <div className="flex items-center justify-between px-4 py-2">
                      <span className="text-[11px] font-semibold uppercase tracking-wide text-brand-muted">
                        Other Mails <span className="font-normal normal-case">(no PO)</span>
                      </span>
                      <span className="rounded-full bg-subtle px-2 py-0.5 text-[10px] font-semibold text-brand-muted">
                        {otherMails.length}
                      </span>
                    </div>
                    {otherMails.length === 0 ? (
                      <div className="px-4 pb-3 text-[11px] text-brand-muted">
                        No mails without a PO for this supplier.
                      </div>
                    ) : (
                      otherMails.map((t) => (
                        <OtherMailRow
                          key={t.thread_key}
                          t={t}
                          active={t.thread_key === selectedOtherKey}
                          onClick={() => void handleSelectOther(t)}
                        />
                      ))
                    )}
                  </div>
                )}
              </>
            )}
          </div>
        </aside>

        {/* CENTER — conversation */}
        <main className="flex min-w-0 flex-1 flex-col overflow-hidden rounded-xl border border-brand-border bg-card shadow-sm">
          {(activePo && activeSupplier) || (inOther && thread) ? (
            <>
              {/* Clean single-line thread header */}
              {activePo && activeSupplier ? (
                <div className="flex items-center gap-2 border-b border-brand-border px-5 py-3">
                  <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${SIGNAL_DOT[threadSignal] ?? "bg-subtle"}`} />
                  <h2 className="truncate font-semibold text-brand-dark">
                    PO #{activePo.supplier_po_no}
                    <span className="ml-2 font-normal text-brand-muted">{activeSupplier.supplier_name}</span>
                  </h2>
                  <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold uppercase ${SIGNAL_CHIP[threadSignal] ?? ""}`}>
                    {SIGNAL_LABEL[threadSignal] ?? threadSignal}
                  </span>
                  <span className="ml-2 hidden text-xs text-brand-muted md:inline">
                    {threadMessages.length} message{threadMessages.length === 1 ? "" : "s"}
                  </span>

                  <div className="ml-auto flex items-center gap-1">
                    <button
                      onClick={() => setHeaderMatsOpen((v) => !v)}
                      className={`inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-xs font-medium ${
                        headerMatsOpen
                          ? "border-brand-dark/20 bg-subtle text-brand-dark"
                          : "border-brand-border text-brand-dark hover:bg-subtle"
                      }`}
                      title="Materials & committed dates"
                    >
                      <Package size={13} /> Materials
                      <ChevronDown size={12} className={`transition-transform ${headerMatsOpen ? "rotate-180" : ""}`} />
                    </button>
                    <button
                      onClick={() => setDetailsOpen((v) => !v)}
                      className={`inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-xs font-medium ${
                        detailsOpen
                          ? "border-signal-red/30 bg-red-50 text-signal-red"
                          : "border-brand-border text-brand-dark hover:bg-subtle"
                      }`}
                    >
                      <Sparkles size={13} /> Details
                    </button>
                    <button
                      onClick={seedAssign}
                      className="p-1.5 text-brand-muted hover:text-brand-dark"
                      title="More"
                    >
                      <MoreHorizontal size={18} />
                    </button>
                  </div>
                </div>
              ) : (
                /* Non-PO "Other Mails" header — no PO chrome (materials / details / tasks). */
                <div className="flex items-center gap-2 border-b border-brand-border px-5 py-3">
                  <Mail size={16} className="shrink-0 text-brand-muted" />
                  <h2 className="truncate font-semibold text-brand-dark">
                    {otherSubject}
                    {otherSupplierName && (
                      <span className="ml-2 font-normal text-brand-muted">{otherSupplierName}</span>
                    )}
                  </h2>
                  <span className="rounded bg-subtle px-1.5 py-0.5 text-[10px] font-bold uppercase text-brand-muted">
                    No PO
                  </span>
                  <span className="ml-2 hidden text-xs text-brand-muted md:inline">
                    {threadMessages.length} message{threadMessages.length === 1 ? "" : "s"}
                  </span>
                </div>
              )}

              {/* Materials & committed dates — quick dropdown from the header */}
              {headerMatsOpen && activePo && (
                <div className="border-b border-brand-border bg-subtle/70 px-5 py-3">
                  <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-brand-muted">
                    Materials &amp; committed dates
                  </div>
                  {(activePo.materials?.length ?? 0) === 0 ? (
                    <div className="text-xs text-brand-muted">No materials on this PO.</div>
                  ) : (
                    <div className="overflow-x-auto rounded border border-brand-border bg-card">
                      <table className="min-w-full text-left text-xs">
                        <thead className="bg-subtle">
                          <tr className="text-[10px] uppercase tracking-wide text-brand-muted">
                            <th className="px-3 py-1.5 font-semibold">Material</th>
                            <th className="px-3 py-1.5 font-semibold">Committed date</th>
                          </tr>
                        </thead>
                        <tbody>
                          {(activePo.materials ?? []).map((m: PoFollowupMaterial) => {
                            const commit =
                              commitments.find(
                                (c) => c.material_name?.toUpperCase() === m.material_name?.toUpperCase(),
                              ) ?? m.commitment ?? null;
                            return (
                              <tr key={m.procurement_record_id} className="border-t border-brand-border">
                                <td className="px-3 py-1.5 text-brand-dark" title={m.material_name}>
                                  {m.material_name}
                                </td>
                                <td className="px-3 py-1.5 text-brand-dark">
                                  {commit?.commitment_date ? (
                                    fmtTableDate(commit.commitment_date)
                                  ) : (
                                    <span className="text-brand-muted">Awaiting supplier</span>
                                  )}
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              )}

              {/* Thread — generous breathing room */}
              <div className="flex-1 space-y-6 overflow-y-auto px-6 py-6 lg:px-10">
                {threadMessages.length === 0 ? (
                  <EmptyState icon={<MessagesSquare size={22} />}>
                    {inOther ? "No messages in this thread yet." : "No emails for this PO yet."}
                  </EmptyState>
                ) : (
                  threadMessages.map((m) => (
                    <MailBubble
                      key={String(m.id)}
                      mail={m}
                      onAssign={
                        activePo && activeSupplier
                          ? () =>
                              openAssign({
                                title: `Follow-up: ${m.subject}`,
                                supplier_name: activeSupplier.supplier_name,
                                supplier_po_no: activePo.supplier_po_no,
                                procurement_record_id: activePo.procurement_record_id,
                                linked_mail_id: numericMailId(m.id),
                              })
                          : () => {}
                      }
                    />
                  ))
                )}
                <div ref={threadEndRef} />
              </div>

              {/* Composer — minimal */}
              <div className="border-t border-brand-border px-5 py-3">
                {/* HI agent response + confirm cards */}
                {(agentReply || agentBusy) && (
                  <div className="mb-2 rounded-lg border border-signal-red/30 bg-red-50/70 p-3 text-sm">
                    <div className="mb-1 flex items-center gap-1.5 font-semibold text-signal-red">
                      <Sparkles size={13} /> HI agent
                      <button
                        className="ml-auto text-[11px] font-normal text-brand-muted hover:text-brand-dark"
                        onClick={() => { setAgentReply(null); setAgentActions([]); }}
                      >
                        dismiss
                      </button>
                    </div>
                    {agentBusy ? (
                      <div className="text-brand-muted">Thinking…</div>
                    ) : (
                      <div className="whitespace-pre-wrap text-brand-dark">{agentReply}</div>
                    )}
                    {agentActions.map((a, i) => (
                      <div key={i} className="mt-2 flex items-center justify-between gap-2 rounded border border-brand-border bg-card p-2">
                        <span className="min-w-0 truncate text-brand-dark">
                          {a.type === "draft"
                            ? `✉️ Email${a.recipient ? ` to ${a.recipient}` : ""}${a.subject ? `: ${a.subject}` : ""}`
                            : `🔔 ${a.kind === "SCHEDULED_SUMMARY" ? "Scheduled summary" : "Followup"}${a.recipient ? ` for ${a.recipient}` : ""}${a.schedule ? ` (${a.schedule})` : ""}`}
                        </span>
                        <span className="flex shrink-0 gap-1.5">
                          <button
                            className="rounded-md bg-signal-red px-3 py-1 text-xs font-semibold text-white hover:opacity-90"
                            onClick={async () => {
                              try {
                                await hub.agentConfirm({ action_type: a.type, id: (a.message_id ?? a.subscription_id) as number });
                                pushToast("ok", a.type === "draft" ? "Sent" : "Confirmed");
                                setAgentActions((prev) => prev.filter((_, j) => j !== i));
                                if (activePo) await loadThread(activePo.procurement_record_id);
                              } catch (e: unknown) {
                                pushToast("err", e instanceof Error ? e.message : "Confirm failed");
                              }
                            }}
                          >
                            {a.type === "draft" ? "Send" : "Confirm"}
                          </button>
                          <button
                            className="rounded-md border border-brand-border px-3 py-1 text-xs text-brand-muted hover:bg-subtle"
                            onClick={() => setAgentActions((prev) => prev.filter((_, j) => j !== i))}
                          >
                            Cancel
                          </button>
                        </span>
                      </div>
                    ))}
                  </div>
                )}
                {/* /hi command hint */}
                {/^\/hi\b/i.test(composer) && (
                  <div className="mb-2 rounded-lg border border-signal-red/20 bg-card p-2 text-[11px] text-brand-muted">
                    <span className="font-semibold text-signal-red">HI agent</span> — try:{" "}
                    {[
                      "summarise this",
                      "send a summary to @username",
                      "give followup to @username",
                      "schedule a daily summary to @username",
                      "what's pending here",
                    ].map((ex) => (
                      <button
                        key={ex}
                        onClick={() => setComposer(`/hi ${ex}`)}
                        className="mr-1 mb-1 inline-block rounded-full border border-brand-border px-2 py-0.5 hover:bg-red-50 hover:text-signal-red"
                      >
                        {ex}
                      </button>
                    ))}
                  </div>
                )}
                <div className="mb-2 flex flex-wrap items-center gap-1.5">
                  <span className="text-[10px] font-semibold uppercase tracking-wide text-brand-muted">Templates</span>
                  {TEMPLATES.map((t) => (
                    <button
                      key={t.label}
                      onClick={() => setComposer(t.body)}
                      className="rounded-full border border-brand-border px-2.5 py-0.5 text-[11px] font-medium text-brand-muted hover:bg-subtle hover:text-brand-dark"
                    >
                      {t.label}
                    </button>
                  ))}
                </div>
                <div className="relative">
                  {/* @mention autocomplete dropdown (above the textarea) */}
                  {mentionQuery !== null && mentionMatches.length > 0 && (
                    <div className="absolute bottom-full left-0 z-20 mb-1 w-72 overflow-hidden rounded-lg border border-brand-border bg-card shadow-lg">
                      <div className="border-b border-brand-border px-2 py-1 text-[10px] uppercase tracking-wide text-brand-muted">
                        Mention a teammate
                      </div>
                      {mentionMatches.map((a, i) => (
                        <button
                          key={`${a.type}-${a.email ?? a.id}-${i}`}
                          onMouseDown={(e) => { e.preventDefault(); insertMention(a.label); }}
                          onMouseEnter={() => setMentionIdx(i)}
                          className={`flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm ${
                            i === mentionIdx ? "bg-red-50 text-signal-red" : "text-brand-dark hover:bg-subtle"
                          }`}
                        >
                          <span className="truncate font-medium">{a.label}</span>
                          <span className="ml-auto shrink-0 text-[10px] uppercase text-brand-muted">{a.type}</span>
                        </button>
                      ))}
                    </div>
                  )}
                  <textarea
                    ref={composerRef}
                    value={composer}
                    onChange={(e) => setComposer(e.target.value)}
                    onKeyDown={(e) => {
                      if (mentionQuery !== null && mentionMatches.length > 0) {
                        if (e.key === "ArrowDown") { e.preventDefault(); setMentionIdx((i) => (i + 1) % mentionMatches.length); return; }
                        if (e.key === "ArrowUp") { e.preventDefault(); setMentionIdx((i) => (i - 1 + mentionMatches.length) % mentionMatches.length); return; }
                        if (e.key === "Enter" || e.key === "Tab") { e.preventDefault(); insertMention(mentionMatches[mentionIdx].label); return; }
                        if (e.key === "Escape") { e.preventDefault(); setComposer((prev) => `${prev} `); return; }
                      }
                    }}
                    placeholder="Type your message…  (tip: start with /hi to ask the HI agent)"
                    className="h-24 w-full resize-none rounded-lg border border-brand-border bg-subtle p-3 pr-28 text-sm outline-none focus:border-signal-red/40 focus:bg-card"
                  />
                  <div className="absolute bottom-3 right-3 flex items-center gap-1.5">
                    {/* HI reply + /hi agent are PO-thread features; hidden on non-PO mails. */}
                    {!inOther && (
                      <button
                        onClick={() => void handleAiReply()}
                        className="inline-flex items-center gap-1 rounded-md border border-signal-red/30 bg-red-50 px-2.5 py-1.5 text-xs font-semibold text-signal-red hover:bg-red-100"
                        title="Generate a Harmony Intelligent reply"
                      >
                        <Sparkles size={13} /> HI
                      </button>
                    )}
                    <button
                      className="rounded-md bg-signal-red p-2 text-white shadow-sm hover:opacity-90 disabled:opacity-50"
                      disabled={!composer.trim() || replying || agentBusy}
                      onClick={() => void handleSendReply()}
                      title={
                        /^\/hi\b/i.test(composer.trim())
                          ? "Ask the HI agent"
                          : sendAsEmail
                            ? "Send by email + post to portal"
                            : "Post to supplier portal only"
                      }
                    >
                      <Send size={16} />
                    </button>
                  </div>
                </div>
                <label className="mt-2 flex items-center gap-2 text-xs text-brand-muted">
                  <input
                    type="checkbox"
                    checked={sendAsEmail}
                    onChange={(e) => setSendAsEmail(e.target.checked)}
                    className="accent-signal-red"
                  />
                  Send as email to the supplier
                  <span className="text-brand-muted/70">
                    {sendAsEmail ? "(emails them + shows in their portal)" : "(portal only — they read & reply in their portal)"}
                  </span>
                </label>
              </div>
            </>
          ) : (
            <div className="grid flex-1 place-items-center text-brand-muted">
              <div className="text-center">
                <MessagesSquare size={34} className="mx-auto mb-2 opacity-40" />
                <p className="text-sm">Select a purchase order or an Other Mail to view the conversation.</p>
              </div>
            </div>
          )}
        </main>

        {/* RIGHT — details + actions (collapsible) */}
        {detailsOpen ? (
          <aside className="flex w-[330px] shrink-0 flex-col overflow-hidden rounded-xl border border-brand-border bg-card shadow-sm">
            <div className="flex items-center justify-between border-b border-brand-border px-4 py-3">
              <div className="min-w-0">
                <div className="text-sm font-semibold text-brand-dark">Details &amp; Actions</div>
                <div className="truncate text-[11px] text-brand-muted">
                  {activePo ? `PO #${activePo.supplier_po_no}` : activeSupplier?.supplier_name || "No PO selected"}
                </div>
              </div>
              <button
                onClick={() => setDetailsOpen(false)}
                className="rounded-md p-1.5 text-brand-muted hover:bg-subtle"
                title="Collapse"
              >
                <ChevronRight size={16} />
              </button>
            </div>

            <div className="flex-1 space-y-4 overflow-y-auto p-4">
              {/* Recommended */}
              <div className="rounded-lg border border-red-100 bg-red-50/60 p-3">
                <div className="text-[10px] font-bold uppercase tracking-wide text-signal-red">Recommended</div>
                <div className="mt-1 text-sm font-semibold text-brand-dark">
                  {noPo ? "Select a PO" : recommendedAction(threadSignal, draftCount, contextTasks.filter((t) => t.status !== "DONE").length)}
                </div>
                <p className="mt-1 text-xs leading-relaxed text-brand-muted">
                  {noPo ? "Choose a supplier and PO to unlock actions." : actionDescription(threadSignal, lastMessage?.subject)}
                </p>
              </div>

              {/* Quick actions */}
              <div>
                <SectionTitle>Quick actions</SectionTitle>
                <div className="grid grid-cols-2 gap-2">
                  <QuickAction icon={<Sparkles size={14} />} label="HI Reply" onClick={() => void handleAiReply()} disabled={noPo} accent />
                  <QuickAction icon={<Send size={14} />} label="Send Draft" onClick={() => void handleSendMailNow()} disabled={noPo} />
                  <QuickAction icon={<AlertTriangle size={14} />} label="Escalate" onClick={() => void handleEscalate()} disabled={noPo} danger />
                  <QuickAction icon={<UserPlus size={14} />} label="Assign" onClick={seedAssign} disabled={!activeSupplier} />
                  <QuickAction icon={<Bell size={14} />} label="Reminder" onClick={seedReminder} disabled={!activeSupplier} />
                  <QuickAction icon={<Mail size={14} />} label="PO Mail" onClick={onPoMail} disabled={noPo} />
                </div>
              </div>

              {/* AI summary */}
              {activePo && (
                <div>
                  <SectionTitle>Harmony Intelligent summary</SectionTitle>
                  <div className="space-y-1.5 rounded-lg border border-brand-border bg-subtle/60 p-3 text-xs leading-relaxed text-brand-dark">
                    <p>
                      Conversation around {activePo.material_name || "this PO"} — {draftCount} draft / {sentCount} sent.
                    </p>
                    <p>
                      <span className="font-semibold text-brand-dark">Latest:</span> {lastMessage?.subject ?? "—"}
                    </p>
                    <p>
                      <span className="font-semibold text-brand-dark">Suggested:</span>{" "}
                      {threadSignal === "BLACK"
                        ? "Escalate to leadership immediately."
                        : threadSignal === "RED"
                          ? "Send strong follow-up and create P0 task."
                          : threadSignal === "YELLOW"
                            ? "Send reminder and confirm commitment date."
                            : "Monitor — no action required."}
                    </p>
                  </div>
                </div>
              )}

              {/* Materials */}
              {activePo && (activePo.materials?.length ?? 0) > 0 && (
                <div>
                  <button
                    onClick={() => setShowMaterials((v) => !v)}
                    className="flex w-full items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-brand-muted hover:text-brand-dark"
                  >
                    <ChevronDown size={13} className={`transition-transform ${showMaterials ? "rotate-180" : ""}`} />
                    Materials ({activePo.material_count ?? activePo.materials?.length})
                    {commitments.length > 0 && (
                      <span className="ml-auto rounded bg-emerald-50 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-700">
                        {commitments.length} commit{commitments.length === 1 ? "" : "s"}
                      </span>
                    )}
                  </button>
                  {showMaterials && (
                    <div className="mt-2 overflow-x-auto rounded border border-brand-border">
                      <table className="min-w-full text-[11px]">
                        <thead className="bg-subtle">
                          <tr>
                            {["CRM", "Material", "Qty", "Due", "Status", "Commit"].map((h, i) => (
                              <th key={i} className="whitespace-nowrap px-2 py-1.5 text-left font-semibold text-brand-muted">
                                {h}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {(activePo.materials ?? []).map((m: PoFollowupMaterial) => {
                            const commit =
                              commitments.find(
                                (c) => c.material_name?.toUpperCase() === m.material_name?.toUpperCase(),
                              ) ?? m.commitment ?? null;
                            return (
                              <tr key={m.procurement_record_id} className="border-t border-brand-border">
                                <td className="whitespace-nowrap px-2 py-1.5 font-mono">{m.crm_no}</td>
                                <td className="max-w-[120px] truncate px-2 py-1.5" title={m.material_name}>{m.material_name}</td>
                                <td className="whitespace-nowrap px-2 py-1.5">{m.po_qty ?? "-"}</td>
                                <td className="whitespace-nowrap px-2 py-1.5">{m.due_date ?? "-"}</td>
                                <td className="whitespace-nowrap px-2 py-1.5">
                                  <span className={`rounded px-1.5 py-0.5 text-[10px] ${SIGNAL_CHIP[(commit?.supplier_status || m.current_status || m.signal) as string] ?? "bg-subtle text-brand-dark"}`}>
                                    {commit?.supplier_status || m.current_status || m.signal}
                                  </span>
                                </td>
                                <td className="whitespace-nowrap px-2 py-1.5">{commit?.commitment_date ?? "-"}</td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              )}

              {/* Open tasks */}
              <div>
                <div className="mb-2 flex items-center justify-between">
                  <SectionTitle className="mb-0">
                    Open tasks ({contextTasks.filter((t) => t.status !== "DONE").length})
                  </SectionTitle>
                  <button onClick={seedAssign} className="rounded-md p-1 text-signal-red hover:bg-red-50" title="New task">
                    <Plus size={15} />
                  </button>
                </div>
                {contextTasks.length === 0 ? (
                  <EmptyState icon={<CheckCircle2 size={18} />}>No tasks yet.</EmptyState>
                ) : (
                  <div className="space-y-2">
                    {contextTasks.map((task) => (
                      <TaskCard key={task.id} task={task} onToggleDone={() => void handleToggleDone(task)} />
                    ))}
                  </div>
                )}
              </div>
            </div>
          </aside>
        ) : (
          <aside className="flex w-12 shrink-0 flex-col items-center gap-2 rounded-xl border border-brand-border bg-card py-3 shadow-sm">
            <RailIcon title="Details & actions" onClick={() => setDetailsOpen(true)}>
              <Sparkles size={18} />
            </RailIcon>
            <RailIcon title="HI Reply" onClick={() => void handleAiReply()} disabled={noPo}>
              <Sparkles size={18} />
            </RailIcon>
            <RailIcon title="Send Draft" onClick={() => void handleSendMailNow()} disabled={noPo}>
              <Send size={18} />
            </RailIcon>
            <RailIcon title="Escalate" onClick={() => void handleEscalate()} disabled={noPo}>
              <AlertTriangle size={18} />
            </RailIcon>
            <RailIcon title="Assign" onClick={seedAssign} disabled={!activeSupplier}>
              <UserPlus size={18} />
            </RailIcon>
            <div className="relative">
              <RailIcon title="Open tasks" onClick={() => setDetailsOpen(true)}>
                <CheckCircle2 size={18} />
              </RailIcon>
              {contextTasks.filter((t) => t.status !== "DONE").length > 0 && (
                <span className="absolute -right-0.5 -top-0.5 rounded-full bg-signal-red px-1 text-[9px] font-bold text-white">
                  {contextTasks.filter((t) => t.status !== "DONE").length}
                </span>
              )}
            </div>
          </aside>
        )}
      </div>

      {/* Create Task (shared form) */}
      {assignOpen && (
        <TaskCreateForm
          assignees={taskAssignees}
          seed={assignSeed}
          suppliers={supplierList.map((s) => s.supplier_name)}
          onCancel={() => setAssignOpen(false)}
          onSave={handleCreateTask}
        />
      )}

      {/* Toasts */}
      <div className="fixed bottom-6 right-6 z-50 flex flex-col gap-2">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={`rounded-md px-4 py-2 text-sm text-white shadow-lg ${
              t.tone === "ok" ? "bg-emerald-600" : "bg-signal-red"
            }`}
          >
            {t.msg}
          </div>
        ))}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// List rows
// ─────────────────────────────────────────────────────────────────────────────
function SupplierRow({ s, active, onClick }: { s: CommHubSupplier; active: boolean; onClick: () => void }) {
  const sig = (s.highest_signal || "GREEN") as TaskSignal;
  const unread = (s.unread_inbound ?? 0) > 0;
  return (
    <button
      onClick={onClick}
      className={`w-full border-b border-brand-border px-4 py-3 text-left transition-colors hover:bg-subtle ${
        active
          ? "bg-red-50/50 ring-1 ring-inset ring-red-100"
          : unread
          ? "border-l-4 border-l-emerald-500 bg-emerald-50/40"
          : ""
      }`}
    >
      <div className="flex items-center gap-2">
        {unread && <span className="h-2 w-2 shrink-0 rounded-full bg-emerald-500" title="Unread supplier replies" />}
        <span className={`h-2 w-2 shrink-0 rounded-full ${SIGNAL_DOT[sig] ?? "bg-subtle"}`} title={SIGNAL_LABEL[sig]} />
        <span className={`flex-1 truncate text-sm text-brand-dark ${unread ? "font-bold" : "font-medium"}`}>
          {s.supplier_name}
        </span>
        {unread && (
          <span className="rounded-full bg-emerald-500 px-1.5 py-0.5 text-[10px] font-bold text-white">
            {(s.unread_inbound ?? 0) > 99 ? "99+" : s.unread_inbound}
          </span>
        )}
        <span className="text-[10px] text-brand-muted">{relTime(s.last_activity_at)}</span>
      </div>
      <p className={`mt-1 truncate pl-4 text-xs ${unread ? "font-medium text-brand-dark/80" : "text-brand-muted"}`}>
        {s.last_subject ?? "No subject"}
      </p>
      {(s.draft_mail_count > 0 || s.task_count > 0) && (
        <div className="mt-1.5 flex items-center gap-1.5 pl-4">
          {s.draft_mail_count > 0 && (
            <span className="rounded bg-red-50 px-1.5 py-0.5 text-[10px] font-bold text-signal-red">
              {s.draft_mail_count} new
            </span>
          )}
          {s.task_count > 0 && (
            <span className="rounded bg-subtle px-1.5 py-0.5 text-[10px] font-semibold text-brand-dark">
              {s.task_count} task{s.task_count === 1 ? "" : "s"}
            </span>
          )}
        </div>
      )}
    </button>
  );
}

function PoRow({ p, active, onClick }: { p: CommHubPO; active: boolean; onClick: () => void }) {
  const sig = (p.signal || "GREEN") as TaskSignal;
  const materialCount = p.material_count ?? p.materials?.length ?? 0;
  const unread = (p.unread_inbound ?? 0) > 0;
  return (
    <button
      onClick={onClick}
      className={`w-full border-b border-brand-border px-4 py-3 text-left transition hover:bg-subtle ${
        active
          ? "bg-amber-50/60 ring-1 ring-inset ring-amber-100"
          : unread
          ? "border-l-4 border-l-emerald-500 bg-emerald-50/40"
          : ""
      }`}
    >
      <div className="flex items-center gap-2">
        <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${SIGNAL_DOT[sig] ?? "bg-subtle"}`} />
        <span className={`truncate text-sm text-brand-dark ${unread ? "font-bold" : "font-medium"}`}>#{p.supplier_po_no}</span>
        {(p.unread_inbound ?? 0) > 0 && (
          <span className="rounded-full bg-emerald-500 px-1.5 py-0.5 text-[10px] font-bold text-white">
            {(p.unread_inbound ?? 0) > 99 ? "99+" : p.unread_inbound}
          </span>
        )}
        <span className={`ml-auto rounded px-1.5 py-0.5 text-[10px] font-bold uppercase ${SIGNAL_CHIP[sig] ?? ""}`}>
          {SIGNAL_LABEL[sig] ?? sig}
        </span>
      </div>
      <div className="mt-1.5 flex items-center gap-2 pl-4 text-[11px] text-brand-muted">
        <Package size={12} className="text-brand-muted" />
        <span>{materialCount} mat{materialCount === 1 ? "" : "s"}</span>
        <span>· {p.mail_count} mail{p.mail_count === 1 ? "" : "s"}</span>
        {p.task_count > 0 && <span>· {p.task_count} task{p.task_count === 1 ? "" : "s"}</span>}
        <span className="ml-auto text-brand-muted">{relTime(p.last_activity_at)}</span>
      </div>
    </button>
  );
}

function OtherMailRow({ t, active, onClick }: { t: OtherMailThread; active: boolean; onClick: () => void }) {
  const unread = (t.unread_inbound ?? 0) > 0;
  return (
    <button
      onClick={onClick}
      className={`w-full border-b border-brand-border px-4 py-2.5 text-left transition hover:bg-subtle ${
        active
          ? "bg-amber-50/60 ring-1 ring-inset ring-amber-100"
          : unread
          ? "border-l-4 border-l-emerald-500 bg-emerald-50/40"
          : ""
      }`}
    >
      <div className="flex items-center gap-2">
        <Mail size={13} className="shrink-0 text-brand-muted" />
        <span className={`truncate text-[13px] text-brand-dark ${unread ? "font-bold" : "font-medium"}`}>
          {t.subject || "(no subject)"}
        </span>
        {unread && (
          <span className="ml-auto rounded-full bg-emerald-500 px-1.5 py-0.5 text-[10px] font-bold text-white">
            {(t.unread_inbound ?? 0) > 99 ? "99+" : t.unread_inbound}
          </span>
        )}
      </div>
      <div className="mt-1 flex items-center gap-2 pl-5 text-[11px] text-brand-muted">
        <span>
          {t.message_count} mail{t.message_count === 1 ? "" : "s"}
        </span>
        <span className="ml-auto text-brand-muted">{relTime(t.last_activity_at)}</span>
      </div>
    </button>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Shared bits
// ─────────────────────────────────────────────────────────────────────────────
function SectionTitle({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`mb-2 text-[11px] font-semibold uppercase tracking-wide text-brand-muted ${className}`}>
      {children}
    </div>
  );
}

function QuickAction({
  icon,
  label,
  onClick,
  disabled,
  accent,
  danger,
}: {
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
  disabled?: boolean;
  accent?: boolean;
  danger?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`inline-flex items-center justify-center gap-1.5 rounded-md border px-2.5 py-2 text-xs font-semibold disabled:pointer-events-none disabled:opacity-40 ${
        danger
          ? "border-red-200 bg-red-50 text-signal-red hover:bg-red-100"
          : accent
            ? "border-signal-red/30 bg-red-50 text-signal-red hover:bg-red-100"
            : "border-brand-border bg-card text-brand-dark hover:bg-subtle"
      }`}
    >
      {icon}
      {label}
    </button>
  );
}

function RailIcon({
  children,
  onClick,
  title,
  disabled,
}: {
  children: React.ReactNode;
  onClick: () => void;
  title: string;
  disabled?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={title}
      aria-label={title}
      className="rounded-md p-2 text-brand-muted hover:bg-subtle hover:text-brand-dark disabled:pointer-events-none disabled:opacity-30"
    >
      {children}
    </button>
  );
}

function EmptyState({ children, icon }: { children: React.ReactNode; icon?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-2 px-4 py-10 text-center text-sm text-brand-muted">
      {icon}
      <div>{children}</div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Mail bubble
// ─────────────────────────────────────────────────────────────────────────────
function MailBubble({ mail, onAssign }: { mail: CommHubMessage; onAssign: () => void }) {
  const isIncoming = mail.direction === "INCOMING";
  const tableRows = mail.table_rows ?? [];
  const bodyText = stripTableText(mail.body);

  return (
    <div className={`flex flex-col ${isIncoming ? "items-start" : "items-end"}`}>
      <div
        className={`group relative max-w-[82%] rounded-2xl border p-4 shadow-sm ${
          isIncoming
            ? "border-brand-border bg-card"
            : "border-amber-100 bg-amber-50 dark:border-amber-500/20 dark:bg-amber-500/10"
        }`}
      >
        <div className="mb-1 flex items-center justify-between gap-3">
          <span className="truncate text-xs font-semibold text-brand-dark">{mail.subject || "(no subject)"}</span>
          <span className="rounded bg-subtle px-1.5 py-0.5 text-[10px] font-semibold uppercase text-brand-muted">
            {mail.sent_status}
          </span>
        </div>
        {mail.table_format && (
          <div className="mb-2">
            <span className="rounded bg-subtle px-1.5 py-0.5 text-[10px] font-semibold uppercase text-brand-dark">
              {mail.table_format === "PO_MATERIALS" ? "PO Material Table" : "Supplier Reply Table"}
            </span>
          </div>
        )}
        {bodyText && (
          <p className="whitespace-pre-wrap text-sm leading-relaxed text-brand-dark">
            {truncate(bodyText, tableRows.length > 0 ? 1200 : 600)}
          </p>
        )}
        {tableRows.length > 0 && <ThreadMessageTable rows={tableRows} />}
        <div className="mt-2 flex flex-wrap items-center gap-2 text-[10px] text-brand-muted">
          <span>{fmtTime(mail.sent_at ?? mail.received_at ?? mail.created_at)}</span>
          <span>·</span>
          <span>{mail.mail_type || mail.source || "MAIL"}</span>
          <span>·</span>
          <span>{isIncoming ? (mail.sender_email || mail.supplier_name || "Supplier") : (mail.supplier_name ?? "You")}</span>
        </div>
        <button
          onClick={onAssign}
          className="absolute -left-9 top-2 rounded-full border border-brand-border bg-card p-1.5 text-brand-muted opacity-0 shadow transition-opacity hover:text-signal-red group-hover:opacity-100"
          title="Assign task from this mail"
        >
          <UserPlus size={12} />
        </button>
      </div>
    </div>
  );
}

function ThreadMessageTable({ rows }: { rows: ThreadTableRow[] }) {
  return (
    <div className="mt-3 overflow-x-auto rounded border border-brand-border bg-card">
      <table className="min-w-full text-xs">
        <thead className="bg-subtle">
          <tr>
            {["CRM No", "Material Name", "Qty", "UOM", "Due Date", "Status", "Commitment Date", "Remark"].map((header) => (
              <th
                key={header}
                className="whitespace-nowrap border-b border-brand-border px-2 py-1.5 text-left font-semibold text-brand-dark"
              >
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={`${row.crm_no || row.material_name || "row"}-${index}`} className="border-t border-brand-border">
              <td className="whitespace-nowrap px-2 py-1.5 font-mono">{row.crm_no || "-"}</td>
              <td className="max-w-[280px] truncate px-2 py-1.5" title={row.material_name || ""}>
                {row.material_name || "-"}
              </td>
              <td className="whitespace-nowrap px-2 py-1.5">{fmtTableQty(row.qty)}</td>
              <td className="whitespace-nowrap px-2 py-1.5">{row.uom || "-"}</td>
              <td className="whitespace-nowrap px-2 py-1.5">{fmtTableDate(row.due_date)}</td>
              <td className="whitespace-nowrap px-2 py-1.5">{row.status || "-"}</td>
              <td className="whitespace-nowrap px-2 py-1.5">{fmtTableDate(row.commitment_date)}</td>
              <td className="max-w-[220px] truncate px-2 py-1.5" title={row.remark || ""}>
                {row.remark || "-"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Task card
// ─────────────────────────────────────────────────────────────────────────────
function TaskCard({ task, onToggleDone }: { task: CommunicationTask; onToggleDone: () => void }) {
  const due = fmtDueDate(task.due_date);
  const done = task.status === "DONE";
  const sig = (task.signal || "YELLOW") as TaskSignal;
  return (
    <div
      className={`rounded-lg border bg-card p-3 transition-colors hover:border-signal-red/30 ${done ? "opacity-60" : ""} ${
        sig === "BLACK" ? "border-gray-900/40" : sig === "RED" ? "border-red-200" : "border-brand-border"
      }`}
    >
      <div className="mb-2 flex items-start gap-2">
        <button
          onClick={onToggleDone}
          className={`mt-0.5 grid h-4 w-4 shrink-0 place-items-center rounded-full border-2 ${
            done ? "border-emerald-500 bg-emerald-500" : "border-brand-border hover:border-signal-red"
          }`}
          title={done ? "Reopen" : "Mark done"}
        >
          {done && <CheckCircle2 size={10} className="text-white" />}
        </button>
        <div className="min-w-0 flex-1">
          <p className={`text-xs font-semibold leading-snug ${done ? "text-brand-muted line-through" : "text-brand-dark"}`}>
            {task.title}
          </p>
          {(task.supplier_po_no || task.supplier_name) && (
            <p className="mt-0.5 truncate text-[10px] text-brand-muted">
              {task.supplier_po_no && <>#{task.supplier_po_no} · </>}
              {task.supplier_name}
            </p>
          )}
        </div>
        <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${SIGNAL_DOT[sig] ?? "bg-subtle"}`} />
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className={`rounded px-1.5 py-0.5 text-[9px] font-bold ${PRIORITY_CHIP[task.priority as TaskPriority] ?? "bg-subtle text-brand-muted"}`}>
            {task.priority}
          </span>
          {task.assigned_to && (
            <span className="max-w-[100px] truncate text-[10px] text-brand-muted">@{task.assigned_to}</span>
          )}
        </div>
        <div className="flex items-center gap-2 text-[10px] text-brand-muted">
          {task.linked_mail_id && <MessagesSquare size={11} />}
          {task.comments_count > 0 && <span>{task.comments_count}c</span>}
          <span className={due.overdue && !done ? "font-semibold text-signal-red" : ""}>{due.text}</span>
        </div>
      </div>
    </div>
  );
}

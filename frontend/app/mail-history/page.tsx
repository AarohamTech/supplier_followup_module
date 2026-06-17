"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import api from "@/lib/api";
import { useStore } from "@/lib/store";
import type {
  CommHubDashboard,
  CommHubMessage,
  CommHubPO,
  CommHubSupplier,
  CommHubTasksGrouped,
  CommHubThread,
  CommunicationTask,
  CommunicationTaskCreate,
  PoFollowupMaterial,
  SupplierMaterialCommitment,
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
  Edit3,
  Filter,
  Inbox,
  Loader2,
  Mail,
  MessagesSquare,
  MoreHorizontal,
  Package,
  Paperclip,
  Plus,
  RefreshCcw,
  Reply,
  Search,
  Send,
  Sparkles,
  UserPlus,
  X,
} from "lucide-react";

// ─────────────────────────────────────────────────────────────────────────────
// Constants
// ─────────────────────────────────────────────────────────────────────────────
const ASSIGNEES = [
  "Rajesh Kumar",
  "Procurement Lead",
  "Stores User",
  "Quality User",
  "Purchase Head",
  "Sourcing Head",
  "Admin User",
];

const TEMPLATES: { label: string; tone: string; body: string }[] = [
  {
    label: "Professional",
    tone: "border-gray-200 text-gray-700",
    body: "Dear Team,\n\nKindly share the latest status on the referenced PO at your earliest convenience.\n\nBest regards,",
  },
  {
    label: "Reminder",
    tone: "border-amber-200 text-amber-700 bg-amber-50",
    body: "Dear Team,\n\nThis is a gentle reminder regarding the pending dispatch for the referenced PO. Please share an updated commitment.\n\nRegards,",
  },
  {
    label: "Strong Follow-up",
    tone: "border-orange-200 text-orange-700 bg-orange-50",
    body: "Dear Team,\n\nWe have not received an update on the referenced PO despite multiple follow-ups. Please confirm dispatch status today.\n\nRegards,",
  },
  {
    label: "Escalation",
    tone: "border-red-200 text-signal-red bg-red-50",
    body: "Dear Team,\n\nThe delay on the referenced PO is now critical and will impact our line. We are escalating this matter to leadership.\n\nRegards,",
  },
];

const SIGNAL_DOT: Record<string, string> = {
  GREEN: "bg-emerald-500",
  YELLOW: "bg-amber-500",
  RED: "bg-signal-red",
  BLACK: "bg-gray-900",
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
  BLACK: "bg-gray-900 text-white",
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
  P3: "bg-gray-100 text-gray-600",
};

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

// ─────────────────────────────────────────────────────────────────────────────
// Page
// ─────────────────────────────────────────────────────────────────────────────
export default function Page() {
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

  // ── UI state ──
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [showAiSummary, setShowAiSummary] = useState(false);
  const [taskPanelOpen, setTaskPanelOpen] = useState(true);
  const [composer, setComposer] = useState("");
  const [assignOpen, setAssignOpen] = useState(false);
  const [assignSeed, setAssignSeed] = useState<Partial<CommunicationTaskCreate>>({});
  const [toasts, setToasts] = useState<{ id: number; tone: "ok" | "err"; msg: string }[]>([]);
  const [expandedPo, setExpandedPo] = useState<Set<string>>(new Set());
  const [commitments, setCommitments] = useState<SupplierMaterialCommitment[]>([]);
  const [showMaterials, setShowMaterials] = useState(false);
  const selectPoGroup = useStore((s) => s.selectPoGroup);

  // ── Derived ──
  const activeSupplier = supplierList.find((s) => s.supplier_name === selectedSupplierName) ?? null;
  const activePo = poList.find((p) => p.procurement_record_id === selectedProcurementId) ?? null;
  const threadMessages: CommHubMessage[] = thread?.messages ?? [];
  const draftCount = threadMessages.filter((m) => m.sent_status === "DRAFT").length;
  const sentCount = threadMessages.filter((m) => m.sent_status !== "DRAFT").length;
  const threadSignal = (thread?.signal ?? activePo?.signal ?? "GREEN") as TaskSignal;
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
    if (!q) return supplierList;
    return supplierList.filter(
      (s) =>
        s.supplier_name.toLowerCase().includes(q) ||
        (s.last_subject || "").toLowerCase().includes(q),
    );
  }, [supplierList, search]);

  // ── Data loaders ──
  const loadKpis = useCallback(async () => {
    try {
      setHubKpis(await api.hubDashboard());
    } catch {}
  }, []);

  const loadTasks = useCallback(
    async (opts: { supplier_id?: number | null; procurement_record_id?: number | null }) => {
      try {
        const params: Record<string, number> = {};
        if (opts.procurement_record_id != null) params.procurement_record_id = opts.procurement_record_id;
        else if (opts.supplier_id != null) params.supplier_id = opts.supplier_id;
        setTaskGroups(await api.hubTasks(params));
      } catch {}
    },
    [],
  );

  const loadThread = useCallback(async (procurementRecordId: number) => {
    try {
      setThread(await api.hubThread({ procurement_record_id: procurementRecordId }));
    } catch {}
  }, []);

  const loadCommitments = useCallback(
    async (supplierName: string, supplierPoNo: string) => {
      try {
        const rows = await api.listCommitments({
          supplier_name: supplierName,
          supplier_po_no: supplierPoNo,
        });
        setCommitments(rows);
      } catch {
        setCommitments([]);
      }
    },
    [],
  );

  const loadPos = useCallback(
    async (supplierName: string, supplierId: number | null): Promise<CommHubPO[]> => {
      const pos = supplierId != null
        ? await api.hubPosById(supplierId)
        : await api.hubPosByName(supplierName);
      setPoList(pos);
      return pos;
    },
    [],
  );

  // ── Select supplier ──
  const handleSelectSupplier = useCallback(
    async (supplierName: string, supplierId: number | null) => {
      if (supplierName === selectedSupplierName) return;
      setSelectedSupplierName(supplierName);
      setSelectedSupplierId(supplierId);
      setSelectedProcurementId(null);
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
            await api.hubMarkThreadRead({
              supplier_po_no: supplierPoNo,
              procurement_record_id: procurementRecordId,
            });
            if (selectedSupplierName) {
              await loadPos(selectedSupplierName, selectedSupplierId);
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
    ],
  );

  // ── Full refresh ──
  const loadAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      await loadKpis();
      const suppliers = await api.hubSuppliers();
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
  }, [loadKpis, loadPos, loadThread, loadTasks, loadCommitments]);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

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
      const created = await api.hubCreateTask(payload);
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
      await api.hubUpdateTask(task.id, { status: next });
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
      await api.hubEscalate(activePo.procurement_record_id);
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
      const result = await api.hubSendMail(targetId);
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
      const result = await api.hubAiReply(activePo.procurement_record_id);
      setComposer(result.body);
      pushToast("ok", "AI reply generated");
    } catch (e: unknown) {
      pushToast("err", e instanceof Error ? e.message : "AI reply failed");
    }
  };

  return (
    <div className="-m-6 flex flex-col h-[calc(100vh-64px)] bg-white">
      {/* Header bar */}
      <header className="h-14 px-6 flex items-center justify-between border-b border-brand-border bg-white">
        <div className="flex items-center gap-5">
          <h1 className="text-lg font-semibold text-brand-dark">
            Supplier Communication Hub
          </h1>
          <div className="relative">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search supplier, subject…  (Ctrl+K)"
              className="pl-9 pr-3 py-1.5 bg-gray-50 border border-transparent focus:border-brand-border focus:bg-white rounded-md w-96 text-sm outline-none"
            />
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={loadAll} className="btn-ghost" disabled={loading}>
            {loading ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <RefreshCcw size={14} />
            )}
            <span className="ml-1">Refresh</span>
          </button>
          <button className="p-2 rounded hover:bg-gray-100 text-gray-500 relative">
            <Bell size={16} />
            {kpis.openTasks > 0 && (
              <span className="absolute -top-0.5 -right-0.5 bg-signal-red text-white text-[9px] font-bold rounded-full px-1">
                {kpis.openTasks}
              </span>
            )}
          </button>
        </div>
      </header>

      {/* KPI strip */}
      <div className="px-6 py-3 flex gap-4 items-center border-b border-brand-border bg-white">
        <div className="flex-1 grid grid-cols-4 gap-4">
          <KpiPill label="Unread Drafts" value={kpis.drafts} tone="text-signal-red" />
          <KpiPill label="Waiting Supplier" value={kpis.waiting} tone="text-amber-600" />
          <KpiPill label="Delayed POs" value={kpis.delayed} tone="text-orange-600" />
          <KpiPill label="Open Tasks" value={kpis.openTasks} tone="text-gray-800" />
        </div>
        <button
          className="btn-primary"
          onClick={() =>
            openAssign({
              supplier_name: activeSupplier?.supplier_name ?? null,
              supplier_po_no: activePo?.supplier_po_no ?? null,
              procurement_record_id: activePo?.procurement_record_id ?? null,
            })
          }
        >
          <Edit3 size={14} />
          <span className="ml-1.5">Compose Task</span>
        </button>
      </div>

      {error && (
        <div className="mx-6 mt-3 text-sm text-signal-red bg-red-50 border border-red-100 rounded-md px-3 py-2">
          {error}
        </div>
      )}

      {/* Workspace */}
      <div className="flex-1 flex overflow-hidden">
        {/* Suppliers panel */}
        <section className="w-[24%] min-w-[260px] border-r border-brand-border flex flex-col bg-white">
          <ColumnHeader
            title="Suppliers"
            right={
              <span className="flex items-center gap-2 text-[11px] text-brand-muted">
                {filteredSuppliers.length}
                <Filter size={14} className="text-gray-400" />
              </span>
            }
          />
          <div className="flex-1 overflow-y-auto">
            {loading && supplierList.length === 0 ? (
              <EmptyState icon={<Loader2 className="animate-spin" size={18} />}>
                Loading…
              </EmptyState>
            ) : filteredSuppliers.length === 0 ? (
              <EmptyState icon={<Inbox size={20} />}>
                No communication data found from existing pipeline.
              </EmptyState>
            ) : (
              filteredSuppliers.map((s) => {
                const active = s.supplier_name === selectedSupplierName;
                const sig = (s.highest_signal || "GREEN") as TaskSignal;
                return (
                  <button
                    key={s.supplier_name}
                    onClick={() => void handleSelectSupplier(s.supplier_name, s.supplier_id)}
                    className={`w-full text-left px-4 py-3 border-b border-brand-border hover:bg-gray-50 transition-colors ${
                      active
                        ? "bg-red-50/40 border-l-2 border-l-signal-red"
                        : "border-l-2 border-l-transparent"
                    }`}
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <span
                        className={`w-2 h-2 rounded-full ${SIGNAL_DOT[sig] ?? "bg-gray-300"}`}
                        title={SIGNAL_LABEL[sig]}
                      />
                      <span
                        className={`font-semibold text-sm truncate flex-1 ${
                          active ? "text-brand-dark" : "text-gray-800"
                        }`}
                      >
                        {s.supplier_name}
                      </span>
                      <span className="text-[10px] text-gray-400">
                        {relTime(s.last_activity_at)}
                      </span>
                    </div>
                    <p className="text-xs text-brand-muted truncate ml-4 mb-2">
                      {s.last_subject ?? "No subject"}
                    </p>
                    <div className="flex justify-between items-center ml-4 gap-2">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <HealthChip pct={s.health_score} />
                        {s.draft_mail_count > 0 && (
                          <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-red-50 text-signal-red">
                            {s.draft_mail_count} new
                          </span>
                        )}
                        {s.task_count > 0 && (
                          <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-gray-100 text-gray-700">
                            {s.task_count} task{s.task_count === 1 ? "" : "s"}
                          </span>
                        )}
                      </div>
                    </div>
                  </button>
                );
              })
            )}
          </div>
        </section>

        {/* PO panel */}
        <section className="w-[22%] min-w-[220px] border-r border-brand-border flex flex-col bg-white">
          <ColumnHeader title="Purchase Orders" />
          <div className="flex-1 overflow-y-auto">
            {activeSupplier && poList.length === 0 && !loading ? (
              <EmptyState icon={<Inbox size={18} />}>No POs found for this supplier.</EmptyState>
            ) : !activeSupplier ? (
              <EmptyState icon={<Inbox size={18} />}>Select a supplier</EmptyState>
            ) : (
              poList.map((p) => {
                const active = p.procurement_record_id === selectedProcurementId;
                const sig = (p.signal || "GREEN") as TaskSignal;
                const poKey = `${p.supplier_name}|${p.supplier_po_no}`;
                const isExpanded = expandedPo.has(poKey);
                const materials = p.materials ?? [];
                const materialCount = p.material_count ?? materials.length;
                return (
                  <div
                    key={p.procurement_record_id}
                    className={`group relative w-full border-b border-brand-border hover:bg-gray-50 transition-colors ${
                      active ? "bg-amber-50/50" : ""
                    }`}
                  >
                    <button
                      onClick={() =>
                        void handleSelectPo(p.procurement_record_id, p.supplier_name, p.supplier_po_no)
                      }
                      className="w-full text-left px-4 py-3"
                    >
                      <div className="flex justify-between items-start mb-1">
                        <div className="flex items-center gap-2 min-w-0">
                          <span className={`w-2 h-2 rounded-full shrink-0 ${SIGNAL_DOT[sig] ?? "bg-gray-300"}`} />
                          <span
                            className={`font-semibold text-sm truncate ${
                              active ? "text-brand-dark" : "text-gray-800"
                            }`}
                          >
                            #{p.supplier_po_no}
                          </span>
                          {(p.unread_inbound ?? 0) > 0 && (
                            <span
                              className="text-[10px] font-bold px-1.5 py-0.5 rounded-full bg-emerald-500 text-white min-w-[18px] text-center"
                              title={`${p.unread_inbound} new supplier mail${
                                p.unread_inbound === 1 ? "" : "s"
                              }`}
                            >
                              {(p.unread_inbound ?? 0) > 99 ? "99+" : p.unread_inbound}
                            </span>
                          )}
                        </div>
                        <span
                          className={`text-[10px] font-bold px-1.5 py-0.5 rounded uppercase ${SIGNAL_CHIP[sig] ?? ""}`}
                        >
                          {SIGNAL_LABEL[sig] ?? sig}
                        </span>
                      </div>
                      <div className="flex items-center gap-2 text-xs text-brand-muted mb-1">
                        <Package size={12} className="text-gray-400" />
                        <span className="font-semibold text-gray-700">{materialCount}</span>
                        <span>material{materialCount === 1 ? "" : "s"} in this PO</span>
                      </div>
                      <div className="flex justify-between items-center text-[10px] text-gray-500">
                        <span>
                          {p.mail_count} mail{p.mail_count === 1 ? "" : "s"}
                          {p.task_count > 0 && ` · ${p.task_count} task${p.task_count === 1 ? "" : "s"}`}
                        </span>
                        <span className="text-gray-400">{relTime(p.last_activity_at)}</span>
                      </div>
                    </button>
                    <div className="px-4 pb-2 flex items-center gap-1 flex-wrap">
                      {materials.length > 0 && (
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setExpandedPo((prev) => {
                              const next = new Set(prev);
                              if (next.has(poKey)) next.delete(poKey);
                              else next.add(poKey);
                              return next;
                            });
                          }}
                          className="text-[10px] font-semibold px-2 py-0.5 rounded bg-slate-100 text-slate-700 hover:bg-slate-200 inline-flex items-center gap-1"
                        >
                          {isExpanded ? <ChevronDown size={10} /> : <ChevronRight size={10} />}
                          {isExpanded ? "Hide materials" : "View materials"}
                        </button>
                      )}
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          selectPoGroup({
                            supplier_name: p.supplier_name,
                            supplier_po_no: p.supplier_po_no,
                          });
                        }}
                        className="text-[10px] font-semibold px-2 py-0.5 rounded bg-signal-red text-white hover:opacity-90 inline-flex items-center gap-1"
                      >
                        <Mail size={10} /> PO Mail
                      </button>
                    </div>
                    {isExpanded && materials.length > 0 && (
                      <div className="px-4 pb-3">
                        <div className="overflow-x-auto border border-brand-border rounded bg-white">
                          <table className="min-w-full text-[10px]">
                            <thead className="bg-slate-100">
                              <tr>
                                {["CRM", "Material", "Qty", "Due", "Sig"].map((h, i) => (
                                  <th key={i} className="text-left px-1.5 py-1 font-semibold text-slate-700 border-b border-brand-border whitespace-nowrap">
                                    {h}
                                  </th>
                                ))}
                              </tr>
                            </thead>
                            <tbody>
                              {materials.map((m: PoFollowupMaterial) => (
                                <tr key={m.procurement_record_id} className="border-t border-brand-border">
                                  <td className="px-1.5 py-1 whitespace-nowrap font-mono">{m.crm_no}</td>
                                  <td className="px-1.5 py-1 max-w-[140px] truncate" title={m.material_name}>{m.material_name}</td>
                                  <td className="px-1.5 py-1 whitespace-nowrap">{m.po_qty ?? "-"}</td>
                                  <td className="px-1.5 py-1 whitespace-nowrap">{m.due_date ?? "-"}</td>
                                  <td className="px-1.5 py-1 whitespace-nowrap">
                                    <span className={`inline-block w-2 h-2 rounded-full ${SIGNAL_DOT[(m.signal || "GREEN") as string] ?? "bg-gray-300"}`} />
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    )}
                    {/* Hover assign */}
                    <div className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity flex gap-1">
                      <IconBtn
                        title="Assign"
                        onClick={(e) => {
                          e.stopPropagation();
                          openAssign({
                            title: `Follow-up PO #${p.supplier_po_no}`,
                            supplier_name: activeSupplier.supplier_name,
                            supplier_po_no: p.supplier_po_no,
                            procurement_record_id: p.procurement_record_id,
                            signal: sig,
                          });
                        }}
                      >
                        <UserPlus size={12} />
                      </IconBtn>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </section>

        {/* Conversation thread */}
        <section className="flex-1 flex flex-col bg-[#FDFDFD] min-w-0">
          {activePo && activeSupplier ? (
            <>
              {/* Thread header */}
              <div className="px-6 py-4 border-b border-brand-border bg-white">
                <div className="flex justify-between items-center mb-2">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className={`w-2 h-2 rounded-full ${SIGNAL_DOT[threadSignal] ?? "bg-gray-300"}`} />
                    <h3 className="font-semibold text-brand-dark truncate">
                      PO #{activePo.supplier_po_no} — {activeSupplier.supplier_name}
                    </h3>
                    <span
                      className={`text-[10px] font-bold px-1.5 py-0.5 rounded uppercase ${SIGNAL_CHIP[threadSignal] ?? ""}`}
                    >
                      {SIGNAL_LABEL[threadSignal] ?? threadSignal}
                    </span>
                  </div>
                  <div className="flex items-center gap-1">
                    <button
                      className="btn-ghost"
                      onClick={() =>
                        openAssign({
                          title: `Assign PO #${activePo.supplier_po_no}`,
                          supplier_name: activeSupplier.supplier_name,
                          supplier_po_no: activePo.supplier_po_no,
                          procurement_record_id: activePo.procurement_record_id,
                          signal: threadSignal,
                          linked_mail_id: lastMessageId,
                        })
                      }
                    >
                      <UserPlus size={14} />
                      <span className="ml-1">Assign</span>
                    </button>
                    <button className="p-1 rounded hover:bg-gray-100 text-gray-400">
                      <MoreHorizontal size={18} />
                    </button>
                  </div>
                </div>
                <button
                  onClick={() => setShowAiSummary((s) => !s)}
                  className="flex items-center gap-1.5 text-xs font-semibold text-signal-red hover:text-red-700"
                >
                  <ChevronDown
                    size={14}
                    className={`transition-transform ${showAiSummary ? "rotate-180" : ""}`}
                  />
                  AI Summary — {threadMessages.length} message
                  {threadMessages.length === 1 ? "" : "s"} · {draftCount} draft ·{" "}
                  {SIGNAL_LABEL[threadSignal] ?? threadSignal} risk
                </button>
                {showAiSummary && (
                  <div className="mt-3 p-3 bg-red-50/50 rounded-lg border border-red-100 text-sm space-y-1">
                    <p className="text-gray-700">
                      <strong className="text-signal-red">Summary:</strong>{" "}
                      Conversation around {activePo.material_name || "this PO"} with{" "}
                      {draftCount} draft / {sentCount} sent mails.
                    </p>
                    <p className="text-gray-700">
                      <strong>Latest:</strong> {lastMessage?.subject ?? "—"}
                    </p>
                    <p className="text-gray-700">
                      <strong>Suggested action:</strong>{" "}
                      {threadSignal === "BLACK"
                        ? "Escalate to leadership immediately."
                        : threadSignal === "RED"
                          ? "Send strong follow-up and create P0 task."
                          : threadSignal === "YELLOW"
                            ? "Send reminder and confirm commitment date."
                            : "Monitor — no action required."}
                    </p>
                  </div>
                )}
                {(activePo.materials?.length ?? 0) > 0 && (
                  <div className="mt-3">
                    <button
                      onClick={() => setShowMaterials((s) => !s)}
                      className="flex items-center gap-1.5 text-xs font-semibold text-slate-700 hover:text-slate-900"
                    >
                      <ChevronDown
                        size={14}
                        className={`transition-transform ${showMaterials ? "rotate-180" : ""}`}
                      />
                      Materials in this PO ({activePo.material_count ?? activePo.materials?.length})
                      {commitments.length > 0 && (
                        <span className="ml-2 chip bg-emerald-50 text-emerald-700 border-emerald-100">
                          {commitments.length} commitment{commitments.length === 1 ? "" : "s"}
                        </span>
                      )}
                    </button>
                    {showMaterials && (
                      <div className="mt-2 overflow-x-auto border border-brand-border rounded bg-white">
                        <table className="min-w-full text-xs">
                          <thead className="bg-slate-100">
                            <tr>
                              {["CRM", "Material Name", "Qty", "UOM", "Due", "Status", "Last Commit Date", "Remark"].map((h, i) => (
                                <th key={i} className="text-left px-2 py-1.5 font-semibold text-slate-700 border-b border-brand-border whitespace-nowrap">
                                  {h}
                                </th>
                              ))}
                            </tr>
                          </thead>
                          <tbody>
                            {(activePo.materials ?? []).map((m: PoFollowupMaterial) => {
                              const commit = commitments.find(
                                (c) => c.material_name?.toUpperCase() === m.material_name?.toUpperCase(),
                              ) ?? m.commitment ?? null;
                              return (
                                <tr key={m.procurement_record_id} className="border-t border-brand-border">
                                  <td className="px-2 py-1.5 whitespace-nowrap font-mono">{m.crm_no}</td>
                                  <td className="px-2 py-1.5 max-w-[260px] truncate" title={m.material_name}>{m.material_name}</td>
                                  <td className="px-2 py-1.5 whitespace-nowrap">{m.po_qty ?? "-"}</td>
                                  <td className="px-2 py-1.5 whitespace-nowrap">{m.uom ?? "-"}</td>
                                  <td className="px-2 py-1.5 whitespace-nowrap">{m.due_date ?? "-"}</td>
                                  <td className="px-2 py-1.5 whitespace-nowrap">
                                    <span className={`chip ${SIGNAL_CHIP[(commit?.supplier_status || m.current_status || m.signal) as string] ?? "bg-gray-100 text-gray-700"}`}>
                                      {commit?.supplier_status || m.current_status || m.signal}
                                    </span>
                                  </td>
                                  <td className="px-2 py-1.5 whitespace-nowrap">{commit?.commitment_date ?? "-"}</td>
                                  <td className="px-2 py-1.5 max-w-[220px] truncate" title={commit?.supplier_remark ?? ""}>
                                    {commit?.supplier_remark ?? "-"}
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
              </div>

              {/* Mail thread */}
              <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5">
                {threadMessages.length === 0 ? (
                  <EmptyState icon={<MessagesSquare size={20} />}>
                    No emails sent yet for this PO.
                  </EmptyState>
                ) : (
                  threadMessages.map((m) => (
                    <MailBubble
                      key={String(m.id)}
                      mail={m}
                      onAssign={() =>
                        openAssign({
                          title: `Follow-up: ${m.subject}`,
                          supplier_name: activeSupplier.supplier_name,
                          supplier_po_no: activePo.supplier_po_no,
                          procurement_record_id: activePo.procurement_record_id,
                          linked_mail_id: numericMailId(m.id),
                        })
                      }
                    />
                  ))
                )}
              </div>

              {/* Composer */}
              <div className="p-4 border-t border-brand-border bg-white shadow-[0_-4px_20px_rgba(0,0,0,0.03)]">
                <div className="flex gap-2 mb-3 items-center flex-wrap">
                  <ToolButton icon={<Reply size={13} />}>Reply</ToolButton>
                  <ToolButton
                    icon={<UserPlus size={13} />}
                    onClick={() =>
                      openAssign({
                        supplier_name: activeSupplier.supplier_name,
                        supplier_po_no: activePo.supplier_po_no,
                        procurement_record_id: activePo.procurement_record_id,
                        linked_mail_id: lastMessageId,
                      })
                    }
                  >
                    Assign
                  </ToolButton>
                  <ToolButton icon={<Sparkles size={13} />} accent onClick={() => void handleAiReply()}>
                    AI Reply
                  </ToolButton>
                  <ToolButton icon={<Send size={13} />} onClick={() => void handleSendMailNow()}>
                    Send Mail
                  </ToolButton>
                  <ToolButton icon={<AlertTriangle size={13} />} onClick={() => void handleEscalate()}>
                    Escalate
                  </ToolButton>
                  <ToolButton
                    icon={<Plus size={13} />}
                    onClick={() =>
                      openAssign({
                        title: `Follow-up: PO ${activePo.supplier_po_no}`,
                        supplier_name: activeSupplier.supplier_name,
                        supplier_po_no: activePo.supplier_po_no,
                        procurement_record_id: activePo.procurement_record_id,
                        linked_mail_id: lastMessageId,
                        task_source: "SUPPLIER",
                      })
                    }
                  >
                    Create Task
                  </ToolButton>
                  <ToolButton
                    icon={<Bell size={13} />}
                    onClick={() =>
                      openAssign({
                        title: `Reminder: PO ${activePo.supplier_po_no}`,
                        supplier_name: activeSupplier.supplier_name,
                        supplier_po_no: activePo.supplier_po_no,
                        procurement_record_id: activePo.procurement_record_id,
                        linked_mail_id: lastMessageId,
                        task_source: "SUPPLIER",
                        reminder_at: new Date(Date.now() + 86400000).toISOString(),
                      })
                    }
                  >
                    Reminder
                  </ToolButton>
                </div>
                <div className="flex gap-2 mb-3 flex-wrap">
                  {TEMPLATES.map((t) => (
                    <button
                      key={t.label}
                      onClick={() => setComposer(t.body)}
                      className={`text-[11px] font-semibold px-2.5 py-1 rounded border ${t.tone} hover:opacity-80`}
                    >
                      {t.label}
                    </button>
                  ))}
                </div>
                <div className="relative">
                  <textarea
                    value={composer}
                    onChange={(e) => setComposer(e.target.value)}
                    placeholder="Type your message…"
                    className="w-full h-24 p-3 bg-gray-50 border border-transparent focus:border-brand-border focus:bg-white rounded-lg text-sm outline-none resize-none"
                  />
                  <button
                    className="absolute bottom-3 right-3 bg-signal-red text-white p-2 rounded-md hover:opacity-90 shadow-sm disabled:opacity-50"
                    disabled={!composer.trim()}
                    onClick={() => {
                      pushToast("ok", "Reply queued (demo)");
                      setComposer("");
                    }}
                  >
                    <Send size={16} />
                  </button>
                </div>
              </div>
            </>
          ) : (
            <div className="flex-1 grid place-items-center text-brand-muted">
              <div className="text-center">
                <MessagesSquare size={32} className="mx-auto mb-2 opacity-40" />
                <p className="text-sm">Select a purchase order to view the conversation.</p>
              </div>
            </div>
          )}
        </section>

        {/* Task panel */}
        <TaskPanel
          open={taskPanelOpen}
          onToggle={() => setTaskPanelOpen((s) => !s)}
          tasks={contextTasks}
          contextLabel={
            activePo
              ? `PO #${activePo.supplier_po_no}`
              : activeSupplier
                ? activeSupplier.supplier_name
                : "All"
          }
          onCreate={() =>
            openAssign({
              supplier_name: activeSupplier?.supplier_name ?? null,
              supplier_po_no: activePo?.supplier_po_no ?? null,
              procurement_record_id: activePo?.procurement_record_id ?? null,
            })
          }
          onToggleDone={handleToggleDone}
        />
      </div>

      {/* Assign Modal */}
      {assignOpen && (
        <AssignModal
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
            className={`px-4 py-2 rounded-md shadow-lg text-sm text-white ${
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
// Sub-components (UI unchanged)
// ─────────────────────────────────────────────────────────────────────────────
function ColumnHeader({ title, right }: { title: string; right?: React.ReactNode }) {
  return (
    <div className="px-4 h-12 flex items-center justify-between border-b border-brand-border">
      <span className="font-semibold text-sm text-brand-dark">{title}</span>
      {right}
    </div>
  );
}

function KpiPill({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <div className="bg-gray-50 border border-brand-border rounded-lg px-4 py-2 flex justify-between items-center">
      <span className="text-[11px] font-semibold uppercase tracking-wider text-brand-muted">
        {label}
      </span>
      <span className={`text-lg font-bold ${tone}`}>{value}</span>
    </div>
  );
}

function HealthChip({ pct }: { pct: number }) {
  const cls =
    pct >= 80
      ? "bg-emerald-50 text-emerald-700"
      : pct >= 50
        ? "bg-amber-50 text-amber-700"
        : "bg-red-50 text-signal-red";
  return (
    <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${cls}`}>
      {pct}% Health
    </span>
  );
}

function EmptyState({ children, icon }: { children: React.ReactNode; icon?: React.ReactNode }) {
  return (
    <div className="px-4 py-10 text-center text-brand-muted text-sm flex flex-col items-center gap-2">
      {icon}
      <div>{children}</div>
    </div>
  );
}

function ToolButton({
  children,
  icon,
  accent,
  onClick,
}: {
  children: React.ReactNode;
  icon: React.ReactNode;
  accent?: boolean;
  onClick?: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`px-3 py-1.5 border rounded-md text-[11px] font-semibold flex items-center gap-1 transition-colors ${
        accent
          ? "border-signal-red/30 text-signal-red hover:bg-red-50"
          : "border-brand-border text-brand-dark hover:bg-gray-50"
      }`}
    >
      {icon}
      {children}
    </button>
  );
}

function IconBtn({
  children,
  onClick,
  title,
}: {
  children: React.ReactNode;
  onClick?: (e: React.MouseEvent) => void;
  title?: string;
}) {
  return (
    <button
      onClick={onClick}
      title={title}
      className="p-1 rounded border border-brand-border bg-white text-gray-500 hover:text-brand-dark shadow-sm"
    >
      {children}
    </button>
  );
}

function MailBubble({ mail, onAssign }: { mail: CommHubMessage; onAssign: () => void }) {
  const isIncoming = mail.direction === "INCOMING";
  const tableRows = mail.table_rows ?? [];
  const bodyText = stripTableText(mail.body);

  return (
    <div className={`flex flex-col ${isIncoming ? "items-start" : "items-end"}`}>
      <div
        className={`group max-w-[88%] p-4 rounded-lg border shadow-sm relative ${
          isIncoming ? "bg-white border-brand-border" : "bg-amber-50 border-amber-100"
        }`}
      >
        <div className="flex items-center justify-between gap-3 mb-1">
          <span className="text-xs font-semibold text-gray-700 truncate">{mail.subject || "(no subject)"}</span>
          <span className="text-[10px] font-semibold uppercase px-1.5 py-0.5 rounded bg-gray-100 text-gray-600">
            {mail.sent_status}
          </span>
        </div>
        {mail.table_format && (
          <div className="mb-2">
            <span className="text-[10px] font-semibold uppercase px-1.5 py-0.5 rounded bg-slate-100 text-slate-700">
              {mail.table_format === "PO_MATERIALS" ? "PO Material Table" : "Supplier Reply Table"}
            </span>
          </div>
        )}
        {bodyText && (
          <p className="text-sm text-gray-800 leading-relaxed whitespace-pre-wrap">
            {truncate(bodyText, tableRows.length > 0 ? 1200 : 600)}
          </p>
        )}
        {tableRows.length > 0 && <ThreadMessageTable rows={tableRows} />}
        <div className="mt-2 flex items-center gap-2 text-[10px] text-gray-400 flex-wrap">
          <span>{fmtTime(mail.sent_at ?? mail.received_at ?? mail.created_at)}</span>
          <span>·</span>
          <span>{mail.mail_type || mail.source || "MAIL"}</span>
          <span>·</span>
          <span>{isIncoming ? (mail.sender_email || mail.supplier_name || "Supplier") : (mail.supplier_name ?? "You")}</span>
        </div>
        <button
          onClick={onAssign}
          className="absolute -left-9 top-2 opacity-0 group-hover:opacity-100 p-1.5 rounded-full bg-white border border-brand-border text-gray-500 hover:text-signal-red shadow"
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
    <div className="mt-3 overflow-x-auto border border-brand-border rounded bg-white">
      <table className="min-w-full text-xs">
        <thead className="bg-slate-100">
          <tr>
            {["CRM No", "Material Name", "Qty", "UOM", "Due Date", "Status", "Commitment Date", "Remark"].map((header) => (
              <th
                key={header}
                className="text-left px-2 py-1.5 font-semibold text-slate-700 border-b border-brand-border whitespace-nowrap"
              >
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={`${row.crm_no || row.material_name || "row"}-${index}`} className="border-t border-brand-border">
              <td className="px-2 py-1.5 whitespace-nowrap font-mono">{row.crm_no || "-"}</td>
              <td className="px-2 py-1.5 max-w-[280px] truncate" title={row.material_name || ""}>
                {row.material_name || "-"}
              </td>
              <td className="px-2 py-1.5 whitespace-nowrap">{fmtTableQty(row.qty)}</td>
              <td className="px-2 py-1.5 whitespace-nowrap">{row.uom || "-"}</td>
              <td className="px-2 py-1.5 whitespace-nowrap">{fmtTableDate(row.due_date)}</td>
              <td className="px-2 py-1.5 whitespace-nowrap">{row.status || "-"}</td>
              <td className="px-2 py-1.5 whitespace-nowrap">{fmtTableDate(row.commitment_date)}</td>
              <td className="px-2 py-1.5 max-w-[220px] truncate" title={row.remark || ""}>
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
// Task Panel
// ─────────────────────────────────────────────────────────────────────────────
function TaskPanel({
  open,
  onToggle,
  tasks,
  contextLabel,
  onCreate,
  onToggleDone,
}: {
  open: boolean;
  onToggle: () => void;
  tasks: CommunicationTask[];
  contextLabel: string;
  onCreate: () => void;
  onToggleDone: (t: CommunicationTask) => void;
}) {
  const openCount = tasks.filter((t) => t.status !== "DONE").length;
  const overdueCount = tasks.filter(
    (t) => t.status !== "DONE" && t.due_date && new Date(t.due_date).getTime() < Date.now(),
  ).length;
  const highestSignal: TaskSignal = tasks.reduce<TaskSignal>(
    (acc, t) => (signalRank(t.signal) > signalRank(acc) ? (t.signal as TaskSignal) : acc),
    "GREEN",
  );

  if (!open) {
    return (
      <aside className="w-[72px] border-l border-brand-border bg-white flex flex-col items-center py-4 relative">
        <button
          onClick={onToggle}
          className="p-2 rounded hover:bg-gray-100 text-gray-500 relative"
          title="Open task panel"
        >
          <CheckCircle2 size={22} />
          {overdueCount > 0 && (
            <span className="absolute -top-0.5 -right-0.5 w-2.5 h-2.5 rounded-full bg-signal-red border-2 border-white" />
          )}
        </button>
        <div className="my-3 h-px w-8 bg-gray-100" />
        <span
          className="[writing-mode:vertical-lr] text-[11px] font-bold text-brand-muted uppercase tracking-widest py-4"
          style={{ transform: "rotate(180deg)" }}
        >
          Tasks ({openCount})
        </span>
        <div className="mt-auto flex flex-col items-center gap-3">
          <button
            onClick={onCreate}
            className="w-10 h-10 bg-signal-red text-white rounded-full shadow-md hover:opacity-90 flex items-center justify-center"
            title="New task"
          >
            <Plus size={18} />
          </button>
          <div className={`px-2 py-1 rounded text-[9px] font-bold uppercase ${SIGNAL_CHIP[highestSignal] ?? ""}`}>
            {SIGNAL_LABEL[highestSignal] ?? highestSignal}
          </div>
        </div>
      </aside>
    );
  }

  return (
    <aside className="w-[320px] border-l border-brand-border bg-white flex flex-col">
      <div className="px-4 h-12 flex items-center justify-between border-b border-brand-border">
        <div className="flex flex-col">
          <span className="font-semibold text-sm text-brand-dark">Task Center ({openCount})</span>
          <span className="text-[10px] text-brand-muted truncate max-w-[200px]">{contextLabel}</span>
        </div>
        <div className="flex items-center gap-1">
          <button onClick={onCreate} className="p-1.5 rounded hover:bg-gray-100 text-signal-red" title="New task">
            <Plus size={16} />
          </button>
          <button onClick={onToggle} className="p-1.5 rounded hover:bg-gray-100 text-gray-500" title="Collapse">
            <ChevronRight size={16} />
          </button>
        </div>
      </div>
      <div className="flex-1 overflow-y-auto px-3 py-3 space-y-4">
        {tasks.length === 0 ? (
          <EmptyState icon={<CheckCircle2 size={20} />}>
            No tasks yet. Use Assign to create one.
          </EmptyState>
        ) : (
          STATUS_GROUPS.map((g) => {
            const groupTasks = tasks.filter((t) => t.status === g.key);
            if (!groupTasks.length) return null;
            return (
              <div key={g.key}>
                <div className="text-[10px] font-bold uppercase tracking-wider text-brand-muted px-1 mb-2">
                  {g.label} · {groupTasks.length}
                </div>
                <div className="space-y-2">
                  {groupTasks.map((t) => (
                    <TaskCard key={t.id} task={t} onToggleDone={() => onToggleDone(t)} />
                  ))}
                </div>
              </div>
            );
          })
        )}
      </div>
    </aside>
  );
}

function TaskCard({ task, onToggleDone }: { task: CommunicationTask; onToggleDone: () => void }) {
  const due = fmtDueDate(task.due_date);
  const done = task.status === "DONE";
  const sig = (task.signal || "YELLOW") as TaskSignal;
  return (
    <div
      className={`p-3 rounded-lg border bg-white hover:border-signal-red/30 transition-colors ${done ? "opacity-60" : ""} ${
        sig === "BLACK" ? "border-gray-900/40" : sig === "RED" ? "border-red-200" : "border-brand-border"
      }`}
    >
      <div className="flex items-start gap-2 mb-2">
        <button
          onClick={onToggleDone}
          className={`mt-0.5 w-4 h-4 rounded-full border-2 grid place-items-center shrink-0 ${
            done ? "bg-emerald-500 border-emerald-500" : "border-gray-300 hover:border-signal-red"
          }`}
          title={done ? "Reopen" : "Mark done"}
        >
          {done && <CheckCircle2 size={10} className="text-white" />}
        </button>
        <div className="flex-1 min-w-0">
          <p className={`text-xs font-semibold leading-snug ${done ? "line-through text-brand-muted" : "text-brand-dark"}`}>
            {task.title}
          </p>
          {(task.supplier_po_no || task.supplier_name) && (
            <p className="text-[10px] text-brand-muted truncate mt-0.5">
              {task.supplier_po_no && <>#{task.supplier_po_no} · </>}
              {task.supplier_name}
            </p>
          )}
        </div>
        <span className={`w-2 h-2 rounded-full shrink-0 mt-1.5 ${SIGNAL_DOT[sig] ?? "bg-gray-300"}`} />
      </div>
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded ${PRIORITY_CHIP[task.priority as TaskPriority] ?? "bg-gray-100 text-gray-600"}`}>
            {task.priority}
          </span>
          {task.assigned_to && (
            <span className="text-[10px] text-brand-muted truncate max-w-[100px]">
              @{task.assigned_to}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2 text-[10px] text-brand-muted">
          {task.linked_mail_id && <MessagesSquare size={11} />}
          {task.comments_count > 0 && <span>{task.comments_count}c</span>}
          <span className={due.overdue && !done ? "text-signal-red font-semibold" : ""}>{due.text}</span>
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Assign Modal
// ─────────────────────────────────────────────────────────────────────────────
function AssignModal({
  seed,
  suppliers,
  onCancel,
  onSave,
}: {
  seed: Partial<CommunicationTaskCreate>;
  suppliers: string[];
  onCancel: () => void;
  onSave: (payload: CommunicationTaskCreate) => void;
}) {
  const [title, setTitle] = useState(seed.title ?? "");
  const [description, setDescription] = useState(seed.description ?? "");
  const [supplierName, setSupplierName] = useState(seed.supplier_name ?? "");
  const [poNo, setPoNo] = useState(seed.supplier_po_no ?? "");
  const [linkedMailId] = useState(seed.linked_mail_id ?? null);
  const [procurementId] = useState(seed.procurement_record_id ?? null);
  const [priority, setPriority] = useState<TaskPriority>((seed.priority as TaskPriority) ?? "P2");
  const [status, setStatus] = useState<TaskStatus>((seed.status as TaskStatus) ?? "TODO");
  const [signal, setSignal] = useState<TaskSignal>((seed.signal as TaskSignal) ?? "YELLOW");
  const [assignedTo, setAssignedTo] = useState(seed.assigned_to ?? ASSIGNEES[0]);
  const [watchers, setWatchers] = useState<string[]>(seed.watchers ?? []);
  const [dueDate, setDueDate] = useState<string>(seed.due_date ? toDatetimeLocal(seed.due_date) : "");
  const [reminder, setReminder] = useState<string>("");
  const [submitting, setSubmitting] = useState(false);

  const supplierOptions = useMemo(() => {
    const set = new Set(suppliers);
    if (supplierName) set.add(supplierName);
    return Array.from(set);
  }, [suppliers, supplierName]);

  const buildPayload = (): CommunicationTaskCreate => ({
    title: title.trim(),
    description: description || undefined,
    supplier_name: supplierName || null,
    supplier_po_no: poNo || null,
    procurement_record_id: procurementId ?? null,
    linked_mail_id: linkedMailId ?? null,
    assigned_to: assignedTo || null,
    assigned_by: "Admin User",
    watchers,
    priority,
    status,
    signal,
    due_date: dueDate ? new Date(dueDate).toISOString() : null,
    reminder_at: reminder ? new Date(reminder).toISOString() : null,
  });

  const submit = async (notify: boolean) => {
    if (!title.trim()) return;
    setSubmitting(true);
    try {
      onSave(buildPayload());
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/40 grid place-items-center p-4" onClick={onCancel}>
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="px-5 py-3 border-b border-brand-border flex items-center justify-between">
          <div className="flex items-center gap-2">
            <UserPlus size={16} className="text-signal-red" />
            <span className="font-semibold">Assign Action</span>
          </div>
          <button className="p-1 rounded hover:bg-gray-100" onClick={onCancel}>
            <X size={18} />
          </button>
        </div>
        <div className="p-5 grid grid-cols-2 gap-4 max-h-[70vh] overflow-y-auto">
          <Field label="Task title" full>
            <input
              autoFocus
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="input"
              placeholder="e.g. Confirm dispatch date"
            />
          </Field>
          <Field label="Description" full>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              className="input resize-none"
              placeholder="Add context, expected outcome…"
            />
          </Field>

          <Field label="Supplier">
            <input
              list="supplier-list"
              value={supplierName}
              onChange={(e) => setSupplierName(e.target.value)}
              className="input"
            />
            <datalist id="supplier-list">
              {supplierOptions.map((s) => (
                <option key={s} value={s} />
              ))}
            </datalist>
          </Field>
          <Field label="PO number">
            <input value={poNo} onChange={(e) => setPoNo(e.target.value)} className="input" placeholder="#45021" />
          </Field>

          <Field label="Priority">
            <select value={priority} onChange={(e) => setPriority(e.target.value as TaskPriority)} className="input">
              {(["P0", "P1", "P2", "P3"] as TaskPriority[]).map((p) => (
                <option key={p} value={p}>{p}</option>
              ))}
            </select>
          </Field>
          <Field label="Signal">
            <select value={signal} onChange={(e) => setSignal(e.target.value as TaskSignal)} className="input">
              <option value="GREEN">● Green — On Track</option>
              <option value="YELLOW">● Yellow — Reminder</option>
              <option value="RED">● Red — Delayed</option>
              <option value="BLACK">● Black — Critical</option>
            </select>
          </Field>

          <Field label="Due date">
            <input type="datetime-local" value={dueDate} onChange={(e) => setDueDate(e.target.value)} className="input" />
          </Field>
          <Field label="Reminder">
            <input type="datetime-local" value={reminder} onChange={(e) => setReminder(e.target.value)} className="input" />
          </Field>

          <Field label="Assigned to">
            <select value={assignedTo} onChange={(e) => setAssignedTo(e.target.value)} className="input">
              {ASSIGNEES.map((a) => (
                <option key={a} value={a}>{a}</option>
              ))}
            </select>
          </Field>
          <Field label="Status">
            <select value={status} onChange={(e) => setStatus(e.target.value as TaskStatus)} className="input">
              {STATUS_GROUPS.map((s) => (
                <option key={s.key} value={s.key}>{s.label}</option>
              ))}
            </select>
          </Field>

          <Field label="Watchers" full>
            <div className="flex flex-wrap gap-1.5">
              {ASSIGNEES.filter((a) => a !== assignedTo).map((a) => {
                const on = watchers.includes(a);
                return (
                  <button
                    key={a}
                    type="button"
                    onClick={() =>
                      setWatchers((prev) => (on ? prev.filter((x) => x !== a) : [...prev, a]))
                    }
                    className={`text-[11px] px-2 py-1 rounded-full border ${
                      on
                        ? "bg-red-50 border-signal-red/30 text-signal-red"
                        : "border-brand-border text-brand-muted hover:bg-gray-50"
                    }`}
                  >
                    {on ? "✓ " : "+ "}
                    {a}
                  </button>
                );
              })}
            </div>
          </Field>
        </div>
        <div className="px-5 py-3 border-t border-brand-border flex justify-end gap-2">
          <button className="btn-ghost" onClick={onCancel} disabled={submitting}>
            Cancel
          </button>
          <button
            className="btn-ghost border border-brand-border"
            onClick={() => void submit(false)}
            disabled={submitting || !title.trim()}
          >
            Save Task
          </button>
          <button
            className="btn-primary"
            onClick={() => void submit(true)}
            disabled={submitting || !title.trim()}
          >
            {submitting ? <Loader2 size={14} className="animate-spin" /> : <Bell size={14} />}
            <span className="ml-1.5">Save &amp; Notify</span>
          </button>
        </div>
      </div>
      <style jsx>{`
        :global(.input) {
          width: 100%;
          padding: 8px 10px;
          font-size: 13px;
          border: 1px solid #e5e7eb;
          border-radius: 6px;
          background: #fff;
          outline: none;
        }
        :global(.input:focus) {
          border-color: #e11d2e;
        }
      `}</style>
    </div>
  );
}

function Field({ label, children, full }: { label: string; children: React.ReactNode; full?: boolean }) {
  return (
    <div className={full ? "col-span-2" : ""}>
      <div className="text-[10px] uppercase tracking-wider text-brand-muted font-semibold mb-1">
        {label}
      </div>
      {children}
    </div>
  );
}

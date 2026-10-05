"use client";

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import {
  ListChecks,
  AlertTriangle,
  Clock,
  CalendarClock,
  Factory,
  Users,
  Flame,
  CheckCircle2,
  RefreshCcw,
  Plus,
  X,
  MessageSquare,
  History,
  Mail,
  Link2,
  ArrowUpCircle,
  ChevronDown,
  ChevronRight,
  Sparkles,
  Lock,
  Paperclip,
  Settings2,
  PanelRightClose,
  PanelRightOpen,
} from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { LanguageToggle, useT } from "@/lib/i18n";
import PageHeader from "@/components/layout/PageHeader";
import { AssigneePicker, WatcherPicker } from "@/components/tasks/AssigneePicker";
import TaskCreateForm from "@/components/tasks/TaskCreateForm";
import {
  AssignedByMePanel,
  BoardSettingsModal,
  CommentComposer,
  QuickFilterChips,
  TaskAttachmentsSection,
  columnDot,
  groupTasks,
  matchesQuickFilter,
  useBoardColumns,
  type QuickFilter,
  type TaskAttachmentAdapter,
} from "@/components/tasks/board";
import type {
  CommunicationTask,
  TaskActivity,
  TaskAssignee,
  TaskBoardColumn,
  TaskComment,
  TaskSource,
  TaskStatus,
} from "@/lib/types";

type DashboardResult = Awaited<ReturnType<typeof api.getTasksDashboard>>;

const SOURCE_OPTIONS: { value: TaskSource | ""; label: string }[] = [
  { value: "", label: "All sources" },
  { value: "SUPPLIER", label: "Supplier" },
  { value: "CUSTOMER", label: "Customer" },
  { value: "INTERNAL", label: "Internal" },
  { value: "ESCALATION", label: "Escalation" },
];

const PRIORITY_OPTS = ["LOW", "MEDIUM", "HIGH"];

const PRIORITY_BADGE: Record<string, string> = {
  HIGH: "bg-rose-100 text-rose-700",
  MEDIUM: "bg-amber-100 text-amber-700",
  LOW: "bg-subtle text-brand-muted",
};

const SOURCE_BADGE: Record<string, string> = {
  SUPPLIER: "bg-violet-100 text-violet-700",
  CUSTOMER: "bg-cyan-100 text-cyan-700",
  INTERNAL: "bg-subtle text-brand-muted",
  ESCALATION: "bg-rose-100 text-rose-700",
};

const staffAttachments: TaskAttachmentAdapter = {
  list: (id) => api.listTaskAttachments(id),
  upload: (id, file) => api.uploadTaskAttachment(id, file),
  remove: (id, attId) => api.deleteTaskAttachment(id, attId),
  downloadUrl: (attId) => `/api/attachments/${attId}/download`,
};

const PANEL_KEY = "tasks-assigned-panel";

function signalDot(signal?: string | null) {
  switch ((signal || "").toUpperCase()) {
    case "BLACK":
      return "bg-black";
    case "RED":
      return "bg-rose-500";
    case "YELLOW":
      return "bg-amber-400";
    case "GREEN":
      return "bg-green-500";
    default:
      return "bg-subtle";
  }
}

function fmtDate(value?: string | null) {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleDateString();
  } catch {
    return value;
  }
}

function fmtDateTime(value?: string | null) {
  if (!value) return "";
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

function ageingDays(value?: string | null) {
  if (!value) return null;
  const created = new Date(value).getTime();
  if (Number.isNaN(created)) return null;
  return Math.max(0, Math.floor((Date.now() - created) / 86400000));
}

function isOverdue(t: CommunicationTask) {
  if (!t.due_date || t.status === "DONE") return false;
  return new Date(t.due_date).getTime() < Date.now();
}

function Kpi({
  label,
  value,
  icon,
  tone,
}: {
  label: string;
  value: number | string | undefined;
  icon: React.ReactNode;
  tone: string;
}) {
  return (
    <div className="card p-3 flex items-center gap-3">
      <div className={`h-9 w-9 rounded-lg flex items-center justify-center ${tone}`}>{icon}</div>
      <div>
        <div className="text-[11px] text-brand-muted leading-none">{label}</div>
        <div className="text-lg font-semibold mt-1 leading-none">{value ?? "—"}</div>
      </div>
    </div>
  );
}

export default function TasksPage() {
  const { t } = useT();
  const { user, hasRole } = useAuth();
  const isAdmin = hasRole("admin");
  const searchParams = useSearchParams();
  const customerMailIdParam = searchParams.get("customer_mail_id");
  const customerMailId = customerMailIdParam ? Number(customerMailIdParam) : null;

  const board = useBoardColumns(api.taskBoardColumns);

  const [dashboard, setDashboard] = useState<DashboardResult | null>(null);
  const [tasks, setTasks] = useState<CommunicationTask[]>([]);
  const [source, setSource] = useState<TaskSource | "">("");
  const [status, setStatus] = useState<TaskStatus | "">("");
  const [priority, setPriority] = useState("");
  const [assigned, setAssigned] = useState("");
  const [supplier, setSupplier] = useState("");
  const [search, setSearch] = useState("");
  const [quick, setQuick] = useState<QuickFilter>("all");
  const [view, setView] = useState<"kanban" | "table">("kanban");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [selected, setSelected] = useState<CommunicationTask | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [showBoardSettings, setShowBoardSettings] = useState(false);
  const [showPanel, setShowPanel] = useState(true);
  const [assignees, setAssignees] = useState<TaskAssignee[]>([]);
  const [suppliers, setSuppliers] = useState<string[]>([]);

  useEffect(() => {
    try {
      if (window.localStorage.getItem(PANEL_KEY) === "closed") setShowPanel(false);
    } catch {
      /* per-device preference only */
    }
  }, []);

  const togglePanel = () => {
    setShowPanel((open) => {
      try {
        window.localStorage.setItem(PANEL_KEY, open ? "closed" : "open");
      } catch {
        /* ignore */
      }
      return !open;
    });
  };

  useEffect(() => {
    api.listAssignees().then(setAssignees).catch(() => setAssignees([]));
    api
      .listSuppliers()
      .then((rows) => setSuppliers(rows.map((s) => s.supplier_name).filter(Boolean)))
      .catch(() => setSuppliers([]));
  }, []);

  const refresh = useCallback(async () => {
    setBusy(true);
    try {
      const [dash, list] = await Promise.all([
        api.getTasksDashboard(),
        api.listUnifiedTasks({
          task_source: source || undefined,
          status: status || undefined,
          assigned_to: assigned || undefined,
          supplier_name: supplier || undefined,
          customer_mail_id: customerMailId ?? undefined,
          limit: 500,
        }),
      ]);
      setDashboard(dash);
      setTasks(list);
    } catch (err) {
      setMessage((err as Error).message);
    } finally {
      setBusy(false);
    }
  }, [source, status, assigned, supplier, customerMailId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // Search + priority, before the quick-filter chips (so chip counts reflect them).
  const searched = useMemo(() => {
    return tasks.filter((task) => {
      if (priority && task.priority !== priority) return false;
      if (search) {
        const hay = `${task.title} ${task.description || ""} ${task.supplier_name || ""} ${task.supplier_po_no || ""} ${task.material_name || ""}`.toLowerCase();
        if (!hay.includes(search.toLowerCase())) return false;
      }
      return true;
    });
  }, [tasks, priority, search]);

  const filtered = useMemo(
    () => searched.filter((task) => matchesQuickFilter(task, quick, user)),
    [searched, quick, user],
  );

  const grouped = useMemo(() => groupTasks(filtered, board.visible), [filtered, board.visible]);

  const taskCounts = useMemo(() => {
    const m: Record<string, number> = {};
    tasks.forEach((task) => {
      m[task.status] = (m[task.status] ?? 0) + 1;
    });
    return m;
  }, [tasks]);

  const moveStatus = useCallback(
    async (task: CommunicationTask, next: TaskStatus) => {
      setBusy(true);
      try {
        const updated = await api.updateTask(task.id, { status: next });
        setSelected((cur) => (cur && cur.id === task.id ? updated : cur));
        await refresh();
      } catch (err) {
        setMessage((err as Error).message);
      } finally {
        setBusy(false);
      }
    },
    [refresh],
  );

  const exportCsv = () => {
    const headers = [
      "id",
      "title",
      "status",
      "priority",
      "source",
      "supplier",
      "po",
      "material",
      "assigned_to",
      "assigned_by",
      "due_date",
    ];
    const rows = filtered.map((task) =>
      [
        task.id,
        `"${(task.title || "").replace(/"/g, '""')}"`,
        board.byKey.get(task.status)?.label ?? task.status,
        task.priority,
        task.task_source || "SUPPLIER",
        `"${(task.supplier_name || "").replace(/"/g, '""')}"`,
        task.supplier_po_no || "",
        `"${(task.material_name || "").replace(/"/g, '""')}"`,
        task.assigned_to || "",
        task.assigned_by || "",
        task.due_date || "",
      ].join(","),
    );
    const blob = new Blob([[headers.join(","), ...rows].join("\n")], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `tasks-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="page-stack">
      <PageHeader
        title={t("Task Manager")}
        description={t("Track supplier, customer, internal and escalation work in kanban or table view.")}
        icon={ListChecks}
        actions={
          <>
            <LanguageToggle />
            <div className="inline-flex border border-brand-border rounded-md overflow-hidden text-xs">
              <button
                type="button"
                onClick={() => setView("kanban")}
                className={`px-3 py-1.5 ${view === "kanban" ? "bg-ink text-white" : "bg-card text-brand-dark"}`}
              >
                {t("Kanban")}
              </button>
              <button
                type="button"
                onClick={() => setView("table")}
                className={`px-3 py-1.5 ${view === "table" ? "bg-ink text-white" : "bg-card text-brand-dark"}`}
              >
                {t("Table")}
              </button>
            </div>
            {isAdmin && (
              <button type="button" onClick={() => setShowBoardSettings(true)} className="btn-outline text-xs" title={t("Board columns")}>
                <Settings2 size={13} /> {t("Board")}
              </button>
            )}
            <button type="button" onClick={exportCsv} className="btn-outline text-xs">
              {t("Export")}
            </button>
            <button type="button" onClick={() => setShowCreate(true)} className="btn-dark text-xs">
              <Plus size={13} /> {t("Create Task")}
            </button>
            <button type="button" onClick={refresh} disabled={busy} className="btn-outline text-xs">
              <RefreshCcw size={13} className={busy ? "animate-spin" : ""} /> {t("Refresh")}
            </button>
          </>
        }
      />

      {message && (
        <div className="card p-2.5 text-xs text-rose-700 bg-rose-50 flex items-center justify-between">
          <span>{message}</span>
          <button onClick={() => setMessage(null)}>
            <X size={13} />
          </button>
        </div>
      )}

      {/* KPI strip */}
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-2.5">
        <Kpi label={t("Total")} value={dashboard?.total_tasks} icon={<ListChecks size={16} className="text-brand-muted" />} tone="bg-subtle" />
        <Kpi label={t("Open")} value={(dashboard?.total_tasks ?? 0) - (dashboard?.done ?? 0)} icon={<Clock size={16} className="text-blue-600" />} tone="bg-blue-100" />
        <Kpi label={t("Overdue")} value={dashboard?.overdue} icon={<AlertTriangle size={16} className="text-rose-600" />} tone="bg-rose-100" />
        <Kpi label={t("Due Today")} value={dashboard?.due_today} icon={<CalendarClock size={16} className="text-amber-600" />} tone="bg-amber-100" />
        <Kpi label={t("Supplier")} value={dashboard?.supplier_tasks} icon={<Factory size={16} className="text-violet-600" />} tone="bg-violet-100" />
        <Kpi label={t("Customer")} value={dashboard?.customer_tasks} icon={<Users size={16} className="text-cyan-600" />} tone="bg-cyan-100" />
        <Kpi label={t("Escalations")} value={dashboard?.escalation_tasks} icon={<Flame size={16} className="text-orange-600" />} tone="bg-orange-100" />
        <Kpi label={t("Completed")} value={dashboard?.done} icon={<CheckCircle2 size={16} className="text-green-600" />} tone="bg-green-100" />
      </div>

      {/* Filter bar */}
      <div className="card p-2.5 space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t("Search title, PO, material…")}
            className="border border-brand-border rounded px-2 py-1.5 text-sm flex-1 min-w-[180px]"
          />
          <select value={source} onChange={(e) => setSource(e.target.value as TaskSource | "")} className="border border-brand-border rounded px-2 py-1.5 text-sm">
            {SOURCE_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{t(o.label)}</option>
            ))}
          </select>
          <select value={status} onChange={(e) => setStatus(e.target.value as TaskStatus | "")} className="border border-brand-border rounded px-2 py-1.5 text-sm">
            <option value="">{t("All statuses")}</option>
            {board.columns.map((c) => (
              <option key={c.key} value={c.key}>{t(c.label)}</option>
            ))}
          </select>
          <select value={priority} onChange={(e) => setPriority(e.target.value)} className="border border-brand-border rounded px-2 py-1.5 text-sm">
            <option value="">{t("All priority")}</option>
            {PRIORITY_OPTS.map((p) => (
              <option key={p} value={p}>{t(p)}</option>
            ))}
          </select>
          <input
            type="text"
            value={supplier}
            onChange={(e) => setSupplier(e.target.value)}
            placeholder={t("Supplier")}
            className="border border-brand-border rounded px-2 py-1.5 text-sm w-32"
          />
          <input
            type="text"
            value={assigned}
            onChange={(e) => setAssigned(e.target.value)}
            placeholder={t("Assignee")}
            className="border border-brand-border rounded px-2 py-1.5 text-sm w-28"
          />
          <button
            type="button"
            onClick={togglePanel}
            className="btn-outline text-xs ml-auto"
            title={showPanel ? t("Hide “Assigned by you”") : t("Show “Assigned by you”")}
          >
            {showPanel ? <PanelRightClose size={13} /> : <PanelRightOpen size={13} />}
            <span className="hidden sm:inline">{t("Assigned by you")}</span>
          </button>
        </div>
        <QuickFilterChips value={quick} onChange={setQuick} tasks={searched} user={user} />
      </div>

      {/* Board / Table + "Assigned by you" */}
      <div className="flex flex-col gap-3 xl:flex-row xl:items-start">
        <div className="min-w-0 flex-1">
          {view === "kanban" ? (
            <div className="flex gap-3 overflow-x-auto pb-3">
              {board.visible.map((col) => {
                const list = grouped.get(col.key) ?? [];
                return (
                  <div key={col.key} className="flex-shrink-0 w-72">
                    <div className="rounded-lg border border-brand-border bg-card shadow-sm">
                      <div className="flex items-center justify-between px-3 py-2 border-b border-brand-border">
                        <div className="flex items-center gap-2">
                          <span className={`h-2 w-2 rounded-full ${columnDot(col.color)}`} />
                          <span className="text-xs font-semibold">{t(col.label)}</span>
                        </div>
                        <span className="text-[11px] text-brand-muted bg-subtle rounded-full px-1.5">{list.length}</span>
                      </div>
                      <div className="p-2 space-y-2 max-h-[calc(100vh-380px)] overflow-y-auto">
                        {list.map((task) => (
                          <TaskCard key={task.id} task={task} onOpen={() => setSelected(task)} />
                        ))}
                        {list.length === 0 && (
                          <div className="text-[11px] text-brand-muted text-center py-4">{t("No tasks")}</div>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="card p-3 overflow-x-auto">
              <table className="w-full text-xs">
                <thead className="text-brand-muted border-b border-brand-border">
                  <tr className="text-left">
                    <th className="py-2 pr-3">{t("Title")}</th>
                    <th className="py-2 pr-3">{t("Source")}</th>
                    <th className="py-2 pr-3">{t("Status")}</th>
                    <th className="py-2 pr-3">{t("Priority")}</th>
                    <th className="py-2 pr-3">{t("Supplier / PO")}</th>
                    <th className="py-2 pr-3">{t("Assignee")}</th>
                    <th className="py-2 pr-3">{t("Assigned by")}</th>
                    <th className="py-2 pr-3">{t("Due")}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-brand-border">
                  {filtered.map((task) => {
                    const col = board.byKey.get(task.status);
                    return (
                      <tr key={task.id} className="hover:bg-subtle cursor-pointer" onClick={() => setSelected(task)}>
                        <td className="py-2 pr-3">
                          <div className="font-medium">{task.title}</div>
                          <div className="text-brand-muted truncate max-w-[280px]">{task.material_name}</div>
                        </td>
                        <td className="py-2 pr-3">
                          <span className={`text-[10px] px-1.5 py-0.5 rounded ${SOURCE_BADGE[task.task_source || "SUPPLIER"]}`}>
                            {t(task.task_source || "SUPPLIER")}
                          </span>
                        </td>
                        <td className="py-2 pr-3">
                          <span className="inline-flex items-center gap-1.5">
                            <span className={`h-2 w-2 rounded-full ${columnDot(col?.color)}`} />
                            {col ? t(col.label) : task.status}
                          </span>
                        </td>
                        <td className="py-2 pr-3">
                          <span className={`text-[10px] px-1.5 py-0.5 rounded ${PRIORITY_BADGE[task.priority] || ""}`}>{t(task.priority)}</span>
                        </td>
                        <td className="py-2 pr-3">
                          <div>{task.supplier_name || "—"}</div>
                          <div className="text-brand-muted">{task.supplier_po_no || ""}</div>
                        </td>
                        <td className="py-2 pr-3">{task.assigned_to || "—"}</td>
                        <td className="py-2 pr-3">{task.assigned_by || "—"}</td>
                        <td className={`py-2 pr-3 whitespace-nowrap ${isOverdue(task) ? "text-rose-600 font-semibold" : ""}`}>
                          {fmtDate(task.due_date)}
                        </td>
                      </tr>
                    );
                  })}
                  {filtered.length === 0 && (
                    <tr>
                      <td className="py-3 text-brand-muted" colSpan={8}>{t("No tasks match these filters.")}</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {showPanel && (
          <AssignedByMePanel tasks={tasks} user={user} columns={board.byKey} onOpen={setSelected} />
        )}
      </div>

      {selected && (
        <TaskDrawer
          task={selected}
          assignees={assignees}
          columns={board.columns}
          onClose={() => setSelected(null)}
          onChanged={async (task) => {
            setSelected(task);
            await refresh();
          }}
          onMove={moveStatus}
        />
      )}

      {showCreate && (
        <TaskCreateForm
          assignees={assignees}
          suppliers={suppliers}
          statusOptions={board.visible.map((c) => ({ key: c.key, label: t(c.label) }))}
          uploadAttachment={(id, file) => api.uploadTaskAttachment(id, file)}
          onCancel={() => setShowCreate(false)}
          onSave={async (payload) => {
            const created = await api.createTask(payload);
            setShowCreate(false);
            void refresh();
            return created;
          }}
        />
      )}

      {showBoardSettings && (
        <BoardSettingsModal
          columns={board.columns}
          colors={board.colors}
          taskCounts={taskCounts}
          onClose={() => setShowBoardSettings(false)}
          onSave={async (cols) => {
            const res = await api.saveTaskBoardColumns(cols);
            board.setColumns(res.columns);
            await refresh();
          }}
        />
      )}
    </div>
  );
}

function TaskCard({ task, onOpen }: { task: CommunicationTask; onOpen: () => void }) {
  const { t } = useT();
  const overdue = isOverdue(task);
  const age = ageingDays(task.created_at);
  return (
    <button
      type="button"
      onClick={onOpen}
      className="w-full rounded-lg border border-brand-border bg-card p-2.5 text-left shadow-sm transition hover:border-brand-border hover:shadow-md"
    >
      <div className="flex items-start justify-between gap-2">
        <span className="text-sm font-medium leading-snug line-clamp-2">{task.title}</span>
        <span className={`text-[10px] px-1.5 py-0.5 rounded font-semibold ${PRIORITY_BADGE[task.priority] || ""}`}>
          {t(task.priority)}
        </span>
      </div>
      <div className="flex flex-wrap items-center gap-1.5 mt-2">
        <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${SOURCE_BADGE[task.task_source || "SUPPLIER"]}`}>
          {t(task.task_source || "SUPPLIER")}
        </span>
        <span className="inline-flex items-center gap-1 text-[10px] text-brand-muted">
          <span className={`h-2 w-2 rounded-full ${signalDot(task.signal)}`} /> {task.signal}
        </span>
        {(task.escalation_level ?? 0) > 0 && (
          <span className="inline-flex items-center gap-0.5 text-[10px] text-rose-700 bg-rose-50 px-1 rounded">
            <Flame size={10} /> L{task.escalation_level}
          </span>
        )}
      </div>
      {(task.supplier_name || task.supplier_po_no) && (
        <div className="text-[11px] text-brand-muted mt-1.5 truncate">
          {task.supplier_name || "—"}
          {task.supplier_po_no ? ` · ${task.supplier_po_no}` : ""}
        </div>
      )}
      {task.material_name && <div className="text-[11px] text-brand-muted truncate">{task.material_name}</div>}
      <div className="flex items-center justify-between mt-2 text-[11px] text-brand-muted">
        <span className={overdue ? "text-rose-600 font-semibold" : ""}>
          {overdue ? t("Overdue") : t("Due")} {fmtDate(task.due_date)}
        </span>
        <span className="flex items-center gap-2">
          {task.linked_mail_id || task.customer_mail_id ? <Mail size={12} /> : null}
          {(task.attachment_count ?? 0) > 0 && (
            <span className="flex items-center gap-0.5">
              <Paperclip size={11} /> {task.attachment_count}
            </span>
          )}
          {age != null && <span>{t("{n}d", { n: age })}</span>}
          {task.comments_count > 0 && (
            <span className="flex items-center gap-0.5">
              <MessageSquare size={11} /> {task.comments_count}
            </span>
          )}
        </span>
      </div>
      {task.assigned_to && (
        <div className="mt-1.5 flex items-center gap-1">
          <span className="h-5 w-5 rounded-full bg-ink text-white text-[9px] flex items-center justify-center">
            {task.assigned_to.slice(0, 2).toUpperCase()}
          </span>
          <span className="text-[11px] text-brand-muted truncate">{task.assigned_to}</span>
        </div>
      )}
    </button>
  );
}

function TaskDrawer({
  task,
  assignees,
  columns,
  onClose,
  onChanged,
  onMove,
}: {
  task: CommunicationTask;
  assignees: TaskAssignee[];
  columns: TaskBoardColumn[];
  onClose: () => void;
  onChanged: (t: CommunicationTask) => void | Promise<void>;
  onMove: (t: CommunicationTask, s: TaskStatus) => void | Promise<void>;
}) {
  const { t } = useT();
  const { user, hasRole } = useAuth();
  const isAdmin = hasRole("admin");
  const canWrite = hasRole("user");

  const [comments, setComments] = useState<TaskComment[]>([]);
  const [activity, setActivity] = useState<TaskActivity[]>([]);
  const [newComment, setNewComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [summarizing, setSummarizing] = useState(false);
  const [watcherIds, setWatcherIds] = useState<number[]>(task.watchers ?? []);
  const [showActivity, setShowActivity] = useState(false); // admin-only change log, collapsed by default

  // Keep local UI state in sync if the parent refreshes the task object.
  useEffect(() => setWatcherIds(task.watchers ?? []), [task.watchers]);

  // Escape closes the dialog.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const load = useCallback(async () => {
    try {
      const c = await api.listTaskComments(task.id);
      setComments(c);
    } catch {
      /* ignore */
    }
    // The activity log is admin-only (backend enforces it too).
    if (!isAdmin) return;
    try {
      setActivity(await api.listTaskActivity(task.id));
    } catch {
      /* ignore */
    }
  }, [task.id, isAdmin]);

  useEffect(() => {
    void load();
  }, [load]);

  async function submitComment() {
    if (!newComment.trim()) return;
    setBusy(true);
    try {
      await api.addTaskComment(task.id, newComment.trim());
      setNewComment("");
      await load();
    } finally {
      setBusy(false);
    }
  }

  async function patch(body: Parameters<typeof api.updateTask>[1]) {
    setBusy(true);
    try {
      const updated = await api.updateTask(task.id, body);
      await onChanged(updated);
      await load();
    } finally {
      setBusy(false);
    }
  }

  async function escalate() {
    await patch({
      escalation_level: (task.escalation_level ?? 0) + 1,
      priority: "HIGH",
      signal: "RED",
    });
  }

  const statusCol = columns.find((c) => c.key === task.status);
  const sortedComments = [...comments].sort((a, b) => +new Date(a.created_at) - +new Date(b.created_at));
  const sortedActivity = [...activity].sort((a, b) => +new Date(b.created_at) - +new Date(a.created_at));
  // A hidden column stays selectable for the task already in it.
  const statusOptions = columns.filter((c) => !c.hidden || c.key === task.status);

  const Field = ({ label, children }: { label: string; children: ReactNode }) => (
    <div>
      <div className="text-[11px] font-medium uppercase tracking-wide text-brand-muted mb-1">{label}</div>
      {children}
    </div>
  );

  return (
    <div className="fixed inset-0 z-50 grid place-items-center p-2 sm:p-4 bg-black/50" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        className="relative w-full max-w-6xl h-[94vh] bg-card rounded-xl shadow-2xl flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-6 py-4 border-b border-brand-border flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-[11px] text-brand-muted">
              <span className="font-mono">TASK-{task.id}</span>
              <span className="text-gray-300">•</span>
              <span className="inline-flex items-center gap-1">
                <span className={`h-2 w-2 rounded-full ${columnDot(statusCol?.color)}`} />
                {statusCol ? t(statusCol.label) : task.status}
              </span>
              {task.assigned_by && (
                <>
                  <span className="text-gray-300">•</span>
                  <span>{t("Assigned by {name}", { name: task.assigned_by })}</span>
                </>
              )}
            </div>
            <h2 className="text-xl font-semibold text-brand-dark leading-snug">{task.title}</h2>
          </div>
          <button onClick={onClose} className="p-1.5 rounded hover:bg-subtle text-brand-muted" aria-label={t("Close")}>
            <X size={18} />
          </button>
        </div>

        {/* Body: main + sidebar, each scrolling on its own */}
        <div className="flex-1 min-h-0 grid md:grid-cols-[minmax(0,1fr)_340px]">
          {/* MAIN */}
          <div className="min-h-0 overflow-y-auto p-6 space-y-6 md:border-r border-brand-border">
            {task.description && (
              <div>
                <div className="text-[11px] font-medium uppercase tracking-wide text-brand-muted mb-1">{t("Description")}</div>
                <p className="text-sm whitespace-pre-wrap text-brand-dark">{task.description}</p>
              </div>
            )}

            {/* AI Summary */}
            <div className="rounded-lg border border-indigo-100 bg-indigo-50/50 p-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-indigo-900 flex items-center gap-1.5">
                  <Sparkles size={13} /> {t("AI Summary")}
                </span>
                <button
                  className="text-xs font-medium text-indigo-700 hover:text-indigo-900 disabled:opacity-50"
                  disabled={summarizing}
                  onClick={async () => {
                    setSummarizing(true);
                    try {
                      const updated = await api.generateTaskAiSummary(task.id);
                      await onChanged(updated);
                    } catch {
                      alert(t("AI summary unavailable (LLM may be disabled)."));
                    } finally {
                      setSummarizing(false);
                    }
                  }}
                >
                  {summarizing ? t("Generating…") : task.ai_summary ? t("Regenerate") : t("Summarize")}
                </button>
              </div>
              <p className="mt-1.5 text-xs text-brand-dark whitespace-pre-wrap">
                {task.ai_summary || t("No summary yet — click Summarize to generate one from the comments & activity.")}
              </p>
              {task.ai_summary_at && (
                <p className="mt-1 text-[10px] text-brand-muted">
                  {t("by {name}", { name: task.ai_summary_by })} · {fmtDateTime(task.ai_summary_at)}
                </p>
              )}
            </div>

            {/* Attachments */}
            <TaskAttachmentsSection
              taskId={task.id}
              adapter={staffAttachments}
              canUpload={canWrite}
              canRemove={(a) => isAdmin || (a.uploaded_by_kind === "staff" && a.uploaded_by_id === user?.id)}
            />

            {/* Comments — visible to all staff */}
            <div>
              <div className="flex items-center gap-1.5 mb-2">
                <MessageSquare size={14} className="text-brand-muted" />
                <span className="text-sm font-semibold text-brand-dark">{t("Comments")}</span>
                <span className="text-xs text-brand-muted">({sortedComments.length})</span>
              </div>

              <CommentComposer value={newComment} onChange={setNewComment} onSubmit={submitComment} busy={busy} />

              <div className="space-y-2">
                {sortedComments.length === 0 && <div className="text-xs text-brand-muted">{t("No comments yet.")}</div>}
                {sortedComments.map((c) => (
                  <div key={c.id} className="rounded-lg border border-brand-border p-2.5">
                    <div className="flex items-center justify-between text-[11px] text-brand-muted">
                      <span className="font-medium text-brand-dark">{c.created_by || "system"}</span>
                      <span>{fmtDateTime(c.created_at)}</span>
                    </div>
                    <p className="text-sm mt-1 whitespace-pre-wrap text-brand-dark">{c.comment}</p>
                  </div>
                ))}
              </div>
            </div>

            {/* Activity log — admin-only, collapsed dropdown */}
            {isAdmin && (
              <div className="border-t border-brand-border pt-3">
                <button
                  type="button"
                  onClick={() => setShowActivity((s) => !s)}
                  className="flex items-center gap-1.5 text-sm font-semibold text-brand-dark w-full"
                >
                  {showActivity ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
                  <History size={14} className="text-brand-muted" />
                  {t("Activity log")}
                  <span className="text-xs font-normal text-brand-muted">({sortedActivity.length})</span>
                  <span className="ml-auto inline-flex items-center gap-1 text-[10px] font-normal text-amber-700 bg-amber-50 px-1.5 py-0.5 rounded">
                    <Lock size={10} /> {t("Admin only")}
                  </span>
                </button>

                {showActivity && (
                  <div className="mt-3 space-y-2 max-h-72 overflow-y-auto pr-1">
                    {sortedActivity.length === 0 && <div className="text-xs text-brand-muted">{t("No activity recorded.")}</div>}
                    {sortedActivity.map((a) => (
                      <div key={a.id} className="flex gap-2 text-xs">
                        <div className="h-1.5 w-1.5 rounded-full bg-brand-muted mt-1.5 flex-shrink-0" />
                        <div className="min-w-0">
                          <span className="text-brand-dark">
                            {a.activity_type.replace(/_/g, " ").toLowerCase()}
                            {a.new_value ? `: ${a.old_value ? `${a.old_value} → ` : ""}${a.new_value}` : ""}
                          </span>
                          {a.created_by && <span className="text-brand-muted"> · {a.created_by}</span>}
                          <div className="text-[10px] text-brand-muted">{fmtDateTime(a.created_at)}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* SIDEBAR — fields */}
          <aside className="min-h-0 overflow-y-auto p-5 space-y-4 bg-subtle">
            <Field label={t("Status")}>
              <select
                value={task.status}
                onChange={(e) => onMove(task, e.target.value as TaskStatus)}
                className="border border-brand-border rounded-md px-2 py-1.5 text-sm w-full bg-card"
              >
                {statusOptions.map((c) => (
                  <option key={c.key} value={c.key}>{t(c.label)}</option>
                ))}
              </select>
            </Field>

            <div className="grid grid-cols-2 gap-3">
              <Field label={t("Priority")}>
                <select
                  value={task.priority}
                  onChange={(e) => patch({ priority: e.target.value as CommunicationTask["priority"] })}
                  className="border border-brand-border rounded-md px-2 py-1.5 text-sm w-full bg-card"
                >
                  {PRIORITY_OPTS.map((p) => (
                    <option key={p} value={p}>{t(p)}</option>
                  ))}
                </select>
              </Field>
              <Field label={t("Signal")}>
                <div className="px-2 py-1.5 text-sm rounded-md border border-brand-border bg-card flex items-center gap-1.5">
                  <span className={`h-2 w-2 rounded-full ${signalDot(task.signal)}`} /> {task.signal}
                </div>
              </Field>
            </div>

            <Field label={t("Assignee")}>
              <AssigneePicker
                value={task.assigned_to_user_id ?? null}
                assignees={assignees}
                placeholder={t("Unassigned")}
                onChange={(id) => patch({ assigned_to_user_id: id })}
              />
            </Field>

            <Field label={t("Watchers")}>
              <WatcherPicker
                value={watcherIds}
                assignees={assignees}
                onChange={(ids) => {
                  setWatcherIds(ids);
                  void patch({ watchers: ids });
                }}
              />
            </Field>

            {/* Linked context */}
            <div className="rounded-lg border border-brand-border p-3 space-y-1.5 bg-card">
              <div className="text-[11px] font-semibold uppercase tracking-wide text-brand-muted flex items-center gap-1">
                <Link2 size={12} /> {t("Linked context")}
              </div>
              <div className="text-xs flex flex-col gap-1 text-brand-dark">
                <span>{t("Source")}: <b>{t(task.task_source || "SUPPLIER")}</b></span>
                {task.supplier_name && <span>{t("Supplier")}: {task.supplier_name}</span>}
                {task.supplier_po_no && <span>{t("PO")}: {task.supplier_po_no}</span>}
                {task.material_name && <span>{t("Material")}: {task.material_name}</span>}
                {task.linked_mail_id && (
                  <Link href={`/mail-history`} className="text-signal-red underline">
                    {t("Linked supplier mail #{id}", { id: task.linked_mail_id })}
                  </Link>
                )}
                {task.customer_mail_id && (
                  <Link href={`/customer-mails?focus=${task.customer_mail_id}`} className="text-signal-red underline">
                    {t("Customer mail #{id}", { id: task.customer_mail_id })}
                  </Link>
                )}
                <span>{t("Due")}: {fmtDate(task.due_date)}</span>
                {task.assigned_by && <span>{t("Assigned by")}: {task.assigned_by}</span>}
              </div>
            </div>

            <button
              type="button"
              onClick={escalate}
              disabled={busy}
              className="w-full text-sm px-3 py-1.5 rounded-md border border-rose-300 text-rose-700 bg-rose-50 hover:bg-rose-100 flex items-center justify-center gap-1 disabled:opacity-50"
            >
              <ArrowUpCircle size={14} /> {t("Escalate")} (L{(task.escalation_level ?? 0) + 1})
            </button>
          </aside>
        </div>
      </div>
    </div>
  );
}

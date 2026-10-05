"use client";

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
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
  Link2,
  ArrowUpCircle,
  Lock,
  Paperclip,
  PanelRightClose,
  PanelRightOpen,
} from "lucide-react";

import { AttachButton, AttachmentDropArea } from "@/components/attachments/Attachments";
import { AssigneePicker } from "@/components/tasks/AssigneePicker";
import {
  AssignedByMePanel,
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
import { useAuth } from "@/lib/auth";
import { LanguageToggle, useT } from "@/lib/i18n";
import type {
  CommunicationTask,
  CommunicationTaskCreate,
  CommunicationTaskUpdate,
  PortalTaskDashboard,
  TaskAssignee,
  TaskBoardColumn,
  TaskComment,
  TaskSource,
  TaskStatus,
} from "@/lib/types";

// ─── Constants (mirror the admin Task Manager) ──────────────────────────────
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

const PANEL_KEY = "eportal-tasks-assigned-panel";

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

// ─── Adapter + permission contract ──────────────────────────────────────────
export interface PortalTaskAdapter {
  listTasks: (filters?: {
    status?: string;
    task_source?: string;
    supplier_po_no?: string;
    overdue?: boolean;
  }) => Promise<CommunicationTask[]>;
  dashboard: () => Promise<PortalTaskDashboard>;
  boardColumns?: () => Promise<{ columns: TaskBoardColumn[]; colors: string[] }>;
  updateTask?: (id: number, patch: CommunicationTaskUpdate) => Promise<CommunicationTask>;
  createTask?: (payload: CommunicationTaskCreate) => Promise<CommunicationTask>;
  deleteTask?: (id: number) => Promise<void>;
  listAssignees?: () => Promise<TaskAssignee[]>;
  listComments?: (id: number) => Promise<TaskComment[]>;
  addComment?: (id: number, comment: string) => Promise<TaskComment>;
  attachments?: TaskAttachmentAdapter;
}

export interface PortalTaskPermissions {
  canCreate: boolean;
  canEdit: boolean;
  canAssign: boolean;
  canDelete: boolean;
  canComment: boolean;
  readOnly: boolean;
}

function Kpi({
  label,
  value,
  icon,
  tone,
}: {
  label: string;
  value: number | string | undefined;
  icon: ReactNode;
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

export default function PortalTaskWorkspace({
  adapter,
  permissions,
  scopeLabel,
}: {
  adapter: PortalTaskAdapter;
  permissions: PortalTaskPermissions;
  scopeLabel: string;
}) {
  const { t } = useT();
  const { user } = useAuth();
  const board = useBoardColumns(adapter.boardColumns);

  const [dashboard, setDashboard] = useState<PortalTaskDashboard | null>(null);
  const [tasks, setTasks] = useState<CommunicationTask[]>([]);
  const [source, setSource] = useState<TaskSource | "">("");
  const [status, setStatus] = useState<TaskStatus | "">("");
  const [priority, setPriority] = useState("");
  const [search, setSearch] = useState("");
  const [quick, setQuick] = useState<QuickFilter>("all");
  const [view, setView] = useState<"kanban" | "table">("kanban");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [selected, setSelected] = useState<CommunicationTask | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [showPanel, setShowPanel] = useState(true);
  const [assignees, setAssignees] = useState<TaskAssignee[]>([]);

  const internal = !permissions.readOnly;

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
    if (permissions.canAssign && adapter.listAssignees) {
      adapter.listAssignees().then(setAssignees).catch(() => setAssignees([]));
    }
  }, [permissions.canAssign, adapter]);

  const refresh = useCallback(async () => {
    setBusy(true);
    try {
      const [dash, list] = await Promise.all([
        adapter.dashboard().catch(() => null),
        adapter.listTasks({
          task_source: source || undefined,
          status: status || undefined,
        }),
      ]);
      if (dash) setDashboard(dash);
      setTasks(list);
    } catch (err) {
      setMessage((err as Error).message);
    } finally {
      setBusy(false);
    }
  }, [adapter, source, status]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

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

  // Client-side KPI fallback when the dashboard endpoint is unavailable.
  const kpiCounts = useMemo(() => {
    if (dashboard) return dashboard;
    const open = tasks.filter((task) => task.status !== "DONE");
    return {
      total_tasks: tasks.length,
      todo: tasks.filter((task) => task.status === "TODO").length,
      in_progress: tasks.filter((task) => task.status === "IN_PROGRESS").length,
      waiting: tasks.filter((task) => task.status === "WAITING_SUPPLIER" || task.status === "WAITING_CUSTOMER").length,
      done: tasks.filter((task) => task.status === "DONE").length,
      overdue: open.filter((task) => isOverdue(task)).length,
      due_today: 0,
      critical: tasks.filter((task) => task.priority === "HIGH").length,
      supplier_tasks: tasks.filter((task) => (task.task_source || "SUPPLIER") === "SUPPLIER").length,
      customer_tasks: tasks.filter((task) => task.task_source === "CUSTOMER").length,
      internal_tasks: tasks.filter((task) => task.task_source === "INTERNAL").length,
      escalation_tasks: tasks.filter((task) => task.task_source === "ESCALATION").length,
    } satisfies PortalTaskDashboard;
  }, [dashboard, tasks]);

  const grouped = useMemo(() => groupTasks(filtered, board.visible), [filtered, board.visible]);

  const moveStatus = useCallback(
    async (task: CommunicationTask, next: TaskStatus) => {
      if (!adapter.updateTask) return;
      setBusy(true);
      try {
        const updated = await adapter.updateTask(task.id, { status: next });
        setSelected((cur) => (cur && cur.id === task.id ? updated : cur));
        await refresh();
      } catch (err) {
        setMessage((err as Error).message);
      } finally {
        setBusy(false);
      }
    },
    [adapter, refresh],
  );

  return (
    <div className="page-stack">
      <PortalTaskHeader
        scopeLabel={scopeLabel}
        view={view}
        setView={setView}
        canCreate={permissions.canCreate && !!adapter.createTask}
        onCreate={() => setShowCreate(true)}
        onRefresh={refresh}
        busy={busy}
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
        <Kpi label={t("Total")} value={kpiCounts.total_tasks} icon={<ListChecks size={16} className="text-brand-muted" />} tone="bg-subtle" />
        <Kpi label={t("Open")} value={(kpiCounts.total_tasks ?? 0) - (kpiCounts.done ?? 0)} icon={<Clock size={16} className="text-blue-600" />} tone="bg-blue-100" />
        <Kpi label={t("Overdue")} value={kpiCounts.overdue} icon={<AlertTriangle size={16} className="text-rose-600" />} tone="bg-rose-100" />
        <Kpi label={t("Due Today")} value={kpiCounts.due_today} icon={<CalendarClock size={16} className="text-amber-600" />} tone="bg-amber-100" />
        <Kpi label={t("Supplier")} value={kpiCounts.supplier_tasks} icon={<Factory size={16} className="text-violet-600" />} tone="bg-violet-100" />
        <Kpi label={t("Customer")} value={kpiCounts.customer_tasks} icon={<Users size={16} className="text-cyan-600" />} tone="bg-cyan-100" />
        <Kpi label={t("Escalations")} value={kpiCounts.escalation_tasks} icon={<Flame size={16} className="text-orange-600" />} tone="bg-orange-100" />
        <Kpi label={t("Completed")} value={kpiCounts.done} icon={<CheckCircle2 size={16} className="text-green-600" />} tone="bg-green-100" />
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
          {internal && (
            <button
              type="button"
              onClick={togglePanel}
              className="btn-outline text-xs ml-auto"
              title={showPanel ? t("Hide “Assigned by you”") : t("Show “Assigned by you”")}
            >
              {showPanel ? <PanelRightClose size={13} /> : <PanelRightOpen size={13} />}
              <span className="hidden sm:inline">{t("Assigned by you")}</span>
            </button>
          )}
        </div>
        <QuickFilterChips value={quick} onChange={setQuick} tasks={searched} user={user} showInternal={internal} />
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
                      <div className="p-2 space-y-2 max-h-[calc(100vh-400px)] overflow-y-auto">
                        {list.map((task) => (
                          <PortalTaskCard
                            key={task.id}
                            task={task}
                            showAssignee={internal}
                            onOpen={() => setSelected(task)}
                          />
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
                    {internal && <th className="py-2 pr-3">{t("Assignee")}</th>}
                    {internal && <th className="py-2 pr-3">{t("Assigned by")}</th>}
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
                        {internal && <td className="py-2 pr-3">{task.assigned_to || "—"}</td>}
                        {internal && <td className="py-2 pr-3">{task.assigned_by || "—"}</td>}
                        <td className={`py-2 pr-3 whitespace-nowrap ${isOverdue(task) ? "text-rose-600 font-semibold" : ""}`}>
                          {fmtDate(task.due_date)}
                        </td>
                      </tr>
                    );
                  })}
                  {filtered.length === 0 && (
                    <tr>
                      <td className="py-3 text-brand-muted" colSpan={internal ? 8 : 6}>{t("No tasks match these filters.")}</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {internal && showPanel && (
          <AssignedByMePanel tasks={tasks} user={user} columns={board.byKey} onOpen={setSelected} />
        )}
      </div>

      {selected && (
        <PortalTaskDrawer
          task={selected}
          adapter={adapter}
          permissions={permissions}
          assignees={assignees}
          columns={board.columns}
          onClose={() => setSelected(null)}
          onChanged={async (task) => {
            setSelected(task);
            await refresh();
          }}
          onDeleted={async () => {
            setSelected(null);
            await refresh();
          }}
          onMove={moveStatus}
        />
      )}

      {showCreate && permissions.canCreate && adapter.createTask && (
        <PortalTaskCreateForm
          assignees={permissions.canAssign ? assignees : []}
          canAssign={permissions.canAssign}
          statusOptions={board.visible}
          canAttach={!!adapter.attachments?.upload}
          onCancel={() => setShowCreate(false)}
          onSave={async (payload, files) => {
            const created = await adapter.createTask!(payload);
            const upload = adapter.attachments?.upload;
            if (upload) {
              for (const f of files) {
                try {
                  await upload(created.id, f);
                } catch (err) {
                  setMessage((err as Error).message);
                }
              }
            }
            setShowCreate(false);
            await refresh();
          }}
        />
      )}
    </div>
  );
}

function PortalTaskCard({
  task,
  showAssignee,
  onOpen,
}: {
  task: CommunicationTask;
  showAssignee: boolean;
  onOpen: () => void;
}) {
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
      {showAssignee && task.assigned_to && (
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

// ─── Header ─────────────────────────────────────────────────────────────────
function PortalTaskHeader({
  scopeLabel,
  view,
  setView,
  canCreate,
  onCreate,
  onRefresh,
  busy,
}: {
  scopeLabel: string;
  view: "kanban" | "table";
  setView: (v: "kanban" | "table") => void;
  canCreate: boolean;
  onCreate: () => void;
  onRefresh: () => void;
  busy: boolean;
}) {
  const { t } = useT();
  return (
    <div className="page-header">
      <div className="flex min-w-0 items-center gap-3">
        <span className="icon-tile bg-red-50 text-signal-red">
          <ListChecks size={17} />
        </span>
        <div className="min-w-0">
          <h1 className="page-title truncate">{t(scopeLabel)}</h1>
          <p className="page-subtitle">{t("Track work in kanban or table view.")}</p>
        </div>
      </div>
      <div className="page-actions">
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
        {canCreate && (
          <button type="button" onClick={onCreate} className="btn-dark text-xs">
            <Plus size={13} /> {t("Create Task")}
          </button>
        )}
        <button type="button" onClick={onRefresh} disabled={busy} className="btn-outline text-xs">
          <RefreshCcw size={13} className={busy ? "animate-spin" : ""} /> {t("Refresh")}
        </button>
      </div>
    </div>
  );
}

// ─── Detail drawer ──────────────────────────────────────────────────────────
function PortalTaskDrawer({
  task,
  adapter,
  permissions,
  assignees,
  columns,
  onClose,
  onChanged,
  onDeleted,
  onMove,
}: {
  task: CommunicationTask;
  adapter: PortalTaskAdapter;
  permissions: PortalTaskPermissions;
  assignees: TaskAssignee[];
  columns: TaskBoardColumn[];
  onClose: () => void;
  onChanged: (t: CommunicationTask) => void | Promise<void>;
  onDeleted: () => void | Promise<void>;
  onMove: (t: CommunicationTask, s: TaskStatus) => void | Promise<void>;
}) {
  const { t } = useT();
  const { user } = useAuth();
  const [comments, setComments] = useState<TaskComment[]>([]);
  const [newComment, setNewComment] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const load = useCallback(async () => {
    if (!adapter.listComments) return;
    try {
      setComments(await adapter.listComments(task.id));
    } catch {
      /* ignore */
    }
  }, [adapter, task.id]);

  useEffect(() => {
    void load();
  }, [load]);

  async function submitComment() {
    if (!newComment.trim() || !adapter.addComment) return;
    setBusy(true);
    try {
      await adapter.addComment(task.id, newComment.trim());
      setNewComment("");
      await load();
    } finally {
      setBusy(false);
    }
  }

  async function patch(body: CommunicationTaskUpdate) {
    if (!adapter.updateTask) return;
    setBusy(true);
    try {
      const updated = await adapter.updateTask(task.id, body);
      await onChanged(updated);
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

  async function remove() {
    if (!adapter.deleteTask) return;
    if (!confirm(t("Delete this task? This cannot be undone."))) return;
    setBusy(true);
    try {
      await adapter.deleteTask(task.id);
      await onDeleted();
    } finally {
      setBusy(false);
    }
  }

  const statusCol = columns.find((c) => c.key === task.status);
  const statusOptions = columns.filter((c) => !c.hidden || c.key === task.status);
  const sortedComments = [...comments].sort((a, b) => +new Date(a.created_at) - +new Date(b.created_at));
  const editable = permissions.canEdit && !permissions.readOnly && !!adapter.updateTask;

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
            <div className="flex flex-wrap items-center gap-2 text-[11px] text-brand-muted">
              <span className="font-mono">TASK-{task.id}</span>
              <span className="text-gray-300">•</span>
              <span className="inline-flex items-center gap-1">
                <span className={`h-2 w-2 rounded-full ${columnDot(statusCol?.color)}`} />
                {statusCol ? t(statusCol.label) : task.status}
              </span>
              {!permissions.readOnly && task.assigned_by && (
                <>
                  <span className="text-gray-300">•</span>
                  <span>{t("Assigned by {name}", { name: task.assigned_by })}</span>
                </>
              )}
              {permissions.readOnly && (
                <span className="inline-flex items-center gap-1 text-[10px] font-medium text-amber-700 bg-amber-50 px-1.5 py-0.5 rounded">
                  <Lock size={10} /> {t("Read only")}
                </span>
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

            {adapter.attachments && (
              <TaskAttachmentsSection
                taskId={task.id}
                adapter={adapter.attachments}
                canUpload={editable || permissions.canComment}
                canRemove={(a) => a.uploaded_by_id === user?.id}
              />
            )}

            {/* Comments */}
            {adapter.listComments && (
              <div>
                <div className="flex items-center gap-1.5 mb-2">
                  <MessageSquare size={14} className="text-brand-muted" />
                  <span className="text-sm font-semibold text-brand-dark">{t("Comments")}</span>
                  <span className="text-xs text-brand-muted">({sortedComments.length})</span>
                </div>

                {permissions.canComment && adapter.addComment && (
                  <CommentComposer value={newComment} onChange={setNewComment} onSubmit={submitComment} busy={busy} />
                )}

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
            )}
          </div>

          {/* SIDEBAR — fields */}
          <aside className="min-h-0 overflow-y-auto p-5 space-y-4 bg-subtle">
            <Field label={t("Status")}>
              {editable ? (
                <select
                  value={task.status}
                  onChange={(e) => onMove(task, e.target.value as TaskStatus)}
                  className="border border-brand-border rounded-md px-2 py-1.5 text-sm w-full bg-card"
                >
                  {statusOptions.map((c) => (
                    <option key={c.key} value={c.key}>{t(c.label)}</option>
                  ))}
                </select>
              ) : (
                <div className="px-2 py-1.5 text-sm rounded-md border border-brand-border bg-card">
                  {statusCol ? t(statusCol.label) : task.status}
                </div>
              )}
            </Field>

            <div className="grid grid-cols-2 gap-3">
              <Field label={t("Priority")}>
                {editable ? (
                  <select
                    value={task.priority}
                    onChange={(e) => patch({ priority: e.target.value as CommunicationTask["priority"] })}
                    className="border border-brand-border rounded-md px-2 py-1.5 text-sm w-full bg-card"
                  >
                    {PRIORITY_OPTS.map((p) => (
                      <option key={p} value={p}>{t(p)}</option>
                    ))}
                  </select>
                ) : (
                  <div className="px-2 py-1.5 text-sm rounded-md border border-brand-border bg-card">{t(task.priority)}</div>
                )}
              </Field>
              <Field label={t("Signal")}>
                <div className="px-2 py-1.5 text-sm rounded-md border border-brand-border bg-card flex items-center gap-1.5">
                  <span className={`h-2 w-2 rounded-full ${signalDot(task.signal)}`} /> {task.signal}
                </div>
              </Field>
            </div>

            {!permissions.readOnly && (
              <Field label={t("Assignee")}>
                {permissions.canAssign && adapter.updateTask ? (
                  <AssigneePicker
                    value={task.assigned_to_user_id ?? null}
                    assignees={assignees}
                    placeholder={t("Unassigned")}
                    onChange={(id) => patch({ assigned_to_user_id: id })}
                  />
                ) : (
                  <div className="px-2 py-1.5 text-sm rounded-md border border-brand-border bg-card">{task.assigned_to || t("Unassigned")}</div>
                )}
              </Field>
            )}

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
                <span>{t("Due")}: {fmtDate(task.due_date)}</span>
                {!permissions.readOnly && task.assigned_by && <span>{t("Assigned by")}: {task.assigned_by}</span>}
              </div>
            </div>

            {editable && (
              <button
                type="button"
                onClick={escalate}
                disabled={busy}
                className="w-full text-sm px-3 py-1.5 rounded-md border border-rose-300 text-rose-700 bg-rose-50 hover:bg-rose-100 flex items-center justify-center gap-1 disabled:opacity-50"
              >
                <ArrowUpCircle size={14} /> {t("Escalate")} (L{(task.escalation_level ?? 0) + 1})
              </button>
            )}

            {permissions.canDelete && adapter.deleteTask && (
              <button
                type="button"
                onClick={remove}
                disabled={busy}
                className="w-full text-sm px-3 py-1.5 rounded-md border border-brand-border text-brand-muted hover:bg-subtle disabled:opacity-50"
              >
                {t("Delete task")}
              </button>
            )}
          </aside>
        </div>
      </div>
    </div>
  );
}

// ─── Create form (slim, reuses CommunicationTaskCreate) ─────────────────────
function PortalTaskCreateForm({
  assignees,
  canAssign,
  statusOptions,
  canAttach,
  onCancel,
  onSave,
}: {
  assignees: TaskAssignee[];
  canAssign: boolean;
  statusOptions: TaskBoardColumn[];
  canAttach: boolean;
  onCancel: () => void;
  onSave: (payload: CommunicationTaskCreate, files: File[]) => void | Promise<void>;
}) {
  const { t } = useT();
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [supplierPoNo, setSupplierPoNo] = useState("");
  const [priority, setPriority] = useState<CommunicationTask["priority"]>("MEDIUM");
  const [status, setStatus] = useState<TaskStatus>("TODO");
  const [signal, setSignal] = useState<CommunicationTask["signal"]>("YELLOW");
  const [assignedToUserId, setAssignedToUserId] = useState<number | null>(null);
  const [dueDate, setDueDate] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [submitting, setSubmitting] = useState(false);

  const submit = async () => {
    if (!title.trim()) return;
    setSubmitting(true);
    try {
      await onSave(
        {
          title: title.trim(),
          description: description || undefined,
          supplier_po_no: supplierPoNo || null,
          priority,
          status,
          signal,
          assigned_to_user_id: canAssign ? assignedToUserId : null,
          due_date: dueDate ? new Date(dueDate).toISOString() : null,
        },
        files,
      );
    } finally {
      setSubmitting(false);
    }
  };

  const label = "mb-1 block text-[11px] font-medium uppercase tracking-wide text-brand-muted";
  const input = "w-full rounded-md border border-brand-border px-2.5 py-2 text-sm";

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4" onClick={onCancel}>
      <div className="w-full max-w-2xl rounded-xl bg-card shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-brand-border px-5 py-3">
          <div className="flex items-center gap-2">
            <Plus size={16} className="text-signal-red" />
            <span className="font-semibold">{t("Create Task")}</span>
          </div>
          <button className="rounded p-1 hover:bg-subtle" onClick={onCancel}>
            <X size={18} />
          </button>
        </div>

        <div className="grid max-h-[70vh] grid-cols-2 gap-4 overflow-y-auto p-5">
          <div className="col-span-2">
            <label className={label}>{t("Task title")}</label>
            <input
              autoFocus
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className={input}
              placeholder={t("e.g. Confirm dispatch date")}
            />
          </div>
          <div className="col-span-2">
            <label className={label}>{t("Description")}</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              className={`${input} resize-none`}
              placeholder={t("Add context, expected outcome…")}
            />
          </div>
          <div>
            <label className={label}>{t("PO number")}</label>
            <input value={supplierPoNo} onChange={(e) => setSupplierPoNo(e.target.value)} className={input} placeholder="#45021" />
          </div>
          <div>
            <label className={label}>{t("Due date")}</label>
            <input type="datetime-local" value={dueDate} onChange={(e) => setDueDate(e.target.value)} className={input} />
          </div>
          <div>
            <label className={label}>{t("Priority")}</label>
            <select value={priority} onChange={(e) => setPriority(e.target.value as CommunicationTask["priority"])} className={input}>
              {PRIORITY_OPTS.map((p) => (
                <option key={p} value={p}>{t(p)}</option>
              ))}
            </select>
          </div>
          <div>
            <label className={label}>{t("Signal")}</label>
            <select value={signal} onChange={(e) => setSignal(e.target.value as CommunicationTask["signal"])} className={input}>
              <option value="GREEN">{t("Green — On Track")}</option>
              <option value="YELLOW">{t("Yellow — Reminder")}</option>
              <option value="RED">{t("Red — Delayed")}</option>
              <option value="BLACK">{t("Black — Critical")}</option>
            </select>
          </div>
          <div>
            <label className={label}>{t("Status")}</label>
            <select value={status} onChange={(e) => setStatus(e.target.value as TaskStatus)} className={input}>
              {statusOptions.map((c) => (
                <option key={c.key} value={c.key}>{t(c.label)}</option>
              ))}
            </select>
          </div>
          {canAssign && (
            <div>
              <label className={label}>{t("Assigned to")}</label>
              <AssigneePicker value={assignedToUserId} assignees={assignees} onChange={setAssignedToUserId} placeholder={t("Unassigned")} />
            </div>
          )}
          {canAttach && (
            <div className="col-span-2">
              <AttachmentDropArea onFiles={(fs) => setFiles((cur) => [...cur, ...fs])}>
                <div className="rounded-lg border border-dashed border-brand-border p-3">
                  <div className="flex items-center justify-between">
                    <span className={label}>{t("Attachments")}</span>
                    <AttachButton
                      onFiles={(fs) => setFiles((cur) => [...cur, ...fs])}
                      className="inline-flex items-center gap-1 rounded-md border border-brand-border px-2 py-1 text-xs hover:bg-subtle"
                    />
                  </div>
                  {files.length === 0 ? (
                    <p className="text-xs text-brand-muted">{t("Drop files here or use the paperclip.")}</p>
                  ) : (
                    <div className="mt-1 flex flex-wrap gap-1.5">
                      {files.map((f, i) => (
                        <span
                          key={`${f.name}-${i}`}
                          className="inline-flex max-w-[240px] items-center gap-1.5 rounded-full border border-brand-border bg-subtle px-2.5 py-1 text-[11px]"
                        >
                          <Paperclip size={11} className="shrink-0 text-brand-muted" />
                          <span className="truncate">{f.name}</span>
                          <button
                            type="button"
                            onClick={() => setFiles((cur) => cur.filter((_, j) => j !== i))}
                            className="shrink-0 text-brand-muted hover:text-signal-red"
                          >
                            <X size={11} />
                          </button>
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </AttachmentDropArea>
            </div>
          )}
        </div>

        <div className="flex justify-end gap-2 border-t border-brand-border px-5 py-3">
          <button className="btn-ghost" onClick={onCancel} disabled={submitting}>
            {t("Cancel")}
          </button>
          <button className="btn-primary" onClick={() => void submit()} disabled={submitting || !title.trim()}>
            <Plus size={14} />
            <span className="ml-1.5">{t("Create Task")}</span>
          </button>
        </div>
      </div>
    </div>
  );
}

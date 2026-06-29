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
} from "lucide-react";

import { AssigneePicker } from "@/components/tasks/AssigneePicker";
import type {
  CommunicationTask,
  CommunicationTaskCreate,
  CommunicationTaskUpdate,
  PortalTaskDashboard,
  TaskAssignee,
  TaskComment,
  TaskSource,
  TaskStatus,
} from "@/lib/types";

// ─── Constants (mirror the admin Task Manager) ──────────────────────────────
const COLUMNS: { key: TaskStatus; label: string; dot: string }[] = [
  { key: "BACKLOG", label: "Backlog", dot: "bg-slate-400" },
  { key: "TODO", label: "To Do", dot: "bg-blue-400" },
  { key: "IN_PROGRESS", label: "In Progress", dot: "bg-amber-400" },
  { key: "WAITING_SUPPLIER", label: "Waiting Supplier", dot: "bg-violet-400" },
  { key: "WAITING_CUSTOMER", label: "Waiting Customer", dot: "bg-cyan-400" },
  { key: "BLOCKED", label: "Blocked", dot: "bg-rose-500" },
  { key: "DONE", label: "Done", dot: "bg-green-500" },
];

const SOURCE_OPTIONS: { value: TaskSource | ""; label: string }[] = [
  { value: "", label: "All sources" },
  { value: "SUPPLIER", label: "Supplier" },
  { value: "CUSTOMER", label: "Customer" },
  { value: "INTERNAL", label: "Internal" },
  { value: "ESCALATION", label: "Escalation" },
];

const PRIORITY_OPTS = ["P0", "P1", "P2", "P3"];

const PRIORITY_BADGE: Record<string, string> = {
  P0: "bg-rose-100 text-rose-700",
  P1: "bg-amber-100 text-amber-700",
  P2: "bg-blue-100 text-blue-700",
  P3: "bg-slate-100 text-slate-600",
};

const SOURCE_BADGE: Record<string, string> = {
  SUPPLIER: "bg-violet-100 text-violet-700",
  CUSTOMER: "bg-cyan-100 text-cyan-700",
  INTERNAL: "bg-slate-100 text-slate-600",
  ESCALATION: "bg-rose-100 text-rose-700",
};

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
      return "bg-slate-300";
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
  updateTask?: (id: number, patch: CommunicationTaskUpdate) => Promise<CommunicationTask>;
  createTask?: (payload: CommunicationTaskCreate) => Promise<CommunicationTask>;
  deleteTask?: (id: number) => Promise<void>;
  listAssignees?: () => Promise<TaskAssignee[]>;
  listComments?: (id: number) => Promise<TaskComment[]>;
  addComment?: (id: number, comment: string) => Promise<TaskComment>;
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
  const [dashboard, setDashboard] = useState<PortalTaskDashboard | null>(null);
  const [tasks, setTasks] = useState<CommunicationTask[]>([]);
  const [source, setSource] = useState<TaskSource | "">("");
  const [status, setStatus] = useState<TaskStatus | "">("");
  const [priority, setPriority] = useState("");
  const [search, setSearch] = useState("");
  const [overdueOnly, setOverdueOnly] = useState(false);
  const [view, setView] = useState<"kanban" | "table">("kanban");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [selected, setSelected] = useState<CommunicationTask | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [assignees, setAssignees] = useState<TaskAssignee[]>([]);

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
          overdue: overdueOnly || undefined,
        }),
      ]);
      if (dash) setDashboard(dash);
      setTasks(list);
    } catch (err) {
      setMessage((err as Error).message);
    } finally {
      setBusy(false);
    }
  }, [adapter, source, status, overdueOnly]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const filtered = useMemo(() => {
    return tasks.filter((t) => {
      if (priority && t.priority !== priority) return false;
      if (search) {
        const hay = `${t.title} ${t.description || ""} ${t.supplier_name || ""} ${t.supplier_po_no || ""} ${t.material_name || ""}`.toLowerCase();
        if (!hay.includes(search.toLowerCase())) return false;
      }
      return true;
    });
  }, [tasks, priority, search]);

  // Client-side KPI fallback when the dashboard endpoint is unavailable.
  const kpiCounts = useMemo(() => {
    if (dashboard) return dashboard;
    const open = tasks.filter((t) => t.status !== "DONE");
    return {
      total_tasks: tasks.length,
      todo: tasks.filter((t) => t.status === "TODO").length,
      in_progress: tasks.filter((t) => t.status === "IN_PROGRESS").length,
      waiting: tasks.filter((t) => t.status === "WAITING_SUPPLIER" || t.status === "WAITING_CUSTOMER").length,
      done: tasks.filter((t) => t.status === "DONE").length,
      overdue: open.filter((t) => isOverdue(t)).length,
      due_today: 0,
      critical: tasks.filter((t) => t.priority === "P0").length,
      supplier_tasks: tasks.filter((t) => (t.task_source || "SUPPLIER") === "SUPPLIER").length,
      customer_tasks: tasks.filter((t) => t.task_source === "CUSTOMER").length,
      internal_tasks: tasks.filter((t) => t.task_source === "INTERNAL").length,
      escalation_tasks: tasks.filter((t) => t.task_source === "ESCALATION").length,
    } satisfies PortalTaskDashboard;
  }, [dashboard, tasks]);

  const grouped = useMemo(() => {
    const buckets = Object.fromEntries(COLUMNS.map((c) => [c.key, [] as CommunicationTask[]])) as Record<
      TaskStatus,
      CommunicationTask[]
    >;
    filtered.forEach((t) => {
      const key = (t.status || "TODO") as TaskStatus;
      (buckets[key] || buckets.TODO).push(t);
    });
    return buckets;
  }, [filtered]);

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
        <Kpi label="Total" value={kpiCounts.total_tasks} icon={<ListChecks size={16} className="text-slate-600" />} tone="bg-slate-100" />
        <Kpi label="Open" value={(kpiCounts.total_tasks ?? 0) - (kpiCounts.done ?? 0)} icon={<Clock size={16} className="text-blue-600" />} tone="bg-blue-100" />
        <Kpi label="Overdue" value={kpiCounts.overdue} icon={<AlertTriangle size={16} className="text-rose-600" />} tone="bg-rose-100" />
        <Kpi label="Due Today" value={kpiCounts.due_today} icon={<CalendarClock size={16} className="text-amber-600" />} tone="bg-amber-100" />
        <Kpi label="Supplier" value={kpiCounts.supplier_tasks} icon={<Factory size={16} className="text-violet-600" />} tone="bg-violet-100" />
        <Kpi label="Customer" value={kpiCounts.customer_tasks} icon={<Users size={16} className="text-cyan-600" />} tone="bg-cyan-100" />
        <Kpi label="Escalations" value={kpiCounts.escalation_tasks} icon={<Flame size={16} className="text-orange-600" />} tone="bg-orange-100" />
        <Kpi label="Completed" value={kpiCounts.done} icon={<CheckCircle2 size={16} className="text-green-600" />} tone="bg-green-100" />
      </div>

      {/* Filter bar */}
      <div className="card p-2.5 flex flex-wrap items-center gap-2">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search title, PO, material…"
          className="border border-brand-border rounded px-2 py-1.5 text-sm flex-1 min-w-[180px]"
        />
        <select value={source} onChange={(e) => setSource(e.target.value as TaskSource | "")} className="border border-brand-border rounded px-2 py-1.5 text-sm">
          {SOURCE_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
        <select value={status} onChange={(e) => setStatus(e.target.value as TaskStatus | "")} className="border border-brand-border rounded px-2 py-1.5 text-sm">
          <option value="">All statuses</option>
          {COLUMNS.map((c) => (
            <option key={c.key} value={c.key}>{c.label}</option>
          ))}
        </select>
        <select value={priority} onChange={(e) => setPriority(e.target.value)} className="border border-brand-border rounded px-2 py-1.5 text-sm">
          <option value="">All priority</option>
          {PRIORITY_OPTS.map((p) => (
            <option key={p} value={p}>{p}</option>
          ))}
        </select>
        <label className="text-xs flex items-center gap-1.5">
          <input type="checkbox" checked={overdueOnly} onChange={(e) => setOverdueOnly(e.target.checked)} />
          Overdue
        </label>
      </div>

      {/* Board / Table */}
      {view === "kanban" ? (
        <div className="flex gap-3 overflow-x-auto pb-3">
          {COLUMNS.map((col) => (
            <div key={col.key} className="flex-shrink-0 w-72">
              <div className="rounded-lg border border-brand-border bg-white shadow-sm">
                <div className="flex items-center justify-between px-3 py-2 border-b border-brand-border">
                  <div className="flex items-center gap-2">
                    <span className={`h-2 w-2 rounded-full ${col.dot}`} />
                    <span className="text-xs font-semibold">{col.label}</span>
                  </div>
                  <span className="text-[11px] text-brand-muted bg-gray-100 rounded-full px-1.5">
                    {grouped[col.key].length}
                  </span>
                </div>
                <div className="p-2 space-y-2 max-h-[calc(100vh-360px)] overflow-y-auto">
                  {grouped[col.key].map((task) => {
                    const overdue = isOverdue(task);
                    const age = ageingDays(task.created_at);
                    return (
                      <button
                        key={task.id}
                        type="button"
                        onClick={() => setSelected(task)}
                        className="w-full rounded-lg border border-brand-border bg-white p-2.5 text-left shadow-sm transition hover:border-gray-300 hover:shadow-md"
                      >
                        <div className="flex items-start justify-between gap-2">
                          <span className="text-sm font-medium leading-snug line-clamp-2">{task.title}</span>
                          <span className={`text-[10px] px-1.5 py-0.5 rounded font-semibold ${PRIORITY_BADGE[task.priority] || ""}`}>
                            {task.priority}
                          </span>
                        </div>
                        <div className="flex flex-wrap items-center gap-1.5 mt-2">
                          <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${SOURCE_BADGE[task.task_source || "SUPPLIER"]}`}>
                            {task.task_source || "SUPPLIER"}
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
                        {task.material_name && (
                          <div className="text-[11px] text-brand-muted truncate">{task.material_name}</div>
                        )}
                        <div className="flex items-center justify-between mt-2 text-[11px] text-brand-muted">
                          <span className={overdue ? "text-rose-600 font-semibold" : ""}>
                            {overdue ? "Overdue " : "Due "}
                            {fmtDate(task.due_date)}
                          </span>
                          <span className="flex items-center gap-2">
                            {age != null && <span>{age}d</span>}
                            {task.comments_count > 0 && (
                              <span className="flex items-center gap-0.5">
                                <MessageSquare size={11} /> {task.comments_count}
                              </span>
                            )}
                          </span>
                        </div>
                        {!permissions.readOnly && task.assigned_to && (
                          <div className="mt-1.5 flex items-center gap-1">
                            <span className="h-5 w-5 rounded-full bg-brand-dark text-white text-[9px] flex items-center justify-center">
                              {task.assigned_to.slice(0, 2).toUpperCase()}
                            </span>
                            <span className="text-[11px] text-brand-muted truncate">{task.assigned_to}</span>
                          </div>
                        )}
                        <div className="mt-2 h-1.5 w-full rounded-full bg-gray-100">
                          <div
                            className="h-1.5 rounded-full bg-emerald-500"
                            style={{ width: `${task.progress_percent ?? 0}%` }}
                          />
                        </div>
                      </button>
                    );
                  })}
                  {grouped[col.key].length === 0 && (
                    <div className="text-[11px] text-brand-muted text-center py-4">No tasks</div>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="card p-3 overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="text-brand-muted border-b border-brand-border">
              <tr className="text-left">
                <th className="py-2 pr-3">Title</th>
                <th className="py-2 pr-3">Source</th>
                <th className="py-2 pr-3">Status</th>
                <th className="py-2 pr-3">Priority</th>
                <th className="py-2 pr-3">Supplier / PO</th>
                {!permissions.readOnly && <th className="py-2 pr-3">Assignee</th>}
                <th className="py-2 pr-3">Due</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-brand-border">
              {filtered.map((task) => (
                <tr key={task.id} className="hover:bg-gray-50 cursor-pointer" onClick={() => setSelected(task)}>
                  <td className="py-2 pr-3">
                    <div className="font-medium">{task.title}</div>
                    <div className="text-brand-muted truncate max-w-[280px]">{task.material_name}</div>
                  </td>
                  <td className="py-2 pr-3">
                    <span className={`text-[10px] px-1.5 py-0.5 rounded ${SOURCE_BADGE[task.task_source || "SUPPLIER"]}`}>
                      {task.task_source || "SUPPLIER"}
                    </span>
                  </td>
                  <td className="py-2 pr-3">{task.status}</td>
                  <td className="py-2 pr-3">
                    <span className={`text-[10px] px-1.5 py-0.5 rounded ${PRIORITY_BADGE[task.priority] || ""}`}>{task.priority}</span>
                  </td>
                  <td className="py-2 pr-3">
                    <div>{task.supplier_name || "—"}</div>
                    <div className="text-brand-muted">{task.supplier_po_no || ""}</div>
                  </td>
                  {!permissions.readOnly && <td className="py-2 pr-3">{task.assigned_to || "—"}</td>}
                  <td className={`py-2 pr-3 whitespace-nowrap ${isOverdue(task) ? "text-rose-600 font-semibold" : ""}`}>
                    {fmtDate(task.due_date)}
                  </td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr>
                  <td className="py-3 text-brand-muted" colSpan={permissions.readOnly ? 6 : 7}>No tasks match these filters.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {selected && (
        <PortalTaskDrawer
          task={selected}
          adapter={adapter}
          permissions={permissions}
          assignees={assignees}
          onClose={() => setSelected(null)}
          onChanged={async (t) => {
            setSelected(t);
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
          onCancel={() => setShowCreate(false)}
          onSave={async (payload) => {
            await adapter.createTask!(payload);
            setShowCreate(false);
            await refresh();
          }}
        />
      )}
    </div>
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
  return (
    <div className="page-header">
      <div className="flex min-w-0 items-center gap-3">
        <span className="icon-tile bg-red-50 text-signal-red">
          <ListChecks size={17} />
        </span>
        <div className="min-w-0">
          <h1 className="page-title truncate">{scopeLabel}</h1>
          <p className="page-subtitle">Track work in kanban or table view.</p>
        </div>
      </div>
      <div className="page-actions">
        <div className="inline-flex border border-brand-border rounded-md overflow-hidden text-xs">
          <button
            type="button"
            onClick={() => setView("kanban")}
            className={`px-3 py-1.5 ${view === "kanban" ? "bg-brand-dark text-white" : "bg-white text-brand-dark"}`}
          >
            Kanban
          </button>
          <button
            type="button"
            onClick={() => setView("table")}
            className={`px-3 py-1.5 ${view === "table" ? "bg-brand-dark text-white" : "bg-white text-brand-dark"}`}
          >
            Table
          </button>
        </div>
        {canCreate && (
          <button type="button" onClick={onCreate} className="btn-dark text-xs">
            <Plus size={13} /> Create Task
          </button>
        )}
        <button type="button" onClick={onRefresh} disabled={busy} className="btn-outline text-xs">
          <RefreshCcw size={13} className={busy ? "animate-spin" : ""} /> Refresh
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
  onClose,
  onChanged,
  onDeleted,
  onMove,
}: {
  task: CommunicationTask;
  adapter: PortalTaskAdapter;
  permissions: PortalTaskPermissions;
  assignees: TaskAssignee[];
  onClose: () => void;
  onChanged: (t: CommunicationTask) => void | Promise<void>;
  onDeleted: () => void | Promise<void>;
  onMove: (t: CommunicationTask, s: TaskStatus) => void | Promise<void>;
}) {
  const [comments, setComments] = useState<TaskComment[]>([]);
  const [newComment, setNewComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [progressLocal, setProgressLocal] = useState<number>(task.progress_percent ?? 0);

  useEffect(() => setProgressLocal(task.progress_percent ?? 0), [task.progress_percent]);

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
      priority: "P0",
      signal: "RED",
    });
  }

  async function remove() {
    if (!adapter.deleteTask) return;
    if (!confirm("Delete this task? This cannot be undone.")) return;
    setBusy(true);
    try {
      await adapter.deleteTask(task.id);
      await onDeleted();
    } finally {
      setBusy(false);
    }
  }

  const statusCol = COLUMNS.find((c) => c.key === task.status);
  const sortedComments = [...comments].sort((a, b) => +new Date(a.created_at) - +new Date(b.created_at));
  const editable = permissions.canEdit && !permissions.readOnly && !!adapter.updateTask;

  const Field = ({ label, children }: { label: string; children: ReactNode }) => (
    <div>
      <div className="text-[11px] font-medium uppercase tracking-wide text-brand-muted mb-1">{label}</div>
      {children}
    </div>
  );

  return (
    <div className="fixed inset-0 z-50 grid place-items-center p-3 sm:p-6 bg-black/50" onClick={onClose}>
      <div
        className="relative w-full max-w-4xl max-h-[90vh] bg-white rounded-xl shadow-2xl flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-5 py-3 border-b border-brand-border flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-[11px] text-brand-muted">
              <span className="font-mono">TASK-{task.id}</span>
              <span className="text-gray-300">•</span>
              <span className="inline-flex items-center gap-1">
                <span className={`h-2 w-2 rounded-full ${statusCol?.dot ?? "bg-slate-400"}`} />
                {statusCol?.label ?? task.status}
              </span>
              {permissions.readOnly && (
                <span className="inline-flex items-center gap-1 text-[10px] font-medium text-amber-700 bg-amber-50 px-1.5 py-0.5 rounded">
                  <Lock size={10} /> Read only
                </span>
              )}
            </div>
            <h2 className="text-lg font-semibold text-brand-dark leading-snug truncate">{task.title}</h2>
          </div>
          <button onClick={onClose} className="p-1.5 rounded hover:bg-gray-100 text-brand-muted">
            <X size={18} />
          </button>
        </div>

        {/* Body: main + sidebar */}
        <div className="flex-1 overflow-y-auto">
          <div className="grid md:grid-cols-3">
            {/* MAIN */}
            <div className="md:col-span-2 p-5 space-y-5 md:border-r border-brand-border">
              {task.description && (
                <div>
                  <div className="text-[11px] font-medium uppercase tracking-wide text-brand-muted mb-1">Description</div>
                  <p className="text-sm whitespace-pre-wrap text-brand-dark">{task.description}</p>
                </div>
              )}

              {/* Comments */}
              {adapter.listComments && (
                <div>
                  <div className="flex items-center gap-1.5 mb-2">
                    <MessageSquare size={14} className="text-brand-muted" />
                    <span className="text-sm font-semibold text-brand-dark">Comments</span>
                    <span className="text-xs text-brand-muted">({sortedComments.length})</span>
                  </div>

                  {permissions.canComment && adapter.addComment && (
                    <div className="flex gap-2 mb-3">
                      <input
                        type="text"
                        value={newComment}
                        onChange={(e) => setNewComment(e.target.value)}
                        onKeyDown={(e) => e.key === "Enter" && submitComment()}
                        placeholder="Add a comment…"
                        className="border border-brand-border rounded-md px-3 py-1.5 text-sm flex-1"
                      />
                      <button
                        onClick={submitComment}
                        disabled={busy || !newComment.trim()}
                        className="text-xs px-3 py-1.5 rounded-md bg-brand-dark text-white disabled:opacity-50"
                      >
                        Send
                      </button>
                    </div>
                  )}

                  <div className="space-y-2">
                    {sortedComments.length === 0 && (
                      <div className="text-xs text-brand-muted">No comments yet.</div>
                    )}
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
            <aside className="p-4 space-y-4 bg-slate-50">
              <Field label="Status">
                {editable ? (
                  <select
                    value={task.status}
                    onChange={(e) => onMove(task, e.target.value as TaskStatus)}
                    className="border border-brand-border rounded-md px-2 py-1.5 text-sm w-full bg-white"
                  >
                    {COLUMNS.map((c) => (
                      <option key={c.key} value={c.key}>{c.label}</option>
                    ))}
                  </select>
                ) : (
                  <div className="px-2 py-1.5 text-sm rounded-md border border-brand-border bg-white">{statusCol?.label ?? task.status}</div>
                )}
              </Field>

              <div className="grid grid-cols-2 gap-3">
                <Field label="Priority">
                  {editable ? (
                    <select
                      value={task.priority}
                      onChange={(e) => patch({ priority: e.target.value as CommunicationTask["priority"] })}
                      className="border border-brand-border rounded-md px-2 py-1.5 text-sm w-full bg-white"
                    >
                      {PRIORITY_OPTS.map((p) => (
                        <option key={p} value={p}>{p}</option>
                      ))}
                    </select>
                  ) : (
                    <div className="px-2 py-1.5 text-sm rounded-md border border-brand-border bg-white">{task.priority}</div>
                  )}
                </Field>
                <Field label="Signal">
                  <div className="px-2 py-1.5 text-sm rounded-md border border-brand-border bg-white flex items-center gap-1.5">
                    <span className={`h-2 w-2 rounded-full ${signalDot(task.signal)}`} /> {task.signal}
                  </div>
                </Field>
              </div>

              {!permissions.readOnly && (
                <Field label="Assignee">
                  {permissions.canAssign && adapter.updateTask ? (
                    <AssigneePicker
                      value={task.assigned_to_user_id ?? null}
                      assignees={assignees}
                      onChange={(id) => patch({ assigned_to_user_id: id })}
                    />
                  ) : (
                    <div className="px-2 py-1.5 text-sm rounded-md border border-brand-border bg-white">{task.assigned_to || "Unassigned"}</div>
                  )}
                </Field>
              )}

              <Field label={`Progress — ${progressLocal}%`}>
                {editable ? (
                  <>
                    <input
                      type="range"
                      min={0}
                      max={100}
                      step={5}
                      value={progressLocal}
                      onChange={(e) => setProgressLocal(Number(e.target.value))}
                      onMouseUp={(e) => patch({ progress_percent: Number((e.target as HTMLInputElement).value) })}
                      onTouchEnd={() => patch({ progress_percent: progressLocal })}
                      onKeyUp={(e) => patch({ progress_percent: Number((e.target as HTMLInputElement).value) })}
                      className="w-full"
                    />
                    <div className="mt-1 h-1.5 w-full rounded-full bg-gray-200">
                      <div className="h-1.5 rounded-full bg-emerald-500" style={{ width: `${progressLocal}%` }} />
                    </div>
                  </>
                ) : (
                  <div className="mt-1 h-1.5 w-full rounded-full bg-gray-200">
                    <div className="h-1.5 rounded-full bg-emerald-500" style={{ width: `${progressLocal}%` }} />
                  </div>
                )}
              </Field>

              {/* Linked context */}
              <div className="rounded-lg border border-brand-border p-3 space-y-1.5 bg-white">
                <div className="text-[11px] font-semibold uppercase tracking-wide text-brand-muted flex items-center gap-1">
                  <Link2 size={12} /> Linked context
                </div>
                <div className="text-xs flex flex-col gap-1 text-brand-dark">
                  <span>Source: <b>{task.task_source || "SUPPLIER"}</b></span>
                  {task.supplier_name && <span>Supplier: {task.supplier_name}</span>}
                  {task.supplier_po_no && <span>PO: {task.supplier_po_no}</span>}
                  {task.material_name && <span>Material: {task.material_name}</span>}
                  <span>Due: {fmtDate(task.due_date)}</span>
                </div>
              </div>

              {editable && (
                <button
                  type="button"
                  onClick={escalate}
                  disabled={busy}
                  className="w-full text-sm px-3 py-1.5 rounded-md border border-rose-300 text-rose-700 bg-rose-50 hover:bg-rose-100 flex items-center justify-center gap-1 disabled:opacity-50"
                >
                  <ArrowUpCircle size={14} /> Escalate (L{(task.escalation_level ?? 0) + 1})
                </button>
              )}

              {permissions.canDelete && adapter.deleteTask && (
                <button
                  type="button"
                  onClick={remove}
                  disabled={busy}
                  className="w-full text-sm px-3 py-1.5 rounded-md border border-brand-border text-brand-muted hover:bg-gray-100 disabled:opacity-50"
                >
                  Delete task
                </button>
              )}
            </aside>
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Create form (slim, reuses CommunicationTaskCreate) ─────────────────────
function PortalTaskCreateForm({
  assignees,
  canAssign,
  onCancel,
  onSave,
}: {
  assignees: TaskAssignee[];
  canAssign: boolean;
  onCancel: () => void;
  onSave: (payload: CommunicationTaskCreate) => void | Promise<void>;
}) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [supplierPoNo, setSupplierPoNo] = useState("");
  const [priority, setPriority] = useState<CommunicationTask["priority"]>("P2");
  const [status, setStatus] = useState<TaskStatus>("TODO");
  const [signal, setSignal] = useState<CommunicationTask["signal"]>("YELLOW");
  const [assignedToUserId, setAssignedToUserId] = useState<number | null>(null);
  const [dueDate, setDueDate] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const submit = async () => {
    if (!title.trim()) return;
    setSubmitting(true);
    try {
      await onSave({
        title: title.trim(),
        description: description || undefined,
        supplier_po_no: supplierPoNo || null,
        priority,
        status,
        signal,
        assigned_to_user_id: canAssign ? assignedToUserId : null,
        due_date: dueDate ? new Date(dueDate).toISOString() : null,
      });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4" onClick={onCancel}>
      <div className="w-full max-w-2xl rounded-xl bg-white shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-brand-border px-5 py-3">
          <div className="flex items-center gap-2">
            <Plus size={16} className="text-signal-red" />
            <span className="font-semibold">Create Task</span>
          </div>
          <button className="rounded p-1 hover:bg-gray-100" onClick={onCancel}>
            <X size={18} />
          </button>
        </div>

        <div className="grid max-h-[70vh] grid-cols-2 gap-4 overflow-y-auto p-5">
          <div className="col-span-2">
            <label className="mb-1 block text-[11px] font-medium uppercase tracking-wide text-brand-muted">Task title</label>
            <input
              autoFocus
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="w-full rounded-md border border-brand-border px-2.5 py-2 text-sm"
              placeholder="e.g. Confirm dispatch date"
            />
          </div>
          <div className="col-span-2">
            <label className="mb-1 block text-[11px] font-medium uppercase tracking-wide text-brand-muted">Description</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              className="w-full resize-none rounded-md border border-brand-border px-2.5 py-2 text-sm"
              placeholder="Add context, expected outcome…"
            />
          </div>
          <div>
            <label className="mb-1 block text-[11px] font-medium uppercase tracking-wide text-brand-muted">PO number</label>
            <input value={supplierPoNo} onChange={(e) => setSupplierPoNo(e.target.value)} className="w-full rounded-md border border-brand-border px-2.5 py-2 text-sm" placeholder="#45021" />
          </div>
          <div>
            <label className="mb-1 block text-[11px] font-medium uppercase tracking-wide text-brand-muted">Due date</label>
            <input type="datetime-local" value={dueDate} onChange={(e) => setDueDate(e.target.value)} className="w-full rounded-md border border-brand-border px-2.5 py-2 text-sm" />
          </div>
          <div>
            <label className="mb-1 block text-[11px] font-medium uppercase tracking-wide text-brand-muted">Priority</label>
            <select value={priority} onChange={(e) => setPriority(e.target.value as CommunicationTask["priority"])} className="w-full rounded-md border border-brand-border px-2.5 py-2 text-sm">
              {PRIORITY_OPTS.map((p) => (
                <option key={p} value={p}>{p}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-[11px] font-medium uppercase tracking-wide text-brand-muted">Signal</label>
            <select value={signal} onChange={(e) => setSignal(e.target.value as CommunicationTask["signal"])} className="w-full rounded-md border border-brand-border px-2.5 py-2 text-sm">
              <option value="GREEN">Green — On Track</option>
              <option value="YELLOW">Yellow — Reminder</option>
              <option value="RED">Red — Delayed</option>
              <option value="BLACK">Black — Critical</option>
            </select>
          </div>
          <div>
            <label className="mb-1 block text-[11px] font-medium uppercase tracking-wide text-brand-muted">Status</label>
            <select value={status} onChange={(e) => setStatus(e.target.value as TaskStatus)} className="w-full rounded-md border border-brand-border px-2.5 py-2 text-sm">
              {COLUMNS.map((c) => (
                <option key={c.key} value={c.key}>{c.label}</option>
              ))}
            </select>
          </div>
          {canAssign && (
            <div>
              <label className="mb-1 block text-[11px] font-medium uppercase tracking-wide text-brand-muted">Assigned to</label>
              <AssigneePicker value={assignedToUserId} assignees={assignees} onChange={setAssignedToUserId} />
            </div>
          )}
        </div>

        <div className="flex justify-end gap-2 border-t border-brand-border px-5 py-3">
          <button className="btn-ghost" onClick={onCancel} disabled={submitting}>
            Cancel
          </button>
          <button className="btn-primary" onClick={() => void submit()} disabled={submitting || !title.trim()}>
            <Plus size={14} />
            <span className="ml-1.5">Create Task</span>
          </button>
        </div>
      </div>
    </div>
  );
}

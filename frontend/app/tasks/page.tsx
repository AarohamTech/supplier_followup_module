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
} from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import PageHeader from "@/components/layout/PageHeader";
import { AssigneePicker, WatcherPicker } from "@/components/tasks/AssigneePicker";
import TaskCreateForm from "@/components/tasks/TaskCreateForm";
import type {
  CommunicationTask,
  TaskActivity,
  TaskAssignee,
  TaskComment,
  TaskSource,
  TaskStatus,
} from "@/lib/types";

type DashboardResult = Awaited<ReturnType<typeof api.getTasksDashboard>>;

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
  P3: "bg-subtle text-brand-muted",
};

const SOURCE_BADGE: Record<string, string> = {
  SUPPLIER: "bg-violet-100 text-violet-700",
  CUSTOMER: "bg-cyan-100 text-cyan-700",
  INTERNAL: "bg-subtle text-brand-muted",
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
  const searchParams = useSearchParams();
  const customerMailIdParam = searchParams.get("customer_mail_id");
  const customerMailId = customerMailIdParam ? Number(customerMailIdParam) : null;

  const [dashboard, setDashboard] = useState<DashboardResult | null>(null);
  const [tasks, setTasks] = useState<CommunicationTask[]>([]);
  const [source, setSource] = useState<TaskSource | "">("");
  const [status, setStatus] = useState<TaskStatus | "">("");
  const [priority, setPriority] = useState("");
  const [assigned, setAssigned] = useState("");
  const [supplier, setSupplier] = useState("");
  const [search, setSearch] = useState("");
  const [overdueOnly, setOverdueOnly] = useState(false);
  const [view, setView] = useState<"kanban" | "table">("kanban");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [selected, setSelected] = useState<CommunicationTask | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [assignees, setAssignees] = useState<TaskAssignee[]>([]);
  const [suppliers, setSuppliers] = useState<string[]>([]);

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
          overdue: overdueOnly,
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
  }, [source, status, assigned, supplier, overdueOnly, customerMailId]);

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
      "due_date",
    ];
    const rows = filtered.map((t) =>
      [
        t.id,
        `"${(t.title || "").replace(/"/g, '""')}"`,
        t.status,
        t.priority,
        t.task_source || "SUPPLIER",
        `"${(t.supplier_name || "").replace(/"/g, '""')}"`,
        t.supplier_po_no || "",
        `"${(t.material_name || "").replace(/"/g, '""')}"`,
        t.assigned_to || "",
        t.due_date || "",
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
        title="Task Manager"
        description="Track supplier, customer, internal and escalation work in kanban or table view."
        icon={ListChecks}
        actions={
          <>
          <div className="inline-flex border border-brand-border rounded-md overflow-hidden text-xs">
            <button
              type="button"
              onClick={() => setView("kanban")}
              className={`px-3 py-1.5 ${view === "kanban" ? "bg-ink text-white" : "bg-card text-brand-dark"}`}
            >
              Kanban
            </button>
            <button
              type="button"
              onClick={() => setView("table")}
              className={`px-3 py-1.5 ${view === "table" ? "bg-ink text-white" : "bg-card text-brand-dark"}`}
            >
              Table
            </button>
          </div>
          <button
            type="button"
            onClick={exportCsv}
            className="btn-outline text-xs"
          >
            Export
          </button>
          <button
            type="button"
            onClick={() => setShowCreate(true)}
            className="btn-dark text-xs"
          >
            <Plus size={13} /> Create Task
          </button>
          <button
            type="button"
            onClick={refresh}
            disabled={busy}
            className="btn-outline text-xs"
          >
            <RefreshCcw size={13} className={busy ? "animate-spin" : ""} /> Refresh
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
        <Kpi label="Total" value={dashboard?.total_tasks} icon={<ListChecks size={16} className="text-brand-muted" />} tone="bg-subtle" />
        <Kpi label="Open" value={(dashboard?.total_tasks ?? 0) - (dashboard?.done ?? 0)} icon={<Clock size={16} className="text-blue-600" />} tone="bg-blue-100" />
        <Kpi label="Overdue" value={dashboard?.overdue} icon={<AlertTriangle size={16} className="text-rose-600" />} tone="bg-rose-100" />
        <Kpi label="Due Today" value={dashboard?.due_today} icon={<CalendarClock size={16} className="text-amber-600" />} tone="bg-amber-100" />
        <Kpi label="Supplier" value={dashboard?.supplier_tasks} icon={<Factory size={16} className="text-violet-600" />} tone="bg-violet-100" />
        <Kpi label="Customer" value={dashboard?.customer_tasks} icon={<Users size={16} className="text-cyan-600" />} tone="bg-cyan-100" />
        <Kpi label="Escalations" value={dashboard?.escalation_tasks} icon={<Flame size={16} className="text-orange-600" />} tone="bg-orange-100" />
        <Kpi label="Completed" value={dashboard?.done} icon={<CheckCircle2 size={16} className="text-green-600" />} tone="bg-green-100" />
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
        <input
          type="text"
          value={supplier}
          onChange={(e) => setSupplier(e.target.value)}
          placeholder="Supplier"
          className="border border-brand-border rounded px-2 py-1.5 text-sm w-32"
        />
        <input
          type="text"
          value={assigned}
          onChange={(e) => setAssigned(e.target.value)}
          placeholder="Assignee"
          className="border border-brand-border rounded px-2 py-1.5 text-sm w-28"
        />
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
              <div className="rounded-lg border border-brand-border bg-card shadow-sm">
                <div className="flex items-center justify-between px-3 py-2 border-b border-brand-border">
                  <div className="flex items-center gap-2">
                    <span className={`h-2 w-2 rounded-full ${col.dot}`} />
                    <span className="text-xs font-semibold">{col.label}</span>
                  </div>
                  <span className="text-[11px] text-brand-muted bg-subtle rounded-full px-1.5">
                    {grouped[col.key].length}
                  </span>
                </div>
                <div className="p-2 space-y-2 max-h-[calc(100vh-340px)] overflow-y-auto">
                  {grouped[col.key].map((task) => {
                    const overdue = isOverdue(task);
                    const age = ageingDays(task.created_at);
                    return (
                      <button
                        key={task.id}
                        type="button"
                        onClick={() => setSelected(task)}
                        className="w-full rounded-lg border border-brand-border bg-card p-2.5 text-left shadow-sm transition hover:border-brand-border hover:shadow-md"
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
                            {task.linked_mail_id || task.customer_mail_id ? <Mail size={12} /> : null}
                            {age != null && <span>{age}d</span>}
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
                        <div className="mt-2 h-1.5 w-full rounded-full bg-subtle">
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
                <th className="py-2 pr-3">Assignee</th>
                <th className="py-2 pr-3">Due</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-brand-border">
              {filtered.map((task) => (
                <tr key={task.id} className="hover:bg-subtle cursor-pointer" onClick={() => setSelected(task)}>
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
                  <td className="py-2 pr-3">{task.assigned_to || "—"}</td>
                  <td className={`py-2 pr-3 whitespace-nowrap ${isOverdue(task) ? "text-rose-600 font-semibold" : ""}`}>
                    {fmtDate(task.due_date)}
                  </td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr>
                  <td className="py-3 text-brand-muted" colSpan={7}>No tasks match these filters.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {selected && (
        <TaskDrawer
          task={selected}
          assignees={assignees}
          onClose={() => setSelected(null)}
          onChanged={async (t) => {
            setSelected(t);
            await refresh();
          }}
          onMove={moveStatus}
        />
      )}

      {showCreate && (
        <TaskCreateForm
          assignees={assignees}
          suppliers={suppliers}
          onCancel={() => setShowCreate(false)}
          onSave={async (payload) => {
            await api.createTask(payload);
            setShowCreate(false);
            await refresh();
          }}
        />
      )}
    </div>
  );
}

function TaskDrawer({
  task,
  assignees,
  onClose,
  onChanged,
  onMove,
}: {
  task: CommunicationTask;
  assignees: TaskAssignee[];
  onClose: () => void;
  onChanged: (t: CommunicationTask) => void | Promise<void>;
  onMove: (t: CommunicationTask, s: TaskStatus) => void | Promise<void>;
}) {
  const { hasRole } = useAuth();
  const isAdmin = hasRole("admin");

  const [comments, setComments] = useState<TaskComment[]>([]);
  const [activity, setActivity] = useState<TaskActivity[]>([]);
  const [newComment, setNewComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [summarizing, setSummarizing] = useState(false);
  const [watcherIds, setWatcherIds] = useState<number[]>(task.watchers ?? []);
  const [progressLocal, setProgressLocal] = useState<number>(task.progress_percent ?? 0);
  const [showActivity, setShowActivity] = useState(false); // admin-only change log, collapsed by default

  // Keep local UI state in sync if the parent refreshes the task object.
  useEffect(() => setWatcherIds(task.watchers ?? []), [task.watchers]);
  useEffect(() => setProgressLocal(task.progress_percent ?? 0), [task.progress_percent]);

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
      priority: "P0",
      signal: "RED",
    });
  }

  const statusCol = COLUMNS.find((c) => c.key === task.status);
  const sortedComments = [...comments].sort((a, b) => +new Date(a.created_at) - +new Date(b.created_at));
  const sortedActivity = [...activity].sort((a, b) => +new Date(b.created_at) - +new Date(a.created_at));

  const Field = ({ label, children }: { label: string; children: ReactNode }) => (
    <div>
      <div className="text-[11px] font-medium uppercase tracking-wide text-brand-muted mb-1">{label}</div>
      {children}
    </div>
  );

  return (
    <div className="fixed inset-0 z-50 grid place-items-center p-3 sm:p-6 bg-black/50" onClick={onClose}>
      <div
        className="relative w-full max-w-4xl max-h-[90vh] bg-card rounded-xl shadow-2xl flex flex-col overflow-hidden"
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
            </div>
            <h2 className="text-lg font-semibold text-brand-dark leading-snug truncate">{task.title}</h2>
          </div>
          <button onClick={onClose} className="p-1.5 rounded hover:bg-subtle text-brand-muted">
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

              {/* AI Summary */}
              <div className="rounded-lg border border-indigo-100 bg-indigo-50/50 p-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-indigo-900 flex items-center gap-1.5">
                    <Sparkles size={13} /> AI Summary
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
                        alert("AI summary unavailable (LLM may be disabled).");
                      } finally {
                        setSummarizing(false);
                      }
                    }}
                  >
                    {summarizing ? "Generating…" : task.ai_summary ? "Regenerate" : "Summarize"}
                  </button>
                </div>
                <p className="mt-1.5 text-xs text-brand-dark whitespace-pre-wrap">
                  {task.ai_summary || "No summary yet — click Summarize to generate one from the comments & activity."}
                </p>
                {task.ai_summary_at && (
                  <p className="mt-1 text-[10px] text-brand-muted">
                    by {task.ai_summary_by} · {fmtDateTime(task.ai_summary_at)}
                  </p>
                )}
              </div>

              {/* Comments — visible to all staff */}
              <div>
                <div className="flex items-center gap-1.5 mb-2">
                  <MessageSquare size={14} className="text-brand-muted" />
                  <span className="text-sm font-semibold text-brand-dark">Comments</span>
                  <span className="text-xs text-brand-muted">({sortedComments.length})</span>
                </div>

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
                    className="text-xs px-3 py-1.5 rounded-md bg-ink text-white disabled:opacity-50"
                  >
                    Send
                  </button>
                </div>

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
                    Activity log
                    <span className="text-xs font-normal text-brand-muted">({sortedActivity.length})</span>
                    <span className="ml-auto inline-flex items-center gap-1 text-[10px] font-normal text-amber-700 bg-amber-50 px-1.5 py-0.5 rounded">
                      <Lock size={10} /> Admin only
                    </span>
                  </button>

                  {showActivity && (
                    <div className="mt-3 space-y-2 max-h-72 overflow-y-auto pr-1">
                      {sortedActivity.length === 0 && (
                        <div className="text-xs text-brand-muted">No activity recorded.</div>
                      )}
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
            <aside className="p-4 space-y-4 bg-subtle">
              <Field label="Status">
                <select
                  value={task.status}
                  onChange={(e) => onMove(task, e.target.value as TaskStatus)}
                  className="border border-brand-border rounded-md px-2 py-1.5 text-sm w-full bg-card"
                >
                  {COLUMNS.map((c) => (
                    <option key={c.key} value={c.key}>{c.label}</option>
                  ))}
                </select>
              </Field>

              <div className="grid grid-cols-2 gap-3">
                <Field label="Priority">
                  <select
                    value={task.priority}
                    onChange={(e) => patch({ priority: e.target.value as CommunicationTask["priority"] })}
                    className="border border-brand-border rounded-md px-2 py-1.5 text-sm w-full bg-card"
                  >
                    {PRIORITY_OPTS.map((p) => (
                      <option key={p} value={p}>{p}</option>
                    ))}
                  </select>
                </Field>
                <Field label="Signal">
                  <div className="px-2 py-1.5 text-sm rounded-md border border-brand-border bg-card">{task.signal}</div>
                </Field>
              </div>

              <Field label="Assignee">
                <AssigneePicker
                  value={task.assigned_to_user_id ?? null}
                  assignees={assignees}
                  onChange={(id) => patch({ assigned_to_user_id: id })}
                />
              </Field>

              <Field label="Watchers">
                <WatcherPicker
                  value={watcherIds}
                  assignees={assignees}
                  onChange={(ids) => {
                    setWatcherIds(ids);
                    void patch({ watchers: ids });
                  }}
                />
              </Field>

              <Field label={`Progress — ${progressLocal}%`}>
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
                <div className="mt-1 h-1.5 w-full rounded-full bg-subtle">
                  <div className="h-1.5 rounded-full bg-emerald-500" style={{ width: `${progressLocal}%` }} />
                </div>
              </Field>

              {/* Linked context */}
              <div className="rounded-lg border border-brand-border p-3 space-y-1.5 bg-card">
                <div className="text-[11px] font-semibold uppercase tracking-wide text-brand-muted flex items-center gap-1">
                  <Link2 size={12} /> Linked context
                </div>
                <div className="text-xs flex flex-col gap-1 text-brand-dark">
                  <span>Source: <b>{task.task_source || "SUPPLIER"}</b></span>
                  {task.supplier_name && <span>Supplier: {task.supplier_name}</span>}
                  {task.supplier_po_no && <span>PO: {task.supplier_po_no}</span>}
                  {task.material_name && <span>Material: {task.material_name}</span>}
                  {task.linked_mail_id && (
                    <Link href={`/mail-history`} className="text-signal-red underline">
                      Linked supplier mail #{task.linked_mail_id}
                    </Link>
                  )}
                  {task.customer_mail_id && (
                    <Link href={`/customer-mails?focus=${task.customer_mail_id}`} className="text-signal-red underline">
                      Customer mail #{task.customer_mail_id}
                    </Link>
                  )}
                  <span>Due: {fmtDate(task.due_date)}</span>
                </div>
              </div>

              <button
                type="button"
                onClick={escalate}
                disabled={busy}
                className="w-full text-sm px-3 py-1.5 rounded-md border border-rose-300 text-rose-700 bg-rose-50 hover:bg-rose-100 flex items-center justify-center gap-1 disabled:opacity-50"
              >
                <ArrowUpCircle size={14} /> Escalate (L{(task.escalation_level ?? 0) + 1})
              </button>
            </aside>
          </div>
        </div>
      </div>
    </div>
  );
}

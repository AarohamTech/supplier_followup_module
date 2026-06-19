"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
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
} from "lucide-react";
import { api } from "@/lib/api";
import PageHeader from "@/components/layout/PageHeader";
import type {
  CommunicationTask,
  TaskActivity,
  TaskComment,
  TaskSource,
  TaskStatus,
} from "@/lib/types";

type DashboardResult = Awaited<ReturnType<typeof api.getTasksDashboard>>;

const COLUMNS: { key: TaskStatus; label: string; accent: string; dot: string }[] = [
  { key: "BACKLOG", label: "Backlog", accent: "border-t-slate-400", dot: "bg-slate-400" },
  { key: "TODO", label: "To Do", accent: "border-t-blue-400", dot: "bg-blue-400" },
  { key: "IN_PROGRESS", label: "In Progress", accent: "border-t-amber-400", dot: "bg-amber-400" },
  { key: "WAITING_SUPPLIER", label: "Waiting Supplier", accent: "border-t-violet-400", dot: "bg-violet-400" },
  { key: "WAITING_CUSTOMER", label: "Waiting Customer", accent: "border-t-cyan-400", dot: "bg-cyan-400" },
  { key: "BLOCKED", label: "Blocked", accent: "border-t-rose-500", dot: "bg-rose-500" },
  { key: "DONE", label: "Done", accent: "border-t-green-500", dot: "bg-green-500" },
];

const SOURCE_OPTIONS: { value: TaskSource | ""; label: string }[] = [
  { value: "", label: "All sources" },
  { value: "SUPPLIER", label: "Supplier" },
  { value: "CUSTOMER", label: "Customer" },
  { value: "INTERNAL", label: "Internal" },
  { value: "ESCALATION", label: "Escalation" },
];

const PRIORITY_OPTS = ["P0", "P1", "P2", "P3"];

const PRIORITY_BORDER: Record<string, string> = {
  P0: "border-l-rose-500",
  P1: "border-l-amber-500",
  P2: "border-l-blue-400",
  P3: "border-l-slate-300",
};

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
        <Kpi label="Total" value={dashboard?.total_tasks} icon={<ListChecks size={16} className="text-slate-600" />} tone="bg-slate-100" />
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
              <div className={`bg-white rounded-lg border border-brand-border border-t-4 ${col.accent} shadow-sm`}>
                <div className="flex items-center justify-between px-3 py-2 border-b border-brand-border">
                  <div className="flex items-center gap-2">
                    <span className={`h-2 w-2 rounded-full ${col.dot}`} />
                    <span className="text-xs font-semibold">{col.label}</span>
                  </div>
                  <span className="text-[11px] text-brand-muted bg-gray-100 rounded-full px-1.5">
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
                        className={`w-full text-left bg-white border border-brand-border rounded-lg p-2.5 shadow-sm hover:shadow-md transition border-l-4 ${PRIORITY_BORDER[task.priority] || "border-l-slate-300"}`}
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
                            <span className="h-5 w-5 rounded-full bg-brand-dark text-white text-[9px] flex items-center justify-center">
                              {task.assigned_to.slice(0, 2).toUpperCase()}
                            </span>
                            <span className="text-[11px] text-brand-muted truncate">{task.assigned_to}</span>
                          </div>
                        )}
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
          onClose={() => setSelected(null)}
          onChanged={async (t) => {
            setSelected(t);
            await refresh();
          }}
          onMove={moveStatus}
        />
      )}

      {showCreate && (
        <CreateTaskModal
          onClose={() => setShowCreate(false)}
          onCreated={async () => {
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
  onClose,
  onChanged,
  onMove,
}: {
  task: CommunicationTask;
  onClose: () => void;
  onChanged: (t: CommunicationTask) => void | Promise<void>;
  onMove: (t: CommunicationTask, s: TaskStatus) => void | Promise<void>;
}) {
  const [comments, setComments] = useState<TaskComment[]>([]);
  const [activity, setActivity] = useState<TaskActivity[]>([]);
  const [newComment, setNewComment] = useState("");
  const [tab, setTab] = useState<"comments" | "activity">("comments");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [c, a] = await Promise.all([
        api.listTaskComments(task.id),
        api.listTaskActivity(task.id),
      ]);
      setComments(c);
      setActivity(a);
    } catch {
      /* ignore */
    }
  }, [task.id]);

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

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/30" onClick={onClose} />
      <div className="relative w-full max-w-md bg-white h-full shadow-2xl flex flex-col">
        <div className="px-4 py-3 border-b border-brand-border flex items-start justify-between gap-2">
          <div>
            <div className="text-[11px] text-brand-muted">Task #{task.id}</div>
            <div className="text-base font-semibold leading-snug">{task.title}</div>
          </div>
          <button onClick={onClose} className="p-1 rounded hover:bg-gray-100">
            <X size={16} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {/* Status row */}
          <div>
            <div className="text-[11px] text-brand-muted mb-1">Status</div>
            <select
              value={task.status}
              onChange={(e) => onMove(task, e.target.value as TaskStatus)}
              className="border border-brand-border rounded px-2 py-1.5 text-sm w-full"
            >
              {COLUMNS.map((c) => (
                <option key={c.key} value={c.key}>{c.label}</option>
              ))}
            </select>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <div className="text-[11px] text-brand-muted mb-1">Priority</div>
              <select
                value={task.priority}
                onChange={(e) => patch({ priority: e.target.value as CommunicationTask["priority"] })}
                className="border border-brand-border rounded px-2 py-1.5 text-sm w-full"
              >
                {PRIORITY_OPTS.map((p) => (
                  <option key={p} value={p}>{p}</option>
                ))}
              </select>
            </div>
            <div>
              <div className="text-[11px] text-brand-muted mb-1">Assignee</div>
              <input
                type="text"
                defaultValue={task.assigned_to || ""}
                onBlur={(e) => {
                  if (e.target.value !== (task.assigned_to || "")) patch({ assigned_to: e.target.value });
                }}
                className="border border-brand-border rounded px-2 py-1.5 text-sm w-full"
              />
            </div>
          </div>

          {task.description && (
            <div>
              <div className="text-[11px] text-brand-muted mb-1">Description</div>
              <p className="text-sm whitespace-pre-wrap">{task.description}</p>
            </div>
          )}

          {/* Linked context */}
          <div className="rounded-lg border border-brand-border p-3 space-y-1.5 bg-gray-50">
            <div className="text-[11px] font-semibold text-brand-muted flex items-center gap-1">
              <Link2 size={12} /> Linked context
            </div>
            <div className="text-xs flex flex-col gap-1">
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
            className="w-full text-sm px-3 py-1.5 rounded-md border border-rose-300 text-rose-700 bg-rose-50 flex items-center justify-center gap-1 disabled:opacity-50"
          >
            <ArrowUpCircle size={14} /> Escalate (L{(task.escalation_level ?? 0) + 1})
          </button>

          {/* Tabs */}
          <div className="border-t border-brand-border pt-3">
            <div className="flex gap-2 mb-2">
              <button
                onClick={() => setTab("comments")}
                className={`text-xs px-2.5 py-1 rounded flex items-center gap-1 ${tab === "comments" ? "bg-brand-dark text-white" : "bg-gray-100"}`}
              >
                <MessageSquare size={12} /> Comments ({comments.length})
              </button>
              <button
                onClick={() => setTab("activity")}
                className={`text-xs px-2.5 py-1 rounded flex items-center gap-1 ${tab === "activity" ? "bg-brand-dark text-white" : "bg-gray-100"}`}
              >
                <History size={12} /> Activity ({activity.length})
              </button>
            </div>

            {tab === "comments" ? (
              <div className="space-y-2">
                {comments.map((c) => (
                  <div key={c.id} className="rounded-lg border border-brand-border p-2">
                    <div className="flex items-center justify-between text-[11px] text-brand-muted">
                      <span className="font-medium text-brand-dark">{c.created_by || "system"}</span>
                      <span>{fmtDateTime(c.created_at)}</span>
                    </div>
                    <p className="text-sm mt-1 whitespace-pre-wrap">{c.comment}</p>
                  </div>
                ))}
                {comments.length === 0 && <div className="text-xs text-brand-muted">No comments yet.</div>}
                <div className="flex gap-2 pt-1">
                  <input
                    type="text"
                    value={newComment}
                    onChange={(e) => setNewComment(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && submitComment()}
                    placeholder="Add a comment…"
                    className="border border-brand-border rounded px-2 py-1.5 text-sm flex-1"
                  />
                  <button
                    onClick={submitComment}
                    disabled={busy || !newComment.trim()}
                    className="text-xs px-3 py-1.5 rounded bg-brand-dark text-white disabled:opacity-50"
                  >
                    Send
                  </button>
                </div>
              </div>
            ) : (
              <div className="space-y-2">
                {activity.map((a) => (
                  <div key={a.id} className="flex gap-2 text-xs">
                    <div className="h-2 w-2 rounded-full bg-brand-dark mt-1.5 flex-shrink-0" />
                    <div>
                      <div className="font-medium">{a.activity_type.replace(/_/g, " ")}</div>
                      <div className="text-brand-muted">
                        {a.old_value ? `${a.old_value} → ` : ""}
                        {a.new_value || ""}
                      </div>
                      <div className="text-[10px] text-brand-muted">{fmtDateTime(a.created_at)}</div>
                    </div>
                  </div>
                ))}
                {activity.length === 0 && <div className="text-xs text-brand-muted">No activity yet.</div>}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function CreateTaskModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: () => void | Promise<void>;
}) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [taskSource, setTaskSource] = useState<TaskSource>("INTERNAL");
  const [priority, setPriority] = useState("P2");
  const [assigned, setAssigned] = useState("");
  const [supplier, setSupplier] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit() {
    if (!title.trim()) {
      setErr("Title is required");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      await api.createTask({
        title: title.trim(),
        description: description || undefined,
        task_source: taskSource,
        priority: priority as CommunicationTask["priority"],
        assigned_to: assigned || undefined,
        supplier_name: supplier || undefined,
        status: "TODO",
      });
      await onCreated();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/30" onClick={onClose} />
      <div className="relative w-full max-w-md bg-white rounded-lg shadow-2xl p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold">Create Task</h2>
          <button onClick={onClose} className="p-1 rounded hover:bg-gray-100">
            <X size={16} />
          </button>
        </div>
        {err && <div className="text-xs text-rose-700 bg-rose-50 rounded p-2">{err}</div>}
        <input
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Task title"
          className="border border-brand-border rounded px-2 py-1.5 text-sm w-full"
        />
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Description (optional)"
          rows={3}
          className="border border-brand-border rounded px-2 py-1.5 text-sm w-full"
        />
        <div className="grid grid-cols-2 gap-3">
          <select value={taskSource} onChange={(e) => setTaskSource(e.target.value as TaskSource)} className="border border-brand-border rounded px-2 py-1.5 text-sm">
            <option value="INTERNAL">Internal</option>
            <option value="SUPPLIER">Supplier</option>
            <option value="CUSTOMER">Customer</option>
            <option value="ESCALATION">Escalation</option>
          </select>
          <select value={priority} onChange={(e) => setPriority(e.target.value)} className="border border-brand-border rounded px-2 py-1.5 text-sm">
            {PRIORITY_OPTS.map((p) => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
        </div>
        <input
          type="text"
          value={supplier}
          onChange={(e) => setSupplier(e.target.value)}
          placeholder="Supplier name (optional)"
          className="border border-brand-border rounded px-2 py-1.5 text-sm w-full"
        />
        <input
          type="text"
          value={assigned}
          onChange={(e) => setAssigned(e.target.value)}
          placeholder="Assign to (optional)"
          className="border border-brand-border rounded px-2 py-1.5 text-sm w-full"
        />
        <div className="flex justify-end gap-2 pt-1">
          <button onClick={onClose} className="text-sm px-3 py-1.5 rounded border border-brand-border">
            Cancel
          </button>
          <button onClick={submit} disabled={busy} className="text-sm px-3 py-1.5 rounded bg-brand-dark text-white disabled:opacity-50">
            {busy ? "Creating…" : "Create"}
          </button>
        </div>
      </div>
    </div>
  );
}

"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import type {
  CustomerMail,
  CustomerMailListResponse,
} from "@/lib/types";

const PRIORITY_TONE: Record<string, string> = {
  P0: "bg-signal-red text-white",
  P1: "bg-amber-500 text-white",
  P2: "bg-blue-500 text-white",
  P3: "bg-gray-300 text-brand-dark",
};

function formatDateTime(value: string | null | undefined) {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

function Kpi({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="card p-3">
      <div className="text-xs text-brand-muted">{label}</div>
      <div className="text-xl font-semibold mt-1">{value}</div>
    </div>
  );
}

function CustomerMailsPageInner() {
  const params = useSearchParams();
  const initialFocus = Number(params?.get("focus") || 0) || null;
  const [data, setData] = useState<CustomerMailListResponse | null>(null);
  const [status, setStatus] = useState<string>("");
  const [mailType, setMailType] = useState<string>("");
  const [assigned, setAssigned] = useState<string>("");
  const [search, setSearch] = useState<string>("");
  const [selectedId, setSelectedId] = useState<number | null>(initialFocus);
  const [selected, setSelected] = useState<CustomerMail | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [resolutionNote, setResolutionNote] = useState("");
  const [taskTitle, setTaskTitle] = useState("");
  const [taskAssigned, setTaskAssigned] = useState("");
  const [taskPriority, setTaskPriority] = useState("P2");

  const refresh = useCallback(async () => {
    setBusy(true);
    try {
      const list = await api.listCustomerMails({
        status: status || undefined,
        mail_type: mailType || undefined,
        assigned_to: assigned || undefined,
        search: search || undefined,
        limit: 200,
      });
      setData(list);
      if (selectedId) {
        const found = list.items.find((m) => m.id === selectedId);
        if (found) setSelected(found);
      }
    } catch (err) {
      setMessage((err as Error).message);
    } finally {
      setBusy(false);
    }
  }, [status, mailType, assigned, search, selectedId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      if (selectedId == null) {
        setSelected(null);
        return;
      }
      try {
        const detail = await api.getCustomerMail(selectedId);
        if (!cancelled) setSelected(detail);
      } catch (err) {
        if (!cancelled) setMessage((err as Error).message);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [selectedId]);

  const items = data?.items || [];
  const stats = data?.stats || {};

  const allowedStatuses = data?.allowed_statuses || [];
  const allowedTypes = data?.allowed_types || [];

  async function handleAssign(field: string, value: string) {
    if (!selected) return;
    setBusy(true);
    setMessage(null);
    try {
      const updated = await api.assignCustomerMail(selected.id, { [field]: value });
      setSelected(updated);
      await refresh();
    } catch (err) {
      setMessage((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function handleResolve() {
    if (!selected) return;
    setBusy(true);
    setMessage(null);
    try {
      const updated = await api.resolveCustomerMail(selected.id, resolutionNote);
      setSelected(updated);
      setResolutionNote("");
      await refresh();
      setMessage("Mail resolved.");
    } catch (err) {
      setMessage((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function handleCreateTask() {
    if (!selected) return;
    setBusy(true);
    setMessage(null);
    try {
      const result = await api.createTaskForCustomerMail(selected.id, {
        title: taskTitle || (selected.subject || "Customer mail follow-up"),
        assigned_to: taskAssigned || undefined,
        priority: taskPriority,
      });
      setTaskTitle("");
      setTaskAssigned("");
      await refresh();
      setMessage(`Task #${result.task_id} created and linked.`);
    } catch (err) {
      setMessage((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold">Customer Mail Inbox</h1>
        <button
          type="button"
          onClick={refresh}
          disabled={busy}
          className="text-xs px-2 py-1 rounded border border-brand-border bg-white"
        >
          {busy ? "Loading…" : "Refresh"}
        </button>
      </div>

      {message && <div className="card p-3 text-xs text-brand-muted">{message}</div>}

      <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
        <Kpi label="Total" value={stats.total ?? "—"} />
        <Kpi label="Open" value={stats.open ?? "—"} />
        <Kpi label="In progress" value={stats.in_progress ?? "—"} />
        <Kpi label="Resolved" value={stats.resolved ?? "—"} />
        <Kpi label="Closed" value={stats.closed ?? "—"} />
        <Kpi label="Today" value={stats.received_today ?? "—"} />
      </div>

      <div className="card p-4 flex flex-wrap gap-3 items-end">
        <label className="text-xs flex flex-col gap-1">
          <span className="text-brand-muted">Status</span>
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            className="border border-brand-border rounded px-2 py-1 text-sm"
          >
            <option value="">All</option>
            {allowedStatuses.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
        <label className="text-xs flex flex-col gap-1">
          <span className="text-brand-muted">Type</span>
          <select
            value={mailType}
            onChange={(e) => setMailType(e.target.value)}
            className="border border-brand-border rounded px-2 py-1 text-sm"
          >
            <option value="">All</option>
            {allowedTypes.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </label>
        <label className="text-xs flex flex-col gap-1">
          <span className="text-brand-muted">Assigned</span>
          <input
            type="text"
            value={assigned}
            onChange={(e) => setAssigned(e.target.value)}
            className="border border-brand-border rounded px-2 py-1 text-sm"
            placeholder="email/user"
          />
        </label>
        <label className="text-xs flex flex-col gap-1 flex-1 min-w-[180px]">
          <span className="text-brand-muted">Search subject / sender</span>
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="border border-brand-border rounded px-2 py-1 text-sm"
          />
        </label>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-1 card p-3 max-h-[640px] overflow-y-auto">
          <div className="text-xs text-brand-muted mb-2">{items.length} mails</div>
          <div className="space-y-2">
            {items.map((mail) => (
              <button
                key={mail.id}
                type="button"
                onClick={() => setSelectedId(mail.id)}
                className={`w-full text-left border rounded p-2 ${
                  selectedId === mail.id
                    ? "border-signal-red bg-red-50"
                    : "border-brand-border bg-white hover:bg-gray-50"
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="text-sm font-medium truncate">{mail.subject || "(no subject)"}</div>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded ${PRIORITY_TONE[mail.priority] || ""}`}>
                    {mail.priority}
                  </span>
                </div>
                <div className="text-xs text-brand-muted truncate">{mail.from_email || "unknown sender"}</div>
                <div className="text-[11px] text-brand-muted flex items-center gap-2 mt-1">
                  <span>{mail.status}</span>
                  <span>· {mail.mail_type}</span>
                  {(mail.open_task_count ?? 0) > 0 && (
                    <span
                      className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-violet-100 text-violet-700"
                      title={`${mail.open_task_count} open task${mail.open_task_count === 1 ? "" : "s"}`}
                    >
                      {mail.open_task_count} task{mail.open_task_count === 1 ? "" : "s"}
                    </span>
                  )}
                  <span className="ml-auto">{formatDateTime(mail.received_at)}</span>
                </div>
              </button>
            ))}
            {items.length === 0 && (
              <div className="text-xs text-brand-muted">No customer mails found.</div>
            )}
          </div>
        </div>

        <div className="lg:col-span-2 card p-4 space-y-3 min-h-[640px]">
          {!selected ? (
            <div className="text-sm text-brand-muted">Select a mail to view details.</div>
          ) : (
            <>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <div className="text-base font-semibold">{selected.subject || "(no subject)"}</div>
                  <div className="text-xs text-brand-muted">
                    From {selected.from_email || "unknown"} · Received {formatDateTime(selected.received_at)}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <span className={`text-xs px-1.5 py-0.5 rounded ${PRIORITY_TONE[selected.priority] || ""}`}>
                    {selected.priority}
                  </span>
                  <span className="text-xs px-1.5 py-0.5 rounded bg-gray-200 text-brand-dark">
                    {selected.status}
                  </span>
                  <span className="text-xs px-1.5 py-0.5 rounded bg-blue-100 text-blue-900">
                    {selected.mail_type}
                  </span>
                </div>
              </div>

              <div className="text-xs text-brand-muted flex flex-wrap gap-3">
                <span>To: {selected.to_email || "—"}</span>
                {selected.cc_email && <span>Cc: {selected.cc_email}</span>}
                {selected.assigned_to && <span>Assigned: {selected.assigned_to}</span>}
                {selected.linked_task_id && (
                  <span className="text-signal-red">Task #{selected.linked_task_id} linked</span>
                )}
                {(selected.task_count ?? 0) > 0 && (
                  <a
                    href={`/tasks?customer_mail_id=${selected.id}`}
                    className="text-violet-700 hover:underline"
                  >
                    {selected.task_count} linked task{(selected.task_count ?? 0) === 1 ? "" : "s"}
                    {(selected.open_task_count ?? 0) > 0
                      ? ` (${selected.open_task_count} open)`
                      : ""}
                  </a>
                )}
              </div>

              <pre className="text-xs whitespace-pre-wrap bg-gray-50 border border-brand-border rounded p-3 max-h-[280px] overflow-y-auto">
                {selected.body || "(empty body)"}
              </pre>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div className="border border-brand-border rounded p-3 space-y-2">
                  <div className="font-semibold text-sm">Triage</div>
                  <label className="text-xs flex flex-col gap-1">
                    <span className="text-brand-muted">Assign to</span>
                    <input
                      type="text"
                      defaultValue={selected.assigned_to || ""}
                      onBlur={(e) => handleAssign("assigned_to", e.target.value)}
                      className="border border-brand-border rounded px-2 py-1 text-sm"
                    />
                  </label>
                  <label className="text-xs flex flex-col gap-1">
                    <span className="text-brand-muted">Status</span>
                    <select
                      value={selected.status}
                      onChange={(e) => handleAssign("status", e.target.value)}
                      className="border border-brand-border rounded px-2 py-1 text-sm"
                    >
                      {allowedStatuses.map((s) => (
                        <option key={s} value={s}>
                          {s}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="text-xs flex flex-col gap-1">
                    <span className="text-brand-muted">Priority</span>
                    <select
                      value={selected.priority}
                      onChange={(e) => handleAssign("priority", e.target.value)}
                      className="border border-brand-border rounded px-2 py-1 text-sm"
                    >
                      <option value="P0">P0 — Critical</option>
                      <option value="P1">P1 — High</option>
                      <option value="P2">P2 — Normal</option>
                      <option value="P3">P3 — Low</option>
                    </select>
                  </label>
                  <label className="text-xs flex flex-col gap-1">
                    <span className="text-brand-muted">Type</span>
                    <select
                      value={selected.mail_type}
                      onChange={(e) => handleAssign("mail_type", e.target.value)}
                      className="border border-brand-border rounded px-2 py-1 text-sm"
                    >
                      {allowedTypes.map((t) => (
                        <option key={t} value={t}>
                          {t}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>

                <div className="border border-brand-border rounded p-3 space-y-2">
                  <div className="font-semibold text-sm">Create task</div>
                  <input
                    type="text"
                    value={taskTitle}
                    onChange={(e) => setTaskTitle(e.target.value)}
                    placeholder="Task title"
                    className="border border-brand-border rounded px-2 py-1 text-sm w-full"
                  />
                  <input
                    type="text"
                    value={taskAssigned}
                    onChange={(e) => setTaskAssigned(e.target.value)}
                    placeholder="Assign to (optional)"
                    className="border border-brand-border rounded px-2 py-1 text-sm w-full"
                  />
                  <select
                    value={taskPriority}
                    onChange={(e) => setTaskPriority(e.target.value)}
                    className="border border-brand-border rounded px-2 py-1 text-sm w-full"
                  >
                    <option value="P0">P0 — Critical</option>
                    <option value="P1">P1 — High</option>
                    <option value="P2">P2 — Normal</option>
                    <option value="P3">P3 — Low</option>
                  </select>
                  <button
                    type="button"
                    onClick={handleCreateTask}
                    disabled={busy}
                    className="w-full text-sm px-3 py-1.5 rounded bg-brand-fg text-white disabled:opacity-50"
                  >
                    Create Task
                  </button>

                  <div className="border-t border-brand-border my-2"></div>
                  <textarea
                    value={resolutionNote}
                    onChange={(e) => setResolutionNote(e.target.value)}
                    placeholder="Resolution note (optional)"
                    rows={2}
                    className="border border-brand-border rounded px-2 py-1 text-sm w-full"
                  />
                  <button
                    type="button"
                    onClick={handleResolve}
                    disabled={busy}
                    className="w-full text-sm px-3 py-1.5 rounded bg-green-600 text-white disabled:opacity-50"
                  >
                    Mark as Resolved
                  </button>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export default function CustomerMailsPage() {
  return (
    <Suspense fallback={<div className="p-6 text-sm text-brand-muted">Loading customer mails…</div>}>
      <CustomerMailsPageInner />
    </Suspense>
  );
}

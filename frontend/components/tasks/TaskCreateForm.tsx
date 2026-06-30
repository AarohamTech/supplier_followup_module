"use client";

import { useMemo, useState } from "react";
import { Bell, Loader2, UserPlus, X } from "lucide-react";

import { AssigneePicker, WatcherPicker } from "@/components/tasks/AssigneePicker";
import type {
  CommunicationTaskCreate,
  TaskAssignee,
  TaskPriority,
  TaskSignal,
  TaskStatus,
} from "@/lib/types";

const STATUS_GROUPS: { key: TaskStatus; label: string }[] = [
  { key: "TODO", label: "To Do" },
  { key: "WAITING_SUPPLIER", label: "Waiting Supplier" },
  { key: "IN_PROGRESS", label: "In Progress" },
  { key: "DONE", label: "Done" },
];

function toDatetimeLocal(iso: string): string {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function Field({ label, children, full }: { label: string; children: React.ReactNode; full?: boolean }) {
  return (
    <div className={full ? "col-span-2" : ""}>
      <label className="mb-1 block text-[11px] font-medium uppercase tracking-wide text-brand-muted">{label}</label>
      {children}
    </div>
  );
}

/**
 * Shared "Create Task" form used by both the Task Manager (/tasks) and the
 * Communication Hub (/mail-history). Same rich field set; uses the modern
 * ID-based assignee + watcher pickers so create writes real `assigned_to_user_id`
 * + `watchers: number[]` (backend denormalizes the display name).
 */
export default function TaskCreateForm({
  assignees,
  suppliers,
  seed = {},
  onCancel,
  onSave,
}: {
  assignees: TaskAssignee[];
  suppliers: string[];
  seed?: Partial<CommunicationTaskCreate>;
  onCancel: () => void;
  onSave: (payload: CommunicationTaskCreate) => void | Promise<void>;
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
  const [assignedToUserId, setAssignedToUserId] = useState<number | null>(seed.assigned_to_user_id ?? null);
  const [watcherIds, setWatcherIds] = useState<number[]>(seed.watchers ?? []);
  const [dueDate, setDueDate] = useState<string>(seed.due_date ? toDatetimeLocal(seed.due_date) : "");
  const [reminder, setReminder] = useState<string>(seed.reminder_at ? toDatetimeLocal(seed.reminder_at) : "");
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
    assigned_to_user_id: assignedToUserId,
    watchers: watcherIds,
    priority,
    status,
    signal,
    due_date: dueDate ? new Date(dueDate).toISOString() : null,
    reminder_at: reminder ? new Date(reminder).toISOString() : null,
  });

  const submit = async () => {
    if (!title.trim()) return;
    setSubmitting(true);
    try {
      await onSave(buildPayload());
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4" onClick={onCancel}>
      <div className="w-full max-w-2xl rounded-xl bg-card shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-brand-border px-5 py-3">
          <div className="flex items-center gap-2">
            <UserPlus size={16} className="text-signal-red" />
            <span className="font-semibold">Create Task</span>
          </div>
          <button className="rounded p-1 hover:bg-subtle" onClick={onCancel}>
            <X size={18} />
          </button>
        </div>

        <div className="grid max-h-[70vh] grid-cols-2 gap-4 overflow-y-auto p-5">
          <Field label="Task title" full>
            <input
              autoFocus
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="tcf-input"
              placeholder="e.g. Confirm dispatch date"
            />
          </Field>
          <Field label="Description" full>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              className="tcf-input resize-none"
              placeholder="Add context, expected outcome…"
            />
          </Field>

          <Field label="Supplier">
            <input
              list="tcf-supplier-list"
              value={supplierName}
              onChange={(e) => setSupplierName(e.target.value)}
              className="tcf-input"
            />
            <datalist id="tcf-supplier-list">
              {supplierOptions.map((s) => (
                <option key={s} value={s} />
              ))}
            </datalist>
          </Field>
          <Field label="PO number">
            <input value={poNo} onChange={(e) => setPoNo(e.target.value)} className="tcf-input" placeholder="#45021" />
          </Field>

          <Field label="Priority">
            <select value={priority} onChange={(e) => setPriority(e.target.value as TaskPriority)} className="tcf-input">
              {(["P0", "P1", "P2", "P3"] as TaskPriority[]).map((p) => (
                <option key={p} value={p}>{p}</option>
              ))}
            </select>
          </Field>
          <Field label="Signal">
            <select value={signal} onChange={(e) => setSignal(e.target.value as TaskSignal)} className="tcf-input">
              <option value="GREEN">● Green — On Track</option>
              <option value="YELLOW">● Yellow — Reminder</option>
              <option value="RED">● Red — Delayed</option>
              <option value="BLACK">● Black — Critical</option>
            </select>
          </Field>

          <Field label="Due date">
            <input type="datetime-local" value={dueDate} onChange={(e) => setDueDate(e.target.value)} className="tcf-input" />
          </Field>
          <Field label="Reminder">
            <input type="datetime-local" value={reminder} onChange={(e) => setReminder(e.target.value)} className="tcf-input" />
          </Field>

          <Field label="Assigned to">
            <AssigneePicker value={assignedToUserId} assignees={assignees} onChange={setAssignedToUserId} />
          </Field>
          <Field label="Status">
            <select value={status} onChange={(e) => setStatus(e.target.value as TaskStatus)} className="tcf-input">
              {STATUS_GROUPS.map((s) => (
                <option key={s.key} value={s.key}>{s.label}</option>
              ))}
            </select>
          </Field>

          <Field label="Watchers" full>
            <WatcherPicker value={watcherIds} assignees={assignees} onChange={setWatcherIds} />
          </Field>
        </div>

        <div className="flex justify-end gap-2 border-t border-brand-border px-5 py-3">
          <button className="btn-ghost" onClick={onCancel} disabled={submitting}>
            Cancel
          </button>
          <button className="btn-primary" onClick={() => void submit()} disabled={submitting || !title.trim()}>
            {submitting ? <Loader2 size={14} className="animate-spin" /> : <Bell size={14} />}
            <span className="ml-1.5">Create Task</span>
          </button>
        </div>
      </div>

      <style jsx>{`
        :global(.tcf-input) {
          width: 100%;
          padding: 8px 10px;
          font-size: 13px;
          border: 1px solid #e5e7eb;
          border-radius: 6px;
          background: #fff;
          outline: none;
        }
        :global(.tcf-input:focus) {
          border-color: #e11d2e;
        }
      `}</style>
    </div>
  );
}

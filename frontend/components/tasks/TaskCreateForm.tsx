"use client";

import { useMemo, useState } from "react";
import { Bell, FileText, Loader2, UserPlus, X } from "lucide-react";

import { AttachButton, AttachmentDropArea } from "@/components/attachments/Attachments";
import { AssigneePicker, WatcherPicker } from "@/components/tasks/AssigneePicker";
import { useT } from "@/lib/i18n";
import type {
  CommunicationTask,
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
  statusOptions,
  uploadAttachment,
  onCancel,
  onSave,
}: {
  assignees: TaskAssignee[];
  suppliers: string[];
  seed?: Partial<CommunicationTaskCreate>;
  /** Board columns to offer; defaults to the common built-ins. */
  statusOptions?: { key: TaskStatus; label: string }[];
  /** When given, files can be attached up front; they upload once the task exists. */
  uploadAttachment?: (taskId: number, file: File) => Promise<unknown>;
  onCancel: () => void;
  /** Return the created task so attachments can be bound to it. */
  onSave: (payload: CommunicationTaskCreate) => void | CommunicationTask | Promise<void | CommunicationTask>;
}) {
  const { t } = useT();
  const statuses = statusOptions ?? STATUS_GROUPS.map((s) => ({ key: s.key, label: t(s.label) }));
  const [files, setFiles] = useState<File[]>([]);
  const [fileError, setFileError] = useState<string | null>(null);
  const [title, setTitle] = useState(seed.title ?? "");
  const [description, setDescription] = useState(seed.description ?? "");
  const [supplierName, setSupplierName] = useState(seed.supplier_name ?? "");
  const [poNo, setPoNo] = useState(seed.supplier_po_no ?? "");
  const [linkedMailId] = useState(seed.linked_mail_id ?? null);
  const [procurementId] = useState(seed.procurement_record_id ?? null);
  const [priority, setPriority] = useState<TaskPriority>((seed.priority as TaskPriority) ?? "MEDIUM");
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
    setFileError(null);
    try {
      const created = await onSave(buildPayload());
      if (created && uploadAttachment && files.length) {
        for (const f of files) {
          try {
            await uploadAttachment(created.id, f);
          } catch (err) {
            setFileError((err as Error).message);
          }
        }
      }
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
            <span className="font-semibold">{t("Create Task")}</span>
          </div>
          <button className="rounded p-1 hover:bg-subtle" onClick={onCancel}>
            <X size={18} />
          </button>
        </div>

        <div className="grid max-h-[70vh] grid-cols-2 gap-4 overflow-y-auto p-5">
          <Field label={t("Task title")} full>
            <input
              autoFocus
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="tcf-input"
              placeholder={t("e.g. Confirm dispatch date")}
            />
          </Field>
          <Field label={t("Description")} full>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              className="tcf-input resize-none"
              placeholder={t("Add context, expected outcome…")}
            />
          </Field>

          <Field label={t("Supplier")}>
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
          <Field label={t("PO number")}>
            <input value={poNo} onChange={(e) => setPoNo(e.target.value)} className="tcf-input" placeholder="#45021" />
          </Field>

          <Field label={t("Priority")}>
            <select value={priority} onChange={(e) => setPriority(e.target.value as TaskPriority)} className="tcf-input">
              {(["LOW", "MEDIUM", "HIGH"] as TaskPriority[]).map((p) => (
                <option key={p} value={p}>{t(p)}</option>
              ))}
            </select>
          </Field>
          <Field label={t("Signal")}>
            <select value={signal} onChange={(e) => setSignal(e.target.value as TaskSignal)} className="tcf-input">
              <option value="GREEN">● {t("Green — On Track")}</option>
              <option value="YELLOW">● {t("Yellow — Reminder")}</option>
              <option value="RED">● {t("Red — Delayed")}</option>
              <option value="BLACK">● {t("Black — Critical")}</option>
            </select>
          </Field>

          <Field label={t("Due date")}>
            <input type="datetime-local" value={dueDate} onChange={(e) => setDueDate(e.target.value)} className="tcf-input" />
          </Field>
          <Field label={t("Reminder")}>
            <input type="datetime-local" value={reminder} onChange={(e) => setReminder(e.target.value)} className="tcf-input" />
          </Field>

          <Field label={t("Assigned to")}>
            <AssigneePicker value={assignedToUserId} assignees={assignees} onChange={setAssignedToUserId} placeholder={t("Unassigned")} />
          </Field>
          <Field label={t("Status")}>
            <select value={status} onChange={(e) => setStatus(e.target.value as TaskStatus)} className="tcf-input">
              {statuses.map((s) => (
                <option key={s.key} value={s.key}>{s.label}</option>
              ))}
            </select>
          </Field>

          <Field label={t("Watchers")} full>
            <WatcherPicker value={watcherIds} assignees={assignees} onChange={setWatcherIds} />
          </Field>

          {uploadAttachment && (
            <div className="col-span-2">
              <AttachmentDropArea onFiles={(fs) => setFiles((cur) => [...cur, ...fs])}>
                <div className="rounded-lg border border-dashed border-brand-border p-3">
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-medium uppercase tracking-wide text-brand-muted">
                      {t("Attachments")}
                    </span>
                    <AttachButton
                      onFiles={(fs) => setFiles((cur) => [...cur, ...fs])}
                      className="inline-flex items-center gap-1 rounded-md border border-brand-border px-2 py-1 text-xs hover:bg-subtle"
                    />
                  </div>
                  {files.length === 0 ? (
                    <p className="mt-1 text-xs text-brand-muted">{t("Drop files here or use the paperclip.")}</p>
                  ) : (
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {files.map((f, i) => (
                        <span
                          key={`${f.name}-${i}`}
                          className="inline-flex max-w-[240px] items-center gap-1.5 rounded-full border border-brand-border bg-subtle px-2.5 py-1 text-[11px]"
                        >
                          <FileText size={12} className="shrink-0 text-brand-muted" />
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
                  {fileError && <p className="mt-1 text-xs text-rose-700">{fileError}</p>}
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
            {submitting ? <Loader2 size={14} className="animate-spin" /> : <Bell size={14} />}
            <span className="ml-1.5">{t("Create Task")}</span>
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

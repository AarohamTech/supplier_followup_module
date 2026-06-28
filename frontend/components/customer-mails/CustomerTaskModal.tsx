"use client";

import { useMemo, useState } from "react";
import { Loader2, UserPlus, X } from "lucide-react";
import type {
  CommunicationTaskCreate,
  CustomerMail,
  TaskPriority,
  TaskSignal,
  TaskStatus,
} from "@/lib/types";
import type { ProcurementContext } from "./ProcurementContextPanel";
import { ASSIGNEES, TASK_STATUS_GROUPS } from "./shared";

interface CustomerTaskModalProps {
  mail: CustomerMail;
  context: ProcurementContext | null;
  saving: boolean;
  onCancel: () => void;
  onSave: (payload: CommunicationTaskCreate) => void;
}

function Field({
  label,
  children,
  full,
}: {
  label: string;
  children: React.ReactNode;
  full?: boolean;
}) {
  return (
    <div className={full ? "col-span-2" : ""}>
      <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-brand-muted">
        {label}
      </div>
      {children}
    </div>
  );
}

const INPUT =
  "w-full rounded-md border border-brand-border bg-white px-2.5 py-2 text-[13px] outline-none focus:border-signal-red";

/**
 * Rich task creator for the Customer Response Workspace — same shape as the
 * Communication Hub creator but seeded with customer-related details. All field
 * state is local to the modal, so typing here never re-renders the workspace.
 * The modal is only mounted while open (lazy), keeping the main page light.
 */
export default function CustomerTaskModal({
  mail,
  context,
  saving,
  onCancel,
  onSave,
}: CustomerTaskModalProps) {
  const [title, setTitle] = useState(mail.subject || "Customer mail follow-up");
  const [description, setDescription] = useState(
    mail.body ? mail.body.slice(0, 500) : "",
  );
  const [customerName, setCustomerName] = useState(
    mail.from_name || mail.customer_name || "",
  );
  const [customerEmail] = useState(mail.from_email || "");
  const [poNo, setPoNo] = useState(
    mail.linked_supplier_po_no || context?.supplierPo || "",
  );
  const [material, setMaterial] = useState(context?.material || "");
  const [priority, setPriority] = useState<TaskPriority>(
    (mail.priority as TaskPriority) || "P2",
  );
  const [signal, setSignal] = useState<TaskSignal>(
    (context?.risk as TaskSignal) || "YELLOW",
  );
  const [status, setStatus] = useState<TaskStatus>("TODO");
  const [assignedTo, setAssignedTo] = useState(mail.assigned_to || ASSIGNEES[0]);
  // watcherNames holds display-only string names for UI; watchers (number[]) will be
  // wired to real user IDs by Task 11's assignee picker.
  const [watcherNames, setWatcherNames] = useState<string[]>([]);
  const [dueDate, setDueDate] = useState("");
  const [reminder, setReminder] = useState("");

  const watcherOptions = useMemo(
    () => ASSIGNEES.filter((a) => a !== assignedTo),
    [assignedTo],
  );

  function buildPayload(): CommunicationTaskCreate {
    return {
      title: title.trim(),
      description: description || undefined,
      customer_mail_id: mail.id,
      task_source: "CUSTOMER",
      supplier_name: customerName || null,
      supplier_po_no: poNo || null,
      material_name: material || null,
      assigned_to: assignedTo || null,
      assigned_by: "Admin User",
      watchers: [],
      priority,
      status,
      signal,
      due_date: dueDate ? new Date(dueDate).toISOString() : null,
      reminder_at: reminder ? new Date(reminder).toISOString() : null,
    };
  }

  function submit() {
    if (!title.trim() || saving) return;
    onSave(buildPayload());
  }

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4"
      onClick={onCancel}
    >
      <div
        className="w-full max-w-2xl rounded-xl bg-white shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-brand-border px-5 py-3">
          <div className="flex items-center gap-2">
            <UserPlus size={16} className="text-signal-red" />
            <span className="font-semibold">Create Customer Task</span>
          </div>
          <button className="rounded p-1 hover:bg-gray-100" onClick={onCancel}>
            <X size={18} />
          </button>
        </div>

        {/* Mail reference banner */}
        <div className="border-b border-brand-border bg-brand-surface px-5 py-2.5">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs">
            <span className="font-semibold text-brand-dark">Ref Mail #{mail.id}</span>
            <span className="truncate text-brand-muted">{mail.subject || "(no subject)"}</span>
            {customerEmail && (
              <span className="text-brand-muted">· {customerEmail}</span>
            )}
            {poNo && <span className="text-signal-red">· {poNo}</span>}
          </div>
        </div>

        <div className="grid max-h-[65vh] grid-cols-2 gap-4 overflow-y-auto p-5">
          <Field label="Task title" full>
            <input
              autoFocus
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className={INPUT}
              placeholder="e.g. Reply to customer with dispatch ETA"
            />
          </Field>
          <Field label="Description" full>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              className={`${INPUT} resize-none`}
              placeholder="Add context, expected outcome…"
            />
          </Field>

          <Field label="Customer name">
            <input
              value={customerName}
              onChange={(e) => setCustomerName(e.target.value)}
              className={INPUT}
              placeholder="Customer / contact"
            />
          </Field>
          <Field label="Customer email">
            <input value={customerEmail} disabled className={`${INPUT} bg-gray-50 text-brand-muted`} />
          </Field>

          <Field label="Linked PO number">
            <input
              value={poNo}
              onChange={(e) => setPoNo(e.target.value)}
              className={INPUT}
              placeholder="#4500123"
            />
          </Field>
          <Field label="Material">
            <input
              value={material}
              onChange={(e) => setMaterial(e.target.value)}
              className={INPUT}
              placeholder="Linked material"
            />
          </Field>

          <Field label="Priority">
            <select
              value={priority}
              onChange={(e) => setPriority(e.target.value as TaskPriority)}
              className={INPUT}
            >
              {(["P0", "P1", "P2", "P3"] as TaskPriority[]).map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Signal">
            <select
              value={signal}
              onChange={(e) => setSignal(e.target.value as TaskSignal)}
              className={INPUT}
            >
              <option value="GREEN">● Green — On Track</option>
              <option value="YELLOW">● Yellow — Reminder</option>
              <option value="RED">● Red — Delayed</option>
              <option value="BLACK">● Black — Critical</option>
            </select>
          </Field>

          <Field label="Due date">
            <input
              type="datetime-local"
              value={dueDate}
              onChange={(e) => setDueDate(e.target.value)}
              className={INPUT}
            />
          </Field>
          <Field label="Reminder">
            <input
              type="datetime-local"
              value={reminder}
              onChange={(e) => setReminder(e.target.value)}
              className={INPUT}
            />
          </Field>

          <Field label="Assigned to">
            <select
              value={assignedTo}
              onChange={(e) => setAssignedTo(e.target.value)}
              className={INPUT}
            >
              {ASSIGNEES.map((a) => (
                <option key={a} value={a}>
                  {a}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Status">
            <select
              value={status}
              onChange={(e) => setStatus(e.target.value as TaskStatus)}
              className={INPUT}
            >
              {TASK_STATUS_GROUPS.map((s) => (
                <option key={s.key} value={s.key}>
                  {s.label}
                </option>
              ))}
            </select>
          </Field>

          <Field label="Watchers" full>
            <div className="flex flex-wrap gap-1.5">
              {watcherOptions.map((a) => {
                const on = watcherNames.includes(a);
                return (
                  <button
                    key={a}
                    type="button"
                    onClick={() =>
                      setWatcherNames((prev) =>
                        on ? prev.filter((x) => x !== a) : [...prev, a],
                      )
                    }
                    className={`rounded-full border px-2 py-1 text-[11px] ${
                      on
                        ? "border-signal-red/30 bg-red-50 text-signal-red"
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

        <div className="flex justify-end gap-2 border-t border-brand-border px-5 py-3">
          <button
            className="rounded-md px-3 py-1.5 text-sm text-brand-muted hover:bg-gray-100"
            onClick={onCancel}
            disabled={saving}
          >
            Cancel
          </button>
          <button
            className="inline-flex items-center gap-1.5 rounded-md bg-signal-red px-3.5 py-1.5 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
            onClick={() => submit()}
            disabled={saving || !title.trim()}
          >
            {saving && <Loader2 size={14} className="animate-spin" />}
            Save Task
          </button>
        </div>
      </div>
    </div>
  );
}

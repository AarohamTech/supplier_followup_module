import type { CustomerMail } from "@/lib/types";
import { isToday } from "./hooks";

export interface QueueTab {
  key: string;
  label: string;
  match: (m: CustomerMail) => boolean;
}

/**
 * Client-side queue buckets. Grouping happens in a single memoized pass so
 * switching tabs never triggers a network request or a full recompute.
 */
export const QUEUE_TABS: QueueTab[] = [
  { key: "pending", label: "Pending Reply", match: (m) => m.status === "OPEN" },
  {
    key: "waiting_internal",
    label: "Waiting Internal",
    match: (m) => m.status === "IN_PROGRESS" && (m.open_task_count ?? 0) > 0,
  },
  {
    key: "waiting_supplier",
    label: "Waiting Supplier",
    match: (m) =>
      !!m.linked_supplier_po_no &&
      m.status !== "RESOLVED" &&
      m.status !== "CLOSED",
  },
  {
    key: "ready",
    label: "Ready To Reply",
    match: (m) => m.status === "IN_PROGRESS" && (m.open_task_count ?? 0) === 0,
  },
  {
    key: "replied",
    label: "Replied Today",
    match: (m) =>
      (m.status === "RESOLVED" || m.status === "CLOSED") && isToday(m.updated_at),
  },
];

export const PRIORITY_TONE: Record<string, string> = {
  P0: "bg-signal-red text-white",
  P1: "bg-amber-500 text-white",
  P2: "bg-blue-500 text-white",
  P3: "bg-gray-200 text-brand-dark",
};

/** AI-triage urgency badge tones. */
export const URGENCY_TONE: Record<string, string> = {
  HIGH: "bg-red-100 text-signal-red",
  MEDIUM: "bg-amber-100 text-amber-700",
  LOW: "bg-emerald-100 text-emerald-700",
};

/** Selectable assignees, mirrored from the Communication Hub task creator. */
export const ASSIGNEES = [
  "Rajesh Kumar",
  "Procurement Lead",
  "Stores User",
  "Quality User",
  "Purchase Head",
  "Sourcing Head",
  "Admin User",
];

export const TASK_STATUS_GROUPS: { key: string; label: string }[] = [
  { key: "TODO", label: "To Do" },
  { key: "WAITING_CUSTOMER", label: "Waiting Customer" },
  { key: "WAITING_SUPPLIER", label: "Waiting Supplier" },
  { key: "IN_PROGRESS", label: "In Progress" },
  { key: "DONE", label: "Done" },
];

/** Convert an ISO string to a value usable by <input type="datetime-local">. */
export function toDatetimeLocal(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(
    d.getDate(),
  )}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export const RISK_TONE: Record<string, string> = {
  GREEN: "bg-emerald-50 text-emerald-700 border-emerald-200",
  YELLOW: "bg-amber-50 text-amber-700 border-amber-200",
  RED: "bg-red-50 text-signal-red border-red-200",
  BLACK: "bg-gray-900 text-white border-gray-900",
};

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export function timeAgo(value: string | null | undefined): string {
  if (!value) return "";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "";
  const diff = Date.now() - d.getTime();
  const mins = Math.round(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs} hr ago`;
  const days = Math.round(hrs / 24);
  return `${days}d ago`;
}

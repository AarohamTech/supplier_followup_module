"use client";

/**
 * Pieces shared by the staff Task Manager (/tasks) and the portal task workspace
 * (/eportal/tasks, /portal/tasks): configurable board columns, quick filters,
 * the "Assigned by you" side panel, task file attachments and the admin board
 * settings dialog.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowDown,
  ArrowUp,
  ChevronRight,
  Download,
  Eye,
  EyeOff,
  FileText,
  Loader2,
  Paperclip,
  Plus,
  Send,
  Settings2,
  Trash2,
  X,
} from "lucide-react";

import { AttachButton, AttachmentDropArea } from "@/components/attachments/Attachments";
import { getToken } from "@/lib/auth-token";
import { useT } from "@/lib/i18n";
import type { AuthUser, CommunicationTask, TaskAttachment, TaskBoardColumn, TaskStatus } from "@/lib/types";

// ─── Columns ────────────────────────────────────────────────────────────────
// Literal class names so Tailwind's JIT keeps them.
const DOT: Record<string, string> = {
  slate: "bg-slate-400",
  blue: "bg-blue-400",
  amber: "bg-amber-400",
  violet: "bg-violet-400",
  cyan: "bg-cyan-400",
  rose: "bg-rose-500",
  green: "bg-green-500",
  orange: "bg-orange-400",
  pink: "bg-pink-400",
  teal: "bg-teal-400",
  indigo: "bg-indigo-400",
  lime: "bg-lime-500",
};

export function columnDot(color?: string | null) {
  return DOT[color || ""] ?? DOT.slate;
}

export const DEFAULT_BOARD_COLUMNS: TaskBoardColumn[] = [
  { key: "BACKLOG", label: "Backlog", color: "slate", hidden: false, builtin: true },
  { key: "TODO", label: "To Do", color: "blue", hidden: false, builtin: true },
  { key: "IN_PROGRESS", label: "In Progress", color: "amber", hidden: false, builtin: true },
  { key: "WAITING_SUPPLIER", label: "Waiting Supplier", color: "violet", hidden: false, builtin: true },
  { key: "WAITING_CUSTOMER", label: "Waiting Customer", color: "cyan", hidden: false, builtin: true },
  { key: "BLOCKED", label: "Blocked", color: "rose", hidden: false, builtin: true },
  { key: "DONE", label: "Done", color: "green", hidden: false, builtin: true },
];

type ColumnsResponse = { columns: TaskBoardColumn[]; colors: string[] };

/** Board layout from the backend; falls back to the built-ins if it can't load. */
export function useBoardColumns(fetcher?: () => Promise<ColumnsResponse>) {
  const [columns, setColumns] = useState<TaskBoardColumn[]>(DEFAULT_BOARD_COLUMNS);
  const [colors, setColors] = useState<string[]>(Object.keys(DOT));

  const reload = useCallback(async () => {
    if (!fetcher) return;
    try {
      const res = await fetcher();
      if (res?.columns?.length) setColumns(res.columns);
      if (res?.colors?.length) setColors(res.colors);
    } catch {
      /* keep the defaults */
    }
  }, [fetcher]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const visible = useMemo(() => columns.filter((c) => !c.hidden), [columns]);
  const byKey = useMemo(() => new Map(columns.map((c) => [c.key, c])), [columns]);
  return { columns, visible, byKey, colors, setColumns, reload };
}

/** Group tasks into the visible columns. A task in a hidden or unknown column
 *  lands in To Do (or the first visible column) so it never disappears. */
export function groupTasks(tasks: CommunicationTask[], visible: TaskBoardColumn[]) {
  const buckets = new Map<string, CommunicationTask[]>(visible.map((c) => [c.key, []]));
  const fallback = buckets.has("TODO") ? "TODO" : visible[0]?.key;
  tasks.forEach((t) => {
    const key = buckets.has(t.status) ? t.status : fallback;
    if (key) buckets.get(key)!.push(t);
  });
  return buckets;
}

// ─── "Who assigned it" helpers ──────────────────────────────────────────────
export function displayNameOf(user: AuthUser | null | undefined) {
  if (!user) return "";
  return user.full_name || user.username || user.email || `user#${user.id}`;
}

export function isAssignedByMe(t: CommunicationTask, user: AuthUser | null | undefined) {
  if (!user) return false;
  if (t.assigned_by_user_id != null) return t.assigned_by_user_id === user.id;
  // Rows from before the assigner id existed only carry the display name.
  return !!t.assigned_by && t.assigned_by === displayNameOf(user);
}

// ─── Quick filters ──────────────────────────────────────────────────────────
export type QuickFilter = "all" | "mine" | "assigned_by_me" | "overdue" | "due_today" | "high" | "unassigned";

function isOverdue(t: CommunicationTask) {
  return !!t.due_date && t.status !== "DONE" && new Date(t.due_date).getTime() < Date.now();
}

function isDueToday(t: CommunicationTask) {
  if (!t.due_date || t.status === "DONE") return false;
  return new Date(t.due_date).toDateString() === new Date().toDateString();
}

export function matchesQuickFilter(t: CommunicationTask, f: QuickFilter, user: AuthUser | null | undefined) {
  switch (f) {
    case "mine":
      return !!user && t.assigned_to_user_id === user.id;
    case "assigned_by_me":
      return isAssignedByMe(t, user);
    case "overdue":
      return isOverdue(t);
    case "due_today":
      return isDueToday(t);
    case "high":
      return t.priority === "HIGH";
    case "unassigned":
      return !t.assigned_to_user_id && !t.assigned_to;
    default:
      return true;
  }
}

const QUICK_FILTERS: { key: QuickFilter; label: string; needsUser?: boolean; internal?: boolean }[] = [
  { key: "all", label: "All tasks" },
  { key: "mine", label: "My tasks", needsUser: true, internal: true },
  { key: "assigned_by_me", label: "Assigned by me", needsUser: true, internal: true },
  { key: "overdue", label: "Overdue" },
  { key: "due_today", label: "Due today" },
  { key: "high", label: "High priority" },
  { key: "unassigned", label: "Unassigned", internal: true },
];

export function QuickFilterChips({
  value,
  onChange,
  tasks,
  user,
  showInternal = true,
}: {
  value: QuickFilter;
  onChange: (f: QuickFilter) => void;
  tasks: CommunicationTask[];
  user: AuthUser | null | undefined;
  /** Supplier view hides assignee-based chips (assignees are stripped there). */
  showInternal?: boolean;
}) {
  const { t } = useT();
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {QUICK_FILTERS.filter((f) => (showInternal || !f.internal) && (!f.needsUser || user)).map((f) => {
        const count = tasks.filter((task) => matchesQuickFilter(task, f.key, user)).length;
        const active = value === f.key;
        return (
          <button
            key={f.key}
            type="button"
            onClick={() => onChange(f.key)}
            className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold transition ${
              active ? "bg-ink text-white" : "bg-subtle text-brand-muted hover:text-brand-dark"
            }`}
          >
            {t(f.label)}
            <span
              className={`rounded-full px-1.5 text-[10px] font-bold ${
                active ? "bg-white/20 text-white" : "bg-card text-brand-muted"
              }`}
            >
              {count}
            </span>
          </button>
        );
      })}
    </div>
  );
}

// ─── "Assigned by you" side panel ───────────────────────────────────────────
export function AssignedByMePanel({
  tasks,
  user,
  columns,
  onOpen,
}: {
  tasks: CommunicationTask[];
  user: AuthUser | null | undefined;
  columns: Map<string, TaskBoardColumn>;
  onOpen: (t: CommunicationTask) => void;
}) {
  const { t } = useT();
  const [showDone, setShowDone] = useState(false);

  const mine = useMemo(
    () =>
      tasks.filter(
        (task) =>
          isAssignedByMe(task, user) &&
          // "assigned by you" means handed to SOMEONE ELSE
          task.assigned_to_user_id !== user?.id &&
          (task.assigned_to_user_id || task.assigned_to),
      ),
    [tasks, user],
  );
  const open = mine.filter((task) => task.status !== "DONE");
  const shown = showDone ? mine : open;

  // Group by assignee so "who has what" reads at a glance.
  const groups = useMemo(() => {
    const m = new Map<string, CommunicationTask[]>();
    shown.forEach((task) => {
      const who = task.assigned_to || t("Unassigned");
      if (!m.has(who)) m.set(who, []);
      m.get(who)!.push(task);
    });
    return [...m.entries()].sort((a, b) => b[1].length - a[1].length);
  }, [shown, t]);

  return (
    <aside className="flex w-full flex-col overflow-hidden rounded-lg border border-brand-border bg-card shadow-sm xl:w-80 xl:shrink-0">
      <div className="flex items-center justify-between border-b border-brand-border px-3 py-2">
        <div>
          <div className="text-xs font-semibold text-brand-dark">{t("Assigned by you")}</div>
          <div className="text-[11px] text-brand-muted">
            {t("{open} open · {total} total", { open: open.length, total: mine.length })}
          </div>
        </div>
        <label className="flex items-center gap-1 text-[11px] text-brand-muted">
          <input type="checkbox" checked={showDone} onChange={(e) => setShowDone(e.target.checked)} />
          {t("Show done")}
        </label>
      </div>
      <div className="max-h-[calc(100vh-340px)] min-h-[120px] flex-1 overflow-y-auto p-2">
        {groups.length === 0 && (
          <div className="px-2 py-6 text-center text-[11px] text-brand-muted">
            {t("Tasks you assign to others will show here.")}
          </div>
        )}
        {groups.map(([who, list]) => (
          <div key={who} className="mb-3 last:mb-0">
            <div className="mb-1 flex items-center gap-1.5 px-1">
              <span className="flex h-5 w-5 items-center justify-center rounded-full bg-ink text-[9px] text-white">
                {who.slice(0, 2).toUpperCase()}
              </span>
              <span className="truncate text-[11px] font-semibold text-brand-dark">{who}</span>
              <span className="ml-auto text-[10px] text-brand-muted">{list.length}</span>
            </div>
            <div className="space-y-1">
              {list.map((task) => {
                const col = columns.get(task.status);
                const overdue = isOverdue(task);
                return (
                  <button
                    key={task.id}
                    type="button"
                    onClick={() => onOpen(task)}
                    className="group flex w-full items-start gap-2 rounded-md border border-transparent px-2 py-1.5 text-left hover:border-brand-border hover:bg-subtle"
                  >
                    <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${columnDot(col?.color)}`} />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-xs font-medium text-brand-dark">{task.title}</span>
                      <span className="block truncate text-[10px] text-brand-muted">
                        {col ? t(col.label) : task.status}
                        {task.due_date && (
                          <span className={overdue ? " font-semibold text-rose-600" : ""}>
                            {" · "}
                            {overdue ? t("Overdue") : t("Due")} {new Date(task.due_date).toLocaleDateString()}
                          </span>
                        )}
                      </span>
                    </span>
                    <ChevronRight size={13} className="mt-1 shrink-0 text-brand-muted opacity-0 group-hover:opacity-100" />
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </aside>
  );
}

// ─── Task attachments ───────────────────────────────────────────────────────
export interface TaskAttachmentAdapter {
  list: (taskId: number) => Promise<TaskAttachment[]>;
  upload?: (taskId: number, file: File) => Promise<TaskAttachment>;
  remove?: (taskId: number, attachmentId: number) => Promise<void>;
  /** Scoped download URL for the current user type. */
  downloadUrl: (attachmentId: number) => string;
}

function fmtSize(bytes?: number) {
  if (!bytes || bytes <= 0) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function TaskAttachmentsSection({
  taskId,
  adapter,
  canUpload,
  canRemove,
  onCountChange,
}: {
  taskId: number;
  adapter: TaskAttachmentAdapter;
  canUpload: boolean;
  canRemove: (a: TaskAttachment) => boolean;
  onCountChange?: (n: number) => void;
}) {
  const { t } = useT();
  const [items, setItems] = useState<TaskAttachment[]>([]);
  const [uploading, setUploading] = useState(0);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const rows = await adapter.list(taskId);
      setItems(rows);
      onCountChange?.(rows.length);
    } catch {
      /* attachments are optional — keep the panel quiet */
    }
  }, [adapter, taskId, onCountChange]);

  useEffect(() => {
    void load();
  }, [load]);

  async function upload(files: File[]) {
    if (!adapter.upload || !files.length) return;
    setError(null);
    setUploading(files.length);
    for (const f of files) {
      try {
        await adapter.upload(taskId, f);
      } catch (err) {
        setError((err as Error).message);
      } finally {
        setUploading((n) => Math.max(0, n - 1));
      }
    }
    await load();
  }

  async function download(a: TaskAttachment) {
    setBusyId(a.id);
    try {
      const token = getToken();
      const res = await fetch(adapter.downloadUrl(a.id), {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error(t("Download failed"));
      const url = URL.createObjectURL(await res.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = a.filename;
      link.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusyId(null);
    }
  }

  async function remove(a: TaskAttachment) {
    if (!adapter.remove) return;
    if (!confirm(t("Remove {name}?", { name: a.filename }))) return;
    setBusyId(a.id);
    try {
      await adapter.remove(taskId, a.id);
      await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusyId(null);
    }
  }

  const body = (
    <div>
      <div className="mb-2 flex items-center gap-1.5">
        <Paperclip size={14} className="text-brand-muted" />
        <span className="text-sm font-semibold text-brand-dark">{t("Attachments")}</span>
        <span className="text-xs text-brand-muted">({items.length})</span>
        {canUpload && adapter.upload && (
          <span className="ml-auto">
            <AttachButton
              onFiles={(files) => void upload(files)}
              disabled={uploading > 0}
              className="inline-flex items-center gap-1 rounded-md border border-brand-border px-2 py-1 text-xs font-medium text-brand-dark hover:bg-subtle disabled:opacity-50"
            />
          </span>
        )}
      </div>

      {error && <div className="mb-2 rounded bg-rose-50 px-2 py-1 text-[11px] text-rose-700">{error}</div>}

      {items.length === 0 && !uploading ? (
        <div className="rounded-lg border border-dashed border-brand-border px-3 py-4 text-center text-xs text-brand-muted">
          {canUpload && adapter.upload ? t("No files yet — drop files here or use the paperclip.") : t("No files attached.")}
        </div>
      ) : (
        <ul className="divide-y divide-brand-border rounded-lg border border-brand-border">
          {items.map((a) => (
            <li key={a.id} className="flex items-center gap-2 px-2.5 py-2">
              <FileText size={15} className="shrink-0 text-signal-red" />
              <div className="min-w-0 flex-1">
                <div className="truncate text-xs font-medium text-brand-dark" title={a.filename}>
                  {a.filename}
                </div>
                <div className="truncate text-[10px] text-brand-muted">
                  {[fmtSize(a.size_bytes), a.uploaded_by, a.created_at ? new Date(a.created_at).toLocaleString() : ""]
                    .filter(Boolean)
                    .join(" · ")}
                </div>
              </div>
              <button
                type="button"
                title={t("Download")}
                onClick={() => void download(a)}
                disabled={busyId === a.id}
                className="rounded p-1 text-brand-muted hover:bg-subtle hover:text-brand-dark disabled:opacity-50"
              >
                {busyId === a.id ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />}
              </button>
              {adapter.remove && canRemove(a) && (
                <button
                  type="button"
                  title={t("Remove")}
                  onClick={() => void remove(a)}
                  disabled={busyId === a.id}
                  className="rounded p-1 text-brand-muted hover:bg-red-50 hover:text-signal-red disabled:opacity-50"
                >
                  <Trash2 size={14} />
                </button>
              )}
            </li>
          ))}
          {uploading > 0 && (
            <li className="flex items-center gap-2 px-2.5 py-2 text-xs text-brand-muted">
              <Loader2 size={14} className="animate-spin" />
              {t("Uploading {n} file(s)…", { n: uploading })}
            </li>
          )}
        </ul>
      )}
    </div>
  );

  return canUpload && adapter.upload ? (
    <AttachmentDropArea onFiles={(files) => void upload(files)} disabled={uploading > 0}>
      {body}
    </AttachmentDropArea>
  ) : (
    body
  );
}

// ─── Comment box (multi-line; Enter sends, Shift+Enter breaks the line) ─────
export function CommentComposer({
  value,
  onChange,
  onSubmit,
  busy,
}: {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  busy?: boolean;
}) {
  const { t } = useT();
  return (
    <div className="mb-3 flex items-end gap-2">
      <textarea
        value={value}
        rows={2}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            onSubmit();
          }
        }}
        placeholder={t("Add a comment…")}
        className="min-h-[44px] flex-1 resize-y rounded-md border border-brand-border px-3 py-2 text-sm"
      />
      <button
        onClick={onSubmit}
        disabled={busy || !value.trim()}
        className="inline-flex items-center gap-1 rounded-md bg-ink px-3 py-2 text-xs text-white disabled:opacity-50"
      >
        <Send size={12} /> {t("Send")}
      </button>
    </div>
  );
}

// ─── Admin: board settings ──────────────────────────────────────────────────
type DraftColumn = TaskBoardColumn & { _new?: boolean; _tmp?: string };

export function BoardSettingsModal({
  columns,
  colors,
  taskCounts,
  onClose,
  onSave,
}: {
  columns: TaskBoardColumn[];
  colors: string[];
  taskCounts: Record<string, number>;
  onClose: () => void;
  onSave: (cols: Partial<TaskBoardColumn>[]) => Promise<void>;
}) {
  const { t } = useT();
  const [draft, setDraft] = useState<DraftColumn[]>(() => columns.map((c) => ({ ...c })));
  const [newLabel, setNewLabel] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const update = (i: number, patch: Partial<DraftColumn>) =>
    setDraft((d) => d.map((c, j) => (j === i ? { ...c, ...patch } : c)));

  const move = (i: number, dir: -1 | 1) =>
    setDraft((d) => {
      const j = i + dir;
      if (j < 0 || j >= d.length) return d;
      const next = [...d];
      [next[i], next[j]] = [next[j], next[i]];
      return next;
    });

  const addColumn = () => {
    const label = newLabel.trim();
    if (!label) return;
    setDraft((d) => {
      // New custom columns go just before Done, where work usually ends up.
      const doneIdx = d.findIndex((c) => c.key === "DONE");
      const col: DraftColumn = {
        key: `NEW_${Date.now()}` as TaskStatus,
        label,
        color: "teal",
        hidden: false,
        builtin: false,
        _new: true,
      };
      const next = [...d];
      next.splice(doneIdx >= 0 ? doneIdx : next.length, 0, col);
      return next;
    });
    setNewLabel("");
  };

  async function save() {
    setSaving(true);
    setError(null);
    try {
      await onSave(
        draft.map((c) => ({
          // A placeholder key tells the backend to mint a real C_* key.
          key: c._new ? undefined : c.key,
          label: c.label.trim(),
          color: c.color,
          hidden: c.hidden,
        })),
      );
      onClose();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/50 p-4" onClick={onClose}>
      <div
        className="flex max-h-[90vh] w-full max-w-2xl flex-col overflow-hidden rounded-xl bg-card shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-brand-border px-5 py-3">
          <div className="flex items-center gap-2">
            <Settings2 size={16} className="text-signal-red" />
            <div>
              <div className="font-semibold">{t("Board columns")}</div>
              <div className="text-[11px] text-brand-muted">
                {t("Rename, reorder, recolour or hide columns, or add your own. Applies to everyone.")}
              </div>
            </div>
          </div>
          <button className="rounded p-1 hover:bg-subtle" onClick={onClose}>
            <X size={18} />
          </button>
        </div>

        <div className="flex-1 space-y-1.5 overflow-y-auto p-4">
          {draft.map((c, i) => {
            const count = taskCounts[c.key] ?? 0;
            return (
              <div
                key={c.key}
                className={`flex items-center gap-2 rounded-lg border border-brand-border px-2 py-1.5 ${c.hidden ? "opacity-60" : ""}`}
              >
                <div className="flex flex-col">
                  <button type="button" onClick={() => move(i, -1)} disabled={i === 0} className="text-brand-muted hover:text-brand-dark disabled:opacity-30" title={t("Move up")}>
                    <ArrowUp size={12} />
                  </button>
                  <button type="button" onClick={() => move(i, 1)} disabled={i === draft.length - 1} className="text-brand-muted hover:text-brand-dark disabled:opacity-30" title={t("Move down")}>
                    <ArrowDown size={12} />
                  </button>
                </div>
                <select
                  value={c.color}
                  onChange={(e) => update(i, { color: e.target.value })}
                  className="rounded border border-brand-border bg-card px-1 py-1 text-xs"
                  title={t("Colour")}
                >
                  {colors.map((col) => (
                    <option key={col} value={col}>
                      {col}
                    </option>
                  ))}
                </select>
                <span className={`h-3 w-3 shrink-0 rounded-full ${columnDot(c.color)}`} />
                <input
                  value={c.label}
                  maxLength={40}
                  onChange={(e) => update(i, { label: e.target.value })}
                  className="min-w-0 flex-1 rounded border border-brand-border px-2 py-1 text-sm"
                />
                <span className="hidden text-[10px] text-brand-muted sm:inline">
                  {c.builtin ? t("built-in") : t("custom")} · {t("{n} tasks", { n: count })}
                </span>
                <button
                  type="button"
                  onClick={() => update(i, { hidden: !c.hidden })}
                  disabled={c.key === "DONE"}
                  title={c.key === "DONE" ? t("Done can't be hidden") : c.hidden ? t("Show") : t("Hide")}
                  className="rounded p-1 text-brand-muted hover:bg-subtle disabled:opacity-30"
                >
                  {c.hidden ? <EyeOff size={14} /> : <Eye size={14} />}
                </button>
                {!c.builtin ? (
                  <button
                    type="button"
                    onClick={() => {
                      if (
                        count > 0 &&
                        !confirm(t("{n} task(s) in this column will move to To Do. Delete the column?", { n: count }))
                      )
                        return;
                      setDraft((d) => d.filter((_, j) => j !== i));
                    }}
                    title={t("Delete column")}
                    className="rounded p-1 text-brand-muted hover:bg-red-50 hover:text-signal-red"
                  >
                    <Trash2 size={14} />
                  </button>
                ) : (
                  <span className="w-[22px]" />
                )}
              </div>
            );
          })}

          <div className="flex items-center gap-2 pt-2">
            <input
              value={newLabel}
              maxLength={40}
              onChange={(e) => setNewLabel(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && addColumn()}
              placeholder={t("New column name, e.g. QC Pending")}
              className="flex-1 rounded-md border border-brand-border px-2.5 py-1.5 text-sm"
            />
            <button type="button" onClick={addColumn} disabled={!newLabel.trim()} className="btn-outline text-xs">
              <Plus size={13} /> {t("Add column")}
            </button>
          </div>
          {error && <div className="rounded bg-rose-50 px-2 py-1 text-xs text-rose-700">{error}</div>}
        </div>

        <div className="flex justify-end gap-2 border-t border-brand-border px-5 py-3">
          <button className="btn-ghost" onClick={onClose} disabled={saving}>
            {t("Cancel")}
          </button>
          <button className="btn-primary" onClick={() => void save()} disabled={saving || draft.some((c) => !c.label.trim())}>
            {saving ? <Loader2 size={14} className="animate-spin" /> : null}
            <span className="ml-1.5">{t("Save board")}</span>
          </button>
        </div>
      </div>
    </div>
  );
}

"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Loader2, Pencil, RefreshCw, UserCheck, X } from "lucide-react";

import type { AssignableUser, SupplierAssignmentRow } from "@/lib/types";
import { useT } from "@/lib/i18n";
import PageHeader from "@/components/layout/PageHeader";
import Pager from "@/components/ui/Pager";

const PAGE_SIZE = 50;

/** Data access for the Supplier Assignment screen. The staff page and the
 *  employee portal pass different endpoints; the screen itself is the same. */
export type SupplierAssignmentsAdapter = {
  list: (params: { search?: string; page?: number; size?: number }) => Promise<{
    suppliers: SupplierAssignmentRow[];
    total: number;
  }>;
  assignableUsers: () => Promise<{ users: AssignableUser[] }>;
  setAssignees: (supplierId: number, userIds: number[]) => Promise<SupplierAssignmentRow>;
};

// Emails here are placeholders, so never show them — use name (or username / id)
// and a small role/emp-code hint instead.
function personLabel(u: AssignableUser): string {
  return u.full_name || u.username || `User #${u.user_id}`;
}
function personMeta(u: AssignableUser): string {
  return [u.role, u.emp_code].filter(Boolean).join(" · ");
}

export default function SupplierAssignmentsView({
  adapter,
  canEdit,
}: {
  adapter: SupplierAssignmentsAdapter;
  canEdit: boolean;
}) {
  const { t } = useT();
  const [rows, setRows] = useState<SupplierAssignmentRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [users, setUsers] = useState<AssignableUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [note, setNote] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [editing, setEditing] = useState<SupplierAssignmentRow | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [userSearch, setUserSearch] = useState("");
  const [saving, setSaving] = useState(false);

  // Assignable users load once (bounded internal-user list; the modal filters them).
  useEffect(() => {
    adapter
      .assignableUsers()
      .then((u) => setUsers(u.users || []))
      .catch((e) => setLoadError((e as Error).message));
  }, [adapter]);

  // Debounce the supplier search; reset to page 1 whenever the query changes.
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebounced(search.trim());
      setPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [search]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const a = await adapter.list({ search: debounced || undefined, page, size: PAGE_SIZE });
      setRows(a.suppliers || []);
      setTotal(a.total);
      setLoadError(null);
    } catch (e) {
      setLoadError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [adapter, debounced, page]);

  useEffect(() => {
    void load();
  }, [load]);

  function openEditor(row: SupplierAssignmentRow) {
    setEditing(row);
    setSelected(new Set(row.assignees.map((a) => a.user_id)));
    setUserSearch("");
    setNote(null);
    setSaveError(null);
  }

  const visibleUsers = useMemo(() => {
    const q = userSearch.trim().toLowerCase();
    if (!q) return users;
    return users.filter((u) =>
      `${u.full_name || ""} ${u.username || ""} ${u.emp_code || ""} ${u.role}`.toLowerCase().includes(q),
    );
  }, [users, userSearch]);

  function toggle(id: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function save() {
    if (!editing) return;
    setSaving(true);
    setNote(null);
    setSaveError(null);
    try {
      const updated = await adapter.setAssignees(editing.supplier_id, Array.from(selected));
      setRows((prev) => prev.map((r) => (r.supplier_id === updated.supplier_id ? updated : r)));
      setEditing(null);
      setNote(t("Saved assignees for {name}.", { name: updated.supplier_name }));
    } catch (e) {
      setSaveError((e as Error).message || t("Could not save assignees."));
    } finally {
      setSaving(false);
    }
  }

  const cols = canEdit ? 3 : 2;

  return (
    <div className="page-stack">
      <PageHeader
        title={t("Supplier Assignments")}
        description={t("Map each supplier to the people responsible for it. A supplier's incoming email is routed to those people in-app (they get a notification).")}
        icon={UserCheck}
      />

      {loadError && (
        <div className="flex items-center justify-between gap-3 rounded-md bg-red-50 px-3 py-2 text-xs text-signal-red" role="alert">
          <span>{loadError}</span>
          <button className="btn-ghost text-xs" onClick={() => void load()}>
            <RefreshCw size={12} /> {t("Retry")}
          </button>
        </div>
      )}
      {note && <div className="card p-3 text-xs text-brand-muted">{note}</div>}

      <div className="card p-3">
        <input
          className="border border-brand-border rounded px-3 py-2 text-sm w-full max-w-sm"
          placeholder={t("Search suppliers…")}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-subtle text-xs text-brand-muted">
            <tr>
              <th className="text-left font-medium px-4 py-2">{t("Supplier")}</th>
              <th className="text-left font-medium px-4 py-2">{t("Assigned people")}</th>
              {canEdit && <th className="text-right font-medium px-4 py-2">{t("Actions")}</th>}
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr><td colSpan={cols} className="px-4 py-6 text-center text-brand-muted">
                <Loader2 className="inline animate-spin" size={16} /> {t("Loading…")}
              </td></tr>
            )}
            {!loading && rows.length === 0 && (
              <tr><td colSpan={cols} className="px-4 py-6 text-center text-brand-muted">{t("No suppliers.")}</td></tr>
            )}
            {rows.map((row) => (
              <tr key={row.supplier_id} className="border-t border-brand-border/60 align-top">
                <td className="px-4 py-2 font-medium">{row.supplier_name}</td>
                <td className="px-4 py-2">
                  {row.assignees.length === 0 ? (
                    <span className="text-xs text-brand-muted">{t("Not assigned")}</span>
                  ) : (
                    <div className="flex flex-wrap gap-1">
                      {row.assignees.map((a) => (
                        <span key={a.user_id} className="px-2 py-0.5 rounded text-xs bg-subtle text-brand-dark">
                          {personLabel(a)}
                        </span>
                      ))}
                    </div>
                  )}
                </td>
                {canEdit && (
                  <td className="px-4 py-2">
                    <div className="flex justify-end">
                      <button type="button" onClick={() => openEditor(row)} className="btn-outline text-xs inline-flex items-center gap-1">
                        <Pencil size={13} /> {t("Edit")}
                      </button>
                    </div>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {!loading && <Pager page={page} size={PAGE_SIZE} total={total} onPage={setPage} unit="suppliers" />}

      {editing && (
        <div className="fixed inset-0 z-50 bg-black/40 grid place-items-center p-4" onClick={() => !saving && setEditing(null)}>
          <div
            className="bg-card rounded-lg shadow-xl w-full max-w-md max-h-[90vh] flex flex-col"
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
          >
            <div className="flex items-center justify-between border-b border-brand-border px-5 py-3">
              <div className="font-semibold text-sm">{t("Assign people — {name}", { name: editing.supplier_name })}</div>
              <button type="button" onClick={() => setEditing(null)} className="p-1 rounded hover:bg-subtle" aria-label={t("Close")}>
                <X size={18} />
              </button>
            </div>

            {saveError && (
              <div className="mx-5 mt-4 rounded-md border border-red-100 bg-red-50 px-3 py-2 text-xs text-signal-red" role="alert">
                {saveError}
              </div>
            )}
            <div className="px-5 pt-4">
              <input
                className="border border-brand-border rounded px-3 py-2 text-sm w-full"
                placeholder={t("Search people…")}
                value={userSearch}
                onChange={(e) => setUserSearch(e.target.value)}
                autoFocus
              />
            </div>
            <div className="overflow-y-auto px-5 pb-2 pt-2 space-y-1">
              {users.length === 0 && <div className="text-xs text-brand-muted">{t("No assignable users.")}</div>}
              {users.length > 0 && visibleUsers.length === 0 && (
                <div className="text-xs text-brand-muted py-2">{t("No people match “{q}”.", { q: userSearch })}</div>
              )}
              {visibleUsers.map((u) => (
                <label key={u.user_id} className="flex items-center gap-2 text-sm py-1 cursor-pointer">
                  <input type="checkbox" checked={selected.has(u.user_id)} onChange={() => toggle(u.user_id)} />
                  <span>{personLabel(u)}</span>
                  {personMeta(u) && <span className="text-xs text-brand-muted">{personMeta(u)}</span>}
                </label>
              ))}
            </div>

            <div className="border-t border-brand-border px-5 py-3 flex items-center justify-between">
              <span className="text-xs text-brand-muted">{t("{n} selected", { n: selected.size })}</span>
              <button type="button" disabled={saving} onClick={save} className="btn-dark">
                {saving ? t("Saving…") : t("Save")}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

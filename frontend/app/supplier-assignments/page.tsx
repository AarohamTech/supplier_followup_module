"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Loader2, Pencil, UserCheck, X } from "lucide-react";

import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { AssignableUser, SupplierAssignmentRow } from "@/lib/types";
import PageHeader from "@/components/layout/PageHeader";

export default function SupplierAssignmentsPage() {
  const { hasRole } = useAuth();
  const canEdit = hasRole("manager");

  const [rows, setRows] = useState<SupplierAssignmentRow[]>([]);
  const [users, setUsers] = useState<AssignableUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [note, setNote] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [editing, setEditing] = useState<SupplierAssignmentRow | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [userSearch, setUserSearch] = useState("");
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [a, u] = await Promise.all([api.listSupplierAssignments(), api.assignableUsers()]);
      setRows(a.suppliers || []);
      setUsers(u.users || []);
    } catch (e) {
      setNote((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return q ? rows.filter((r) => r.supplier_name.toLowerCase().includes(q)) : rows;
  }, [rows, search]);

  function openEditor(row: SupplierAssignmentRow) {
    setEditing(row);
    setSelected(new Set(row.assignees.map((a) => a.user_id)));
    setUserSearch("");
    setNote(null);
  }

  const visibleUsers = useMemo(() => {
    const q = userSearch.trim().toLowerCase();
    if (!q) return users;
    return users.filter((u) =>
      `${u.full_name || ""} ${u.email} ${u.role}`.toLowerCase().includes(q),
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
    try {
      const updated = await api.setSupplierAssignees(editing.supplier_id, Array.from(selected));
      setRows((prev) => prev.map((r) => (r.supplier_id === updated.supplier_id ? updated : r)));
      setEditing(null);
      setNote(`Saved assignees for ${updated.supplier_name}.`);
    } catch (e) {
      setNote((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="page-stack">
      <PageHeader
        title="Supplier Assignments"
        description="Map each supplier to the people responsible for it. A supplier's incoming email is routed to those people in-app (they get a notification)."
        icon={UserCheck}
      />

      {note && <div className="card p-3 text-xs text-brand-muted">{note}</div>}

      <div className="card p-3">
        <input
          className="border border-brand-border rounded px-3 py-2 text-sm w-full max-w-sm"
          placeholder="Search suppliers…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-subtle text-xs text-brand-muted">
            <tr>
              <th className="text-left font-medium px-4 py-2">Supplier</th>
              <th className="text-left font-medium px-4 py-2">Assigned people</th>
              {canEdit && <th className="text-right font-medium px-4 py-2">Actions</th>}
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr><td colSpan={canEdit ? 3 : 2} className="px-4 py-6 text-center text-brand-muted">
                <Loader2 className="inline animate-spin" size={16} /> Loading…
              </td></tr>
            )}
            {!loading && filtered.length === 0 && (
              <tr><td colSpan={canEdit ? 3 : 2} className="px-4 py-6 text-center text-brand-muted">No suppliers.</td></tr>
            )}
            {filtered.map((row) => (
              <tr key={row.supplier_id} className="border-t border-brand-border/60 align-top">
                <td className="px-4 py-2 font-medium">{row.supplier_name}</td>
                <td className="px-4 py-2">
                  {row.assignees.length === 0 ? (
                    <span className="text-xs text-brand-muted">Not assigned</span>
                  ) : (
                    <div className="flex flex-wrap gap-1">
                      {row.assignees.map((a) => (
                        <span key={a.user_id} className="px-2 py-0.5 rounded text-xs bg-subtle text-brand-dark">
                          {a.full_name || a.email}
                        </span>
                      ))}
                    </div>
                  )}
                </td>
                {canEdit && (
                  <td className="px-4 py-2">
                    <div className="flex justify-end">
                      <button type="button" onClick={() => openEditor(row)} className="btn-outline text-xs inline-flex items-center gap-1">
                        <Pencil size={13} /> Edit
                      </button>
                    </div>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Editor modal */}
      {editing && (
        <div className="fixed inset-0 z-50 bg-black/40 grid place-items-center p-4" onClick={() => setEditing(null)}>
          <div
            className="bg-card rounded-lg shadow-xl w-full max-w-md max-h-[90vh] flex flex-col"
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
          >
            <div className="flex items-center justify-between border-b border-brand-border px-5 py-3">
              <div className="font-semibold text-sm">Assign people — {editing.supplier_name}</div>
              <button type="button" onClick={() => setEditing(null)} className="p-1 rounded hover:bg-subtle" aria-label="Close">
                <X size={18} />
              </button>
            </div>

            <div className="px-5 pt-4">
              <input
                className="border border-brand-border rounded px-3 py-2 text-sm w-full"
                placeholder="Search people…"
                value={userSearch}
                onChange={(e) => setUserSearch(e.target.value)}
                autoFocus
              />
            </div>
            <div className="overflow-y-auto px-5 pb-2 pt-2 space-y-1">
              {users.length === 0 && <div className="text-xs text-brand-muted">No assignable users.</div>}
              {users.length > 0 && visibleUsers.length === 0 && (
                <div className="text-xs text-brand-muted py-2">No people match “{userSearch}”.</div>
              )}
              {visibleUsers.map((u) => (
                <label key={u.user_id} className="flex items-center gap-2 text-sm py-1 cursor-pointer">
                  <input type="checkbox" checked={selected.has(u.user_id)} onChange={() => toggle(u.user_id)} />
                  <span>{u.full_name || u.email}</span>
                  <span className="text-xs text-brand-muted">{u.email} · {u.role}</span>
                </label>
              ))}
            </div>

            <div className="border-t border-brand-border px-5 py-3 flex items-center justify-between">
              <span className="text-xs text-brand-muted">{selected.size} selected</span>
              <button type="button" disabled={saving} onClick={save} className="btn-dark">
                {saving ? "Saving…" : "Save"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

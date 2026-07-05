"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Loader2, Plus, RotateCcw, Trash2, ShieldCheck } from "lucide-react";

import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { AuthUser, Role } from "@/lib/types";
import PageHeader from "@/components/layout/PageHeader";
import Pager from "@/components/ui/Pager";

const SIZE = 50;
const ALL_ROLES: Role[] = ["viewer", "user", "manager", "admin"];

const ROLE_BADGE: Record<Role, string> = {
  admin: "bg-red-50 text-signal-red",
  manager: "bg-amber-50 text-amber-700",
  user: "bg-blue-50 text-blue-700",
  viewer: "bg-subtle text-brand-muted",
};

export default function UsersAdminPage() {
  const { user: me, hasRole } = useAuth();
  const [users, setUsers] = useState<AuthUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);

  // create form
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<Role>("user");
  const [creating, setCreating] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    api
      .listUsers()
      // Staff page manages internal accounts only; supplier portal logins are
      // provisioned + managed from Email Master.
      .then((list) => setUsers(list.filter((u) => u.supplier_id == null)))
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (hasRole("admin")) load();
    else setLoading(false);
  }, [hasRole, load]);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 2500);
    return () => clearTimeout(t);
  }, [toast]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return users;
    return users.filter((u) => `${u.full_name ?? ""} ${u.email} ${u.role}`.toLowerCase().includes(q));
  }, [users, search]);
  useEffect(() => setPage(1), [search]);
  const paged = useMemo(() => filtered.slice((page - 1) * SIZE, page * SIZE), [filtered, page]);

  if (!hasRole("admin")) {
    return (
      <div className="empty-state">
        <ShieldCheck className="mx-auto mb-2 h-6 w-6 text-brand-muted" />
        You need the <strong>admin</strong> role to manage users.
      </div>
    );
  }

  const onCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setCreating(true);
    try {
      await api.createUser({ email: email.trim(), password, full_name: fullName || null, role });
      setEmail("");
      setFullName("");
      setPassword("");
      setRole("user");
      setToast("User created.");
      load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setCreating(false);
    }
  };

  const onChangeRole = async (u: AuthUser, next: Role) => {
    try {
      const updated = await api.updateUser(u.id, { role: next });
      setUsers((prev) => prev.map((x) => (x.id === u.id ? updated : x)));
      setToast(`Role updated to ${next}.`);
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const onToggleActive = async (u: AuthUser) => {
    try {
      const updated = await api.updateUser(u.id, { is_active: !u.is_active });
      setUsers((prev) => prev.map((x) => (x.id === u.id ? updated : x)));
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const onResetPassword = async (u: AuthUser) => {
    const pwd = window.prompt(`New password for ${u.email} (min 8 chars):`);
    if (!pwd) return;
    try {
      await api.resetUserPassword(u.id, pwd);
      setToast("Password reset.");
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const onDelete = async (u: AuthUser) => {
    if (!window.confirm(`Delete ${u.email}? This cannot be undone.`)) return;
    try {
      await api.deleteUser(u.id);
      setUsers((prev) => prev.filter((x) => x.id !== u.id));
      setToast("User deleted.");
    } catch (err) {
      setError((err as Error).message);
    }
  };

  return (
    <div className="page-stack">
      <PageHeader
        title="User Management"
        description="Create users, assign roles and manage account access."
        icon={ShieldCheck}
        actions={
          <div className="flex items-center gap-2">
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search users…"
              className="input max-w-xs"
            />
            {toast && <span className="rounded-md bg-ink px-3 py-1.5 text-xs text-white">{toast}</span>}
          </div>
        }
      />

      {error && (
        <div className="rounded-md bg-red-50 px-3 py-2 text-xs text-signal-red">{error}</div>
      )}

      {/* Create user */}
      <form
        onSubmit={onCreate}
        className="grid grid-cols-1 gap-3 rounded-xl border border-brand-border bg-card p-4 md:grid-cols-5"
      >
        <input
          type="email" required placeholder="Email" value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="rounded-md border border-brand-border px-3 py-2 text-sm outline-none focus:border-signal-red md:col-span-2"
        />
        <input
          type="text" placeholder="Full name" value={fullName}
          onChange={(e) => setFullName(e.target.value)}
          className="rounded-md border border-brand-border px-3 py-2 text-sm outline-none focus:border-signal-red"
        />
        <input
          type="password" required minLength={8} placeholder="Password (min 8)" value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="rounded-md border border-brand-border px-3 py-2 text-sm outline-none focus:border-signal-red"
        />
        <div className="flex gap-2">
          <select
            value={role}
            onChange={(e) => setRole(e.target.value as Role)}
            className="flex-1 rounded-md border border-brand-border px-2 py-2 text-sm capitalize outline-none focus:border-signal-red"
          >
            {ALL_ROLES.map((r) => (
              <option key={r} value={r}>{r}</option>
            ))}
          </select>
          <button
            type="submit" disabled={creating}
            className="flex items-center gap-1 rounded-md bg-signal-red px-3 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-60"
          >
            {creating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
            Add
          </button>
        </div>
      </form>

      {/* Users table */}
      <div className="overflow-hidden rounded-xl border border-brand-border bg-card">
        <table className="w-full text-sm">
          <thead className="bg-brand-surface text-left text-xs uppercase tracking-wider text-brand-muted">
            <tr>
              <th className="px-4 py-2.5">User</th>
              <th className="px-4 py-2.5">Role</th>
              <th className="px-4 py-2.5">Status</th>
              <th className="px-4 py-2.5">Last login</th>
              <th className="px-4 py-2.5 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-brand-border">
            {loading ? (
              <tr><td colSpan={5} className="px-4 py-8 text-center text-brand-muted">Loading…</td></tr>
            ) : filtered.length === 0 ? (
              <tr><td colSpan={5} className="px-4 py-8 text-center text-brand-muted">No users.</td></tr>
            ) : (
              paged.map((u) => {
                const isSelf = u.id === me?.id;
                return (
                  <tr key={u.id} className="hover:bg-subtle">
                    <td className="px-4 py-2.5">
                      <div className="font-medium text-brand-dark">{u.full_name || "—"}</div>
                      <div className="text-xs text-brand-muted">{u.email}{isSelf && " (you)"}</div>
                    </td>
                    <td className="px-4 py-2.5">
                      <select
                        value={u.role}
                        onChange={(e) => onChangeRole(u, e.target.value as Role)}
                        className={`rounded-full px-2 py-1 text-xs font-medium capitalize outline-none ${ROLE_BADGE[u.role as Role] ?? ""}`}
                      >
                        {ALL_ROLES.map((r) => (
                          <option key={r} value={r}>{r}</option>
                        ))}
                      </select>
                    </td>
                    <td className="px-4 py-2.5">
                      <button
                        onClick={() => onToggleActive(u)}
                        className={`rounded-full px-2.5 py-1 text-xs font-medium ${
                          u.is_active ? "bg-emerald-50 text-emerald-700" : "bg-subtle text-brand-muted"
                        }`}
                      >
                        {u.is_active ? "Active" : "Inactive"}
                      </button>
                    </td>
                    <td className="px-4 py-2.5 text-xs text-brand-muted">
                      {u.last_login_at ? new Date(u.last_login_at).toLocaleString() : "Never"}
                    </td>
                    <td className="px-4 py-2.5">
                      <div className="flex items-center justify-end gap-1">
                        <button
                          onClick={() => onResetPassword(u)}
                          title="Reset password"
                          className="rounded-md p-1.5 text-brand-muted hover:bg-subtle hover:text-brand-dark"
                        >
                          <RotateCcw className="h-4 w-4" />
                        </button>
                        <button
                          onClick={() => onDelete(u)}
                          disabled={isSelf}
                          title={isSelf ? "You cannot delete yourself" : "Delete user"}
                          className="rounded-md p-1.5 text-brand-muted hover:bg-red-50 hover:text-signal-red disabled:opacity-30"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
      {!loading && <Pager page={page} size={SIZE} total={filtered.length} onPage={setPage} unit="users" />}
    </div>
  );
}

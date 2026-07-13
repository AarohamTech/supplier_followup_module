"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Download, KeyRound, Loader2, Pencil, Power, ShieldCheck, Trash2, Upload, UserPlus, X } from "lucide-react";

import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { AuthUser, EmployeeCredential } from "@/lib/types";

function fmtDate(d?: string | null) {
  if (!d) return "—";
  const dt = new Date(d);
  return isNaN(dt.getTime()) ? "—" : dt.toLocaleString();
}

export default function EmployeesAdminPage() {
  const { hasRole, company } = useAuth();
  const isAdmin = hasRole("admin");

  const [list, setList] = useState<AuthUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [creds, setCreds] = useState<EmployeeCredential[]>([]);
  const [credsNote, setCredsNote] = useState<string>("");
  const fileRef = useRef<HTMLInputElement>(null);

  const [newUsername, setNewUsername] = useState("");
  const [newName, setNewName] = useState("");
  const [newEmpCode, setNewEmpCode] = useState("");

  const [editUser, setEditUser] = useState<AuthUser | null>(null);
  const [editEmail, setEditEmail] = useState("");
  const [editName, setEditName] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setList(await api.listEmployeeLogins());
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isAdmin) void load();
  }, [isAdmin, load]);

  if (!isAdmin) {
    return (
      <div className="page-stack">
        <div className="card p-6 text-sm text-brand-muted">You need an admin account to manage employee logins.</div>
      </div>
    );
  }

  const onImport = async (file: File) => {
    setBusy(true);
    setError(null);
    try {
      const res = await api.importEmployeeSheet(file);
      setCreds(res.created || []);
      const parts = [`${res.created?.length || 0} created`];
      if (res.reactivated?.length) parts.push(`${res.reactivated.length} reactivated`);
      if (res.conflicts?.length) parts.push(`${res.conflicts.length} conflicts`);
      if (res.skipped?.length) parts.push(`${res.skipped.length} skipped`);
      setCredsNote(`Imported sheet: ${parts.join(", ")}.`);
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const onCreate = async () => {
    if (!newUsername.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const r = await api.createEmployeeLogin({
        username: newUsername.trim(),
        full_name: newName.trim() || null,
        emp_code: newEmpCode.trim() || null,
      });
      setCreds([{ username: r.username, full_name: r.full_name, temp_password: r.temp_password, emp_code: r.emp_code }]);
      setCredsNote(`Created ${r.username}.`);
      setNewUsername("");
      setNewName("");
      setNewEmpCode("");
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const openEdit = (u: AuthUser) => {
    setEditUser(u);
    setEditEmail(u.email?.endsWith("@employee.local") ? "" : u.email || "");
    setEditName(u.full_name || "");
    setError(null);
  };

  const onSaveEdit = async () => {
    if (!editUser) return;
    setBusy(true);
    setError(null);
    try {
      const body: { email?: string; full_name?: string | null } = { full_name: editName.trim() || null };
      if (editEmail.trim()) body.email = editEmail.trim();
      await api.updateEmployeeLogin(editUser.id, body);
      setEditUser(null);
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const onReset = async (u: AuthUser) => {
    setBusy(true);
    setError(null);
    try {
      const r = await api.resetEmployeeLogin(u.id);
      setCreds([{ username: r.username, full_name: r.full_name, temp_password: r.temp_password }]);
      setCredsNote(`Reset password for ${r.username}.`);
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const onToggleActive = async (u: AuthUser) => {
    setBusy(true);
    try {
      if (u.is_active) await api.deactivateEmployeeLogin(u.id);
      else await api.activateEmployeeLogin(u.id);
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const onDelete = async (u: AuthUser) => {
    if (!confirm(`Delete employee login "${u.username}"? This cannot be undone.`)) return;
    setBusy(true);
    try {
      await api.deleteEmployeeLogin(u.id);
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const downloadCreds = async () => {
    try {
      const blob = await api.downloadEmployeeCredentials(creds);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "employee_credentials.xlsx";
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <div className="page-stack">
      <div className="page-header">
        <div>
          <h1 className="page-title">Employee Logins</h1>
          <p className="page-subtitle">
            Provision and manage internal employee portal accounts
            {company ? <> for <span className="font-medium">{company.display_name}</span> — new logins are pinned to this company (switch companies from the top bar)</> : null}.
          </p>
        </div>
        <label className="btn-primary cursor-pointer">
          {busy ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />} Import employee sheet
          <input
            ref={fileRef}
            type="file"
            accept=".xlsx"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void onImport(f);
            }}
          />
        </label>
      </div>

      {error && <div className="rounded-md bg-red-50 px-3 py-2 text-xs text-signal-red">{error}</div>}

      {/* Newly generated credentials (temp passwords are only shown once) */}
      {creds.length > 0 && (
        <div className="card border-emerald-200 bg-emerald-50/40 p-4">
          <div className="mb-2 flex items-center justify-between">
            <div className="text-sm font-semibold text-brand-dark">{credsNote} Share these temporary passwords now.</div>
            <button onClick={downloadCreds} className="btn-ghost text-xs">
              <Download size={14} /> Download Excel
            </button>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="text-left text-[10px] uppercase text-brand-muted">
                <tr>
                  <th className="px-2 py-1">Name</th>
                  <th className="px-2 py-1">Username</th>
                  <th className="px-2 py-1">Temporary password</th>
                </tr>
              </thead>
              <tbody>
                {creds.map((c, i) => (
                  <tr key={i} className="border-t border-emerald-100">
                    <td className="px-2 py-1">{c.full_name || "—"}</td>
                    <td className="px-2 py-1 font-medium">{c.username}</td>
                    <td className="px-2 py-1 font-mono">{c.temp_password}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Add a single employee */}
      <div className="card p-4">
        <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-brand-dark">
          <UserPlus size={16} className="text-signal-red" /> Add a single employee
        </div>
        <div className="grid gap-2 sm:grid-cols-4">
          <input className="input" placeholder="Username (login id)" value={newUsername} onChange={(e) => setNewUsername(e.target.value)} />
          <input className="input" placeholder="Full name" value={newName} onChange={(e) => setNewName(e.target.value)} />
          <input className="input" placeholder="Emp code (CRM)" value={newEmpCode} onChange={(e) => setNewEmpCode(e.target.value)} />
          <button onClick={onCreate} disabled={busy || !newUsername.trim()} className="btn-primary">
            {busy ? <Loader2 size={14} className="animate-spin" /> : <UserPlus size={14} />} Create
          </button>
        </div>
      </div>

      {/* Existing logins */}
      <div className="card overflow-x-auto">
        <table className="w-full min-w-[760px] text-sm">
          <thead className="bg-subtle text-left text-[11px] uppercase tracking-wider text-brand-muted">
            <tr>
              <th className="px-3 py-2">Username</th>
              <th className="px-3 py-2">Name</th>
              <th className="px-3 py-2">Email</th>
              <th className="px-3 py-2">Emp code</th>
              <th className="px-3 py-2">Status</th>
              <th className="px-3 py-2">Last login</th>
              <th className="px-3 py-2 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={7} className="px-3 py-6 text-center text-brand-muted">
                  <Loader2 size={16} className="mx-auto animate-spin" />
                </td>
              </tr>
            ) : list.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-3 py-6 text-center text-brand-muted">
                  No employee logins yet — import the sheet above.
                </td>
              </tr>
            ) : (
              list.map((u) => (
                <tr key={u.id} className="border-t border-brand-border">
                  <td className="px-3 py-2 font-medium text-brand-dark">{u.username}</td>
                  <td className="px-3 py-2">{u.full_name || "—"}</td>
                  <td className="px-3 py-2 text-xs">
                    {u.email?.endsWith("@employee.local") ? (
                      <span className="text-brand-muted italic">no email set</span>
                    ) : (
                      u.email || "—"
                    )}
                  </td>
                  <td className="px-3 py-2 font-mono text-xs">{u.emp_code || "—"}</td>
                  <td className="px-3 py-2">
                    <span
                      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                        u.is_active ? "bg-emerald-50 text-emerald-700" : "bg-subtle text-brand-muted"
                      }`}
                    >
                      {u.is_active ? "Active" : "Inactive"}
                    </span>
                    {u.must_change_password && (
                      <span className="ml-1 inline-flex rounded-full bg-amber-50 px-2 py-0.5 text-[10px] font-semibold text-amber-700">
                        Must change
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-xs text-brand-muted">{fmtDate(u.last_login_at)}</td>
                  <td className="px-3 py-2">
                    <div className="flex items-center justify-end gap-1">
                      <button onClick={() => openEdit(u)} disabled={busy} title="Edit email / name" className="rounded p-1.5 text-brand-muted hover:bg-subtle hover:text-brand-dark">
                        <Pencil size={15} />
                      </button>
                      <button onClick={() => onReset(u)} disabled={busy} title="Reset password" className="rounded p-1.5 text-brand-muted hover:bg-subtle hover:text-brand-dark">
                        <KeyRound size={15} />
                      </button>
                      <button onClick={() => onToggleActive(u)} disabled={busy} title={u.is_active ? "Deactivate" : "Activate"} className="rounded p-1.5 text-brand-muted hover:bg-subtle hover:text-brand-dark">
                        <Power size={15} />
                      </button>
                      <button onClick={() => onDelete(u)} disabled={busy} title="Delete" className="rounded p-1.5 text-brand-muted hover:bg-red-50 hover:text-signal-red">
                        <Trash2 size={15} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <div className="flex items-center gap-2 text-[11px] text-brand-muted">
        <ShieldCheck size={13} /> Employees log in at the same sign-in page using their username and the temporary password, then set their own password.
      </div>

      {/* Edit employee modal */}
      {editUser && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/50 p-4" onClick={() => setEditUser(null)}>
          <div className="w-full max-w-md rounded-xl bg-card shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between border-b border-brand-border px-5 py-3">
              <div className="text-sm font-semibold text-brand-dark">
                Edit {editUser.username}
              </div>
              <button onClick={() => setEditUser(null)} className="rounded p-1 text-brand-muted hover:bg-subtle">
                <X size={16} />
              </button>
            </div>
            <div className="space-y-3 p-5">
              <div>
                <label className="mb-1 block text-[11px] font-medium uppercase tracking-wide text-brand-muted">Email</label>
                <input
                  type="email"
                  className="input w-full"
                  placeholder="name@company.com"
                  value={editEmail}
                  onChange={(e) => setEditEmail(e.target.value)}
                />
                <p className="mt-1 text-[10px] text-brand-muted">
                  Leave blank to keep the current placeholder. Employees still sign in with their username.
                </p>
              </div>
              <div>
                <label className="mb-1 block text-[11px] font-medium uppercase tracking-wide text-brand-muted">Full name</label>
                <input
                  type="text"
                  className="input w-full"
                  placeholder="Full name"
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                />
              </div>
            </div>
            <div className="flex justify-end gap-2 border-t border-brand-border px-5 py-3">
              <button onClick={() => setEditUser(null)} className="btn-ghost text-xs">Cancel</button>
              <button onClick={onSaveEdit} disabled={busy} className="btn-primary text-xs">
                {busy ? <Loader2 size={14} className="animate-spin" /> : null} Save
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

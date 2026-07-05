"use client";

import { useCallback, useEffect, useState } from "react";
import { AtSign, Loader2, Pencil, Send, Trash2, X } from "lucide-react";

import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { MailIdentityUser } from "@/lib/types";
import PageHeader from "@/components/layout/PageHeader";

const field = "border border-brand-border rounded px-2 py-1 text-sm w-full";

type EditState = {
  enabled: boolean;
  smtp_host: string;
  smtp_port: number;
  smtp_user: string;
  from_email: string;
  use_ssl: boolean;
  password: string;
};

function statusBadge(u: MailIdentityUser) {
  if (!u.identity) return { label: "Not set", cls: "text-brand-muted bg-subtle" };
  if (!u.identity.enabled) return { label: "Disabled", cls: "text-amber-700 bg-amber-50" };
  return { label: "Configured", cls: "text-green-700 bg-green-50" };
}

export default function SendingIdentitiesPage() {
  const { hasRole } = useAuth();
  const isAdmin = hasRole("admin");

  const [rows, setRows] = useState<MailIdentityUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [editing, setEditing] = useState<MailIdentityUser | null>(null);
  const [form, setForm] = useState<EditState | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await api.listMailIdentities();
      setRows(resp.users || []);
    } catch (e) {
      setNote((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isAdmin) void load();
    else setLoading(false);
  }, [isAdmin, load]);

  function openEditor(u: MailIdentityUser) {
    setEditing(u);
    setForm({
      enabled: u.identity?.enabled ?? true,
      smtp_host: u.identity?.smtp_host ?? "",
      smtp_port: u.identity?.smtp_port ?? 587,
      smtp_user: u.identity?.smtp_user ?? u.email,
      from_email: u.identity?.from_email ?? u.email,
      use_ssl: u.identity?.use_ssl ?? false,
      password: "",
    });
    setNote(null);
  }

  async function run(key: string, fn: () => Promise<void>) {
    setBusy(key);
    setNote(null);
    try {
      await fn();
    } catch (e) {
      setNote((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  const save = () => {
    if (!editing || !form) return;
    return run("save", async () => {
      await api.putMailIdentity(editing.user_id, { ...form, password: form.password || undefined });
      setEditing(null);
      setForm(null);
      await load();
      setNote("Sending identity saved.");
    });
  };

  const remove = (u: MailIdentityUser) =>
    run(`del-${u.user_id}`, async () => {
      await api.deleteMailIdentity(u.user_id);
      await load();
      setNote(`Removed personal mailbox for ${u.email}.`);
    });

  const test = (u: MailIdentityUser) =>
    run(`test-${u.user_id}`, async () => {
      const r = await api.testMailIdentity(u.user_id);
      setNote(r.ok ? `${u.email}: connection OK` : `${u.email}: ${r.error || r.reason || "failed"}`);
    });

  if (!isAdmin) {
    return (
      <div className="page-stack">
        <PageHeader title="Sending Identities" description="Per-user “send as” SMTP credentials." icon={AtSign} />
        <div className="card p-4 text-sm text-brand-muted">This page is available to administrators only.</div>
      </div>
    );
  }

  return (
    <div className="page-stack">
      <PageHeader
        title="Sending Identities"
        description="Map a user's own SMTP mailbox so their outgoing mail is sent as them. Credentials are stored encrypted and used automatically once mapped; sends fall back to the main mailbox if a personal send fails."
        icon={AtSign}
      />

      {note && <div className="card p-3 text-xs text-brand-muted">{note}</div>}

      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-subtle text-xs text-brand-muted">
            <tr>
              <th className="text-left font-medium px-4 py-2">User</th>
              <th className="text-left font-medium px-4 py-2">Role</th>
              <th className="text-left font-medium px-4 py-2">Personal mailbox</th>
              <th className="text-left font-medium px-4 py-2">From address</th>
              <th className="text-right font-medium px-4 py-2">Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr><td colSpan={5} className="px-4 py-6 text-center text-brand-muted">
                <Loader2 className="inline animate-spin" size={16} /> Loading…
              </td></tr>
            )}
            {!loading && rows.length === 0 && (
              <tr><td colSpan={5} className="px-4 py-6 text-center text-brand-muted">No users.</td></tr>
            )}
            {rows.map((u) => {
              const badge = statusBadge(u);
              return (
                <tr key={u.user_id} className="border-t border-brand-border/60">
                  <td className="px-4 py-2">
                    <div className="font-medium">{u.full_name || u.username || u.email}</div>
                    <div className="text-xs text-brand-muted">{u.email}{u.emp_code ? ` · ${u.emp_code}` : ""}</div>
                  </td>
                  <td className="px-4 py-2 text-xs">{u.role}</td>
                  <td className="px-4 py-2">
                    <span className={`px-2 py-0.5 rounded text-xs ${badge.cls}`}>{badge.label}</span>
                    {u.identity?.password_set && (
                      <span className="ml-2 text-xs text-brand-muted">pwd {u.identity.password_masked}</span>
                    )}
                  </td>
                  <td className="px-4 py-2 text-xs">{u.identity?.from_email || "—"}</td>
                  <td className="px-4 py-2">
                    <div className="flex items-center justify-end gap-1">
                      <button type="button" onClick={() => openEditor(u)} className="btn-outline text-xs inline-flex items-center gap-1">
                        <Pencil size={13} /> Edit
                      </button>
                      {u.identity && (
                        <button type="button" disabled={busy === `test-${u.user_id}`} onClick={() => test(u)}
                          className="btn-outline text-xs inline-flex items-center gap-1">
                          <Send size={13} /> Test
                        </button>
                      )}
                      {u.identity && (
                        <button type="button" disabled={busy === `del-${u.user_id}`} onClick={() => remove(u)}
                          className="btn-outline text-xs inline-flex items-center gap-1 text-red-600">
                          <Trash2 size={13} /> Remove
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Editor */}
      {editing && form && (
        <div className="card p-5 space-y-3">
          <div className="flex items-center justify-between">
            <div className="font-semibold text-sm">
              Personal mailbox — {editing.full_name || editing.email}
            </div>
            <button type="button" onClick={() => { setEditing(null); setForm(null); }} className="btn-outline text-xs inline-flex items-center gap-1">
              <X size={13} /> Close
            </button>
          </div>

          <div className="flex flex-wrap items-center gap-4">
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={form.enabled} onChange={(e) => setForm((f) => f && { ...f, enabled: e.target.checked })} />
              <span>Enabled (send this user’s mail as them)</span>
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={form.use_ssl} onChange={(e) => setForm((f) => f && { ...f, use_ssl: e.target.checked })} />
              <span>Use SSL (port 465)</span>
            </label>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <label className="text-sm flex flex-col gap-1 sm:col-span-2">
              <span className="text-xs text-brand-muted">SMTP host</span>
              <input className={field} value={form.smtp_host}
                onChange={(e) => setForm((f) => f && { ...f, smtp_host: e.target.value })} placeholder="smtp.gmail.com" />
            </label>
            <label className="text-sm flex flex-col gap-1">
              <span className="text-xs text-brand-muted">Port</span>
              <input type="number" className={field} value={form.smtp_port}
                onChange={(e) => setForm((f) => f && { ...f, smtp_port: Number(e.target.value) })} />
            </label>
            <label className="text-sm flex flex-col gap-1">
              <span className="text-xs text-brand-muted">From address</span>
              <input className={field} value={form.from_email}
                onChange={(e) => setForm((f) => f && { ...f, from_email: e.target.value })} placeholder={editing.email} />
            </label>
            <label className="text-sm flex flex-col gap-1">
              <span className="text-xs text-brand-muted">SMTP username</span>
              <input className={field} value={form.smtp_user}
                onChange={(e) => setForm((f) => f && { ...f, smtp_user: e.target.value })} />
            </label>
            <label className="text-sm flex flex-col gap-1">
              <span className="text-xs text-brand-muted">Password</span>
              <input type="password" className={field} value={form.password}
                onChange={(e) => setForm((f) => f && { ...f, password: e.target.value })}
                placeholder={editing.identity?.password_set ? "•••••••• (leave blank to keep)" : "App password / SMTP password"} />
            </label>
          </div>

          <button type="button" disabled={busy === "save"} onClick={save} className="btn-dark">
            {busy === "save" ? "Saving…" : "Save identity"}
          </button>
        </div>
      )}
    </div>
  );
}

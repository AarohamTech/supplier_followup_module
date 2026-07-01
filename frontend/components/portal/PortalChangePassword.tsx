"use client";

import { useState } from "react";

import { Logo, ZanvarMark } from "@/components/brand/Logo";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

/**
 * Forced first-login (or post-reset) password change for supplier accounts.
 * Rendered by AppShell whenever `user.must_change_password` is true; on success
 * we refresh the session so the flag clears and the portal opens.
 */
export default function PortalChangePassword() {
  const { user, refresh, logout } = useAuth();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (next.length < 8) {
      setError("New password must be at least 8 characters.");
      return;
    }
    if (next !== confirm) {
      setError("New password and confirmation do not match.");
      return;
    }
    setBusy(true);
    try {
      await api.changePassword(current, next);
      await refresh();
    } catch (err) {
      setError((err as Error).message || "Could not change password.");
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-brand-surface px-4">
      <div className="w-full max-w-sm rounded-lg border border-brand-border bg-card p-8 shadow-card">
        <div className="mb-6 text-center">
          <div className="mx-auto mb-3 flex items-center justify-center gap-3">
            <ZanvarMark size={48} />
            <span className="flex h-16 w-16 items-center justify-center rounded-2xl bg-red-50 text-signal-red">
              <Logo size={40} />
            </span>
          </div>
          <h1 className="text-lg font-bold text-signal-red">Set a new password</h1>
          <p className="mt-1 text-xs text-brand-muted">
            Welcome{user?.supplier_name ? `, ${user.supplier_name}` : ""}. For your security,
            choose a new password before continuing.
          </p>
        </div>

        <form onSubmit={onSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block text-xs font-medium text-brand-dark">Temporary password</label>
            <input
              type="password"
              required
              autoFocus
              value={current}
              onChange={(e) => setCurrent(e.target.value)}
              className="input"
              placeholder="The password we emailed you"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-brand-dark">New password</label>
            <input
              type="password"
              required
              value={next}
              onChange={(e) => setNext(e.target.value)}
              className="input"
              placeholder="At least 8 characters"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-brand-dark">Confirm new password</label>
            <input
              type="password"
              required
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              className="input"
              placeholder="Re-enter new password"
            />
          </div>

          {error && (
            <div className="rounded-md bg-red-50 px-3 py-2 text-xs text-signal-red">{error}</div>
          )}

          <button type="submit" disabled={busy} className="btn-primary w-full">
            {busy ? "Saving..." : "Set password & continue"}
          </button>
          <button type="button" onClick={logout} className="btn-ghost w-full">
            Sign out
          </button>
        </form>
      </div>
    </div>
  );
}

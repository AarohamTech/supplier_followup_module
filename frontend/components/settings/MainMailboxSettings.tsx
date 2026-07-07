"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { MailConfig } from "@/lib/types";

type Probe = { ok?: boolean; error?: string; reason?: string; authenticated?: boolean; mailbox_count?: number };

const field = "border border-brand-border rounded px-2 py-1 text-sm w-full";

/**
 * First section of Settings: edit the MAIN mailbox (SMTP + IMAP) for the current
 * company. Admin-only edit; everyone else sees a read-only view. Credentials are
 * saved to the backend (encrypted at rest) and take effect at runtime.
 */
export default function MainMailboxSettings() {
  const { hasRole } = useAuth();
  const isAdmin = hasRole("admin");

  const [cfg, setCfg] = useState<MailConfig | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [smtpTest, setSmtpTest] = useState<Probe | null>(null);
  const [imapTest, setImapTest] = useState<Probe | null>(null);

  const [smtp, setSmtp] = useState({ enabled: false, host: "", port: 587, user: "", from: "", password: "" });
  const [imap, setImap] = useState({
    enabled: false, protocol: "IMAP", use_ssl: false, host: "", port: 993, user: "", folder: "INBOX", password: "",
  });

  async function load() {
    const c = await api.getMailConfig();
    setCfg(c);
    setSmtp({ enabled: c.smtp.enabled, host: c.smtp.host, port: c.smtp.port || 587, user: c.smtp.user, from: c.smtp.from, password: "" });
    setImap({
      enabled: c.imap.enabled, protocol: c.imap.protocol || "IMAP", use_ssl: c.imap.use_ssl,
      host: c.imap.host, port: c.imap.port || 993, user: c.imap.user, folder: c.imap.folder || "INBOX", password: "",
    });
  }

  useEffect(() => {
    void load().catch((e) => setNote((e as Error).message));
  }, []);

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

  const saveSmtp = () =>
    run("save-smtp", async () => {
      await api.putSmtpConfig({ ...smtp, password: smtp.password || undefined });
      await load();
      setNote("SMTP credentials saved.");
    });

  const saveImap = () =>
    run("save-imap", async () => {
      await api.putImapConfig({ ...imap, password: imap.password || undefined });
      await load();
      setNote("Inbox credentials saved.");
    });

  const testSmtp = () =>
    run("test-smtp", async () => setSmtpTest((await api.testSmtp()) as Probe));
  const testImap = () =>
    run("test-imap", async () => setImapTest((await api.testImap()) as Probe));

  const passwordPlaceholder = (isSet: boolean) => (isSet ? "•••••••• (leave blank to keep)" : "Not set");

  return (
    <section className="space-y-3">
      <div>
        <h2 className="font-semibold text-base">Main Mailbox Credentials</h2>
        <p className="text-xs text-brand-muted">
          The system mailbox used to send and receive mail for this company.{" "}
          {isAdmin ? "Editable by admins; changes take effect immediately (no restart)." : "Only an admin can change these."}
        </p>
      </div>

      {note && <div className="card p-2 text-xs text-brand-muted">{note}</div>}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* ── SMTP (outbound) ── */}
        <div className="card p-5 space-y-3">
          <div className="flex items-center justify-between">
            <div className="font-semibold text-sm">SMTP (Outbound)</div>
            <button type="button" disabled={busy === "test-smtp"} onClick={testSmtp} className="btn-outline text-xs">
              {busy === "test-smtp" ? "Testing…" : "Test Connection"}
            </button>
          </div>

          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={smtp.enabled} disabled={!isAdmin}
              onChange={(e) => setSmtp((s) => ({ ...s, enabled: e.target.checked }))} />
            <span>Enabled</span>
          </label>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <label className="text-sm flex flex-col gap-1 sm:col-span-2">
              <span className="text-xs text-brand-muted">Host</span>
              <input className={field} disabled={!isAdmin} value={smtp.host}
                onChange={(e) => setSmtp((s) => ({ ...s, host: e.target.value }))} placeholder="smtp.example.com" />
            </label>
            <label className="text-sm flex flex-col gap-1">
              <span className="text-xs text-brand-muted">Port</span>
              <input type="number" className={field} disabled={!isAdmin} value={smtp.port}
                onChange={(e) => setSmtp((s) => ({ ...s, port: Number(e.target.value) }))} />
            </label>
            <label className="text-sm flex flex-col gap-1">
              <span className="text-xs text-brand-muted">From address</span>
              <input className={field} disabled={!isAdmin} value={smtp.from}
                onChange={(e) => setSmtp((s) => ({ ...s, from: e.target.value }))} placeholder="stores@example.com" />
            </label>
            <label className="text-sm flex flex-col gap-1">
              <span className="text-xs text-brand-muted">Username</span>
              <input className={field} disabled={!isAdmin} value={smtp.user}
                onChange={(e) => setSmtp((s) => ({ ...s, user: e.target.value }))} />
            </label>
            <label className="text-sm flex flex-col gap-1">
              <span className="text-xs text-brand-muted">Password</span>
              <input type="password" className={field} disabled={!isAdmin} value={smtp.password}
                onChange={(e) => setSmtp((s) => ({ ...s, password: e.target.value }))}
                placeholder={passwordPlaceholder(!!cfg?.smtp.password_set)} />
            </label>
          </div>

          {smtpTest && (
            <div className={`text-xs px-2 py-1 rounded ${smtpTest.ok ? "text-green-700 bg-green-50" : "text-red-700 bg-red-50"}`}>
              {smtpTest.ok
                ? `Connection OK${smtpTest.authenticated ? " · authenticated" : ""}`
                : `Failed: ${smtpTest.error || smtpTest.reason || "unknown"}`}
            </div>
          )}
          {isAdmin && (
            <button type="button" disabled={busy === "save-smtp"} onClick={saveSmtp} className="btn-dark">
              {busy === "save-smtp" ? "Saving…" : "Save SMTP"}
            </button>
          )}
        </div>

        {/* ── Inbox (IMAP/POP3) ── */}
        <div className="card p-5 space-y-3">
          <div className="flex items-center justify-between">
            <div className="font-semibold text-sm">Inbox ({imap.protocol})</div>
            <button type="button" disabled={busy === "test-imap"} onClick={testImap} className="btn-outline text-xs">
              {busy === "test-imap" ? "Testing…" : "Test Connection"}
            </button>
          </div>

          <div className="flex flex-wrap items-center gap-4">
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={imap.enabled} disabled={!isAdmin}
                onChange={(e) => setImap((s) => ({ ...s, enabled: e.target.checked }))} />
              <span>Enabled</span>
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={imap.use_ssl} disabled={!isAdmin}
                onChange={(e) => setImap((s) => ({ ...s, use_ssl: e.target.checked }))} />
              <span>Use SSL</span>
            </label>
            <label className="flex items-center gap-2 text-sm">
              <span className="text-xs text-brand-muted">Protocol</span>
              <select className={field + " w-auto"} disabled={!isAdmin} value={imap.protocol}
                onChange={(e) => setImap((s) => ({ ...s, protocol: e.target.value }))}>
                <option value="IMAP">IMAP</option>
                <option value="POP3">POP3</option>
              </select>
            </label>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <label className="text-sm flex flex-col gap-1 sm:col-span-2">
              <span className="text-xs text-brand-muted">Host</span>
              <input className={field} disabled={!isAdmin} value={imap.host}
                onChange={(e) => setImap((s) => ({ ...s, host: e.target.value }))} placeholder="imap.example.com" />
            </label>
            <label className="text-sm flex flex-col gap-1">
              <span className="text-xs text-brand-muted">Port</span>
              <input type="number" className={field} disabled={!isAdmin} value={imap.port}
                onChange={(e) => setImap((s) => ({ ...s, port: Number(e.target.value) }))} />
            </label>
            <label className="text-sm flex flex-col gap-1">
              <span className="text-xs text-brand-muted">Folder</span>
              <input className={field} disabled={!isAdmin} value={imap.folder}
                onChange={(e) => setImap((s) => ({ ...s, folder: e.target.value }))} placeholder="INBOX" />
            </label>
            <label className="text-sm flex flex-col gap-1">
              <span className="text-xs text-brand-muted">Username</span>
              <input className={field} disabled={!isAdmin} value={imap.user}
                onChange={(e) => setImap((s) => ({ ...s, user: e.target.value }))} />
            </label>
            <label className="text-sm flex flex-col gap-1">
              <span className="text-xs text-brand-muted">Password</span>
              <input type="password" className={field} disabled={!isAdmin} value={imap.password}
                onChange={(e) => setImap((s) => ({ ...s, password: e.target.value }))}
                placeholder={passwordPlaceholder(!!cfg?.imap.password_set)} />
            </label>
          </div>

          {imapTest && (
            <div className={`text-xs px-2 py-1 rounded ${imapTest.ok ? "text-green-700 bg-green-50" : "text-red-700 bg-red-50"}`}>
              {imapTest.ok
                ? `Connection OK${imapTest.mailbox_count !== undefined ? ` · mailbox=${imapTest.mailbox_count}` : ""}`
                : `Failed: ${imapTest.error || imapTest.reason || "unknown"}`}
            </div>
          )}
          {isAdmin && (
            <button type="button" disabled={busy === "save-imap"} onClick={saveImap} className="btn-dark">
              {busy === "save-imap" ? "Saving…" : "Save Inbox"}
            </button>
          )}
        </div>
      </div>
    </section>
  );
}

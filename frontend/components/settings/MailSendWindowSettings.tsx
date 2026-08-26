"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { MailSendWindow } from "@/lib/types";

const field = "border border-brand-border rounded px-2 py-1 text-sm w-full";

const HOURS = Array.from({ length: 24 }, (_, h) => h);

function hourLabel(h: number) {
  return `${String(h).padStart(2, "0")}:00`;
}

/**
 * Auto follow-up send window. Auto follow-ups (PO_FOLLOWUP_*) are held during
 * office hours and drained overnight at a capped rate; staff-composed mail is
 * never held. Manager+ can edit.
 */
export default function MailSendWindowSettings() {
  const { hasRole } = useAuth();
  const canEdit = hasRole("manager"); // roleAtLeast — admin passes too

  const [cfg, setCfg] = useState<MailSendWindow | null>(null);
  const [form, setForm] = useState({
    enabled: true,
    start_hour: 19,
    end_hour: 8,
    per_minute_limit: 25,
    send_interval_minutes: 1,
  });
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  async function load() {
    const { mail_window } = await api.getMailWindow();
    setCfg(mail_window);
    setForm({
      enabled: mail_window.enabled,
      start_hour: mail_window.start_hour,
      end_hour: mail_window.end_hour,
      per_minute_limit: mail_window.per_minute_limit,
      send_interval_minutes: mail_window.send_interval_minutes || 1,
    });
  }

  useEffect(() => {
    void load().catch((e) => setNote((e as Error).message));
  }, []);

  async function save() {
    setBusy(true);
    setNote(null);
    try {
      const { mail_window } = await api.updateMailWindow(form);
      setCfg(mail_window);
      setNote("Saved.");
    } catch (e) {
      setNote((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const cadenceMismatch = form.send_interval_minutes !== 1;

  return (
    <div className="card p-5 space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="font-semibold text-sm">Auto Follow-up Send Window</div>
          <p className="text-xs text-brand-muted">
            Auto follow-ups wait for this window. Staff-composed mail and “Send now” are never held.
          </p>
        </div>
        {cfg && (
          <span
            className={
              cfg.enabled && !cfg.window_open
                ? "text-xs px-2 py-1 rounded bg-amber-50 text-amber-700"
                : "text-xs px-2 py-1 rounded bg-green-50 text-green-700"
            }
          >
            {!cfg.enabled
              ? "Always open"
              : cfg.window_open
                ? `Open — closes ${cfg.next_change_local} ${cfg.timezone}`
                : `Holding — opens ${cfg.next_change_local} ${cfg.timezone}`}
          </span>
        )}
      </div>

      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={form.enabled}
          disabled={!canEdit}
          onChange={(e) => setForm({ ...form, enabled: e.target.checked })}
        />
        Hold auto follow-ups during office hours
      </label>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <label className="mb-1 block text-xs font-medium text-brand-dark">Window opens</label>
          <select
            className={field}
            value={form.start_hour}
            disabled={!canEdit || !form.enabled}
            onChange={(e) => setForm({ ...form, start_hour: Number(e.target.value) })}
          >
            {HOURS.map((h) => (
              <option key={h} value={h}>{hourLabel(h)}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-brand-dark">Window closes</label>
          <select
            className={field}
            value={form.end_hour}
            disabled={!canEdit || !form.enabled}
            onChange={(e) => setForm({ ...form, end_hour: Number(e.target.value) })}
          >
            {HOURS.map((h) => (
              <option key={h} value={h}>{hourLabel(h)}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-brand-dark">Mails per run</label>
          <input
            type="number"
            min={1}
            max={200}
            className={field}
            value={form.per_minute_limit}
            disabled={!canEdit}
            onChange={(e) => setForm({ ...form, per_minute_limit: Number(e.target.value) })}
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-brand-dark">Send every (min)</label>
          <input
            type="number"
            min={1}
            max={60}
            className={field}
            value={form.send_interval_minutes}
            disabled={!canEdit}
            onChange={(e) => setForm({ ...form, send_interval_minutes: Number(e.target.value) })}
          />
        </div>
      </div>

      <p className="text-xs text-brand-muted">
        {cadenceMismatch ? (
          <>
            <span className="text-amber-700">
              Sending every {form.send_interval_minutes} min means about{" "}
              {(form.per_minute_limit / form.send_interval_minutes).toFixed(1)} mails/minute
            </span>
            , not {form.per_minute_limit}. Set the interval to 1 for a true per-minute cap.
          </>
        ) : (
          <>
            Up to {form.per_minute_limit} mails per minute, counting auto follow-ups and staff mail
            together — keep this under your SMTP provider’s ceiling.
          </>
        )}
      </p>

      {cfg?.enabled && form.start_hour === form.end_hour && (
        <p className="text-xs text-amber-700">
          Opening and closing hours match, so nothing is ever held.
        </p>
      )}

      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={save}
          disabled={!canEdit || busy}
          className="text-xs px-3 py-1.5 rounded bg-ink text-white disabled:opacity-50"
        >
          {busy ? "Saving…" : "Save Window"}
        </button>
        {!canEdit && <span className="text-xs text-brand-muted">Manager access required to edit.</span>}
        {note && <span className="text-xs text-brand-muted">{note}</span>}
      </div>
    </div>
  );
}

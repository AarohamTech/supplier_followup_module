"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import type {
  CronJobLog,
  CronJobRow,
  DraftRule,
  MailEngineHealth,
  MailEngineSnapshot,
} from "@/lib/types";
import { signalClass } from "@/lib/format";

type TestResult = {
  ok?: boolean;
  enabled?: boolean;
  host?: string;
  port?: number;
  authenticated?: boolean;
  folder?: string;
  protocol?: string;
  mailbox_count?: number;
  reason?: string;
  error?: string;
};

const SCHEDULER_FIELDS: { key: string; label: string }[] = [
  { key: "MAIL_FETCH_INTERVAL_MINUTES", label: "Mail Fetch (min)" },
  { key: "STATUS_CHANGE_INTERVAL_MINUTES", label: "Status Change Scan (min)" },
  { key: "AUTO_REPLY_INTERVAL_MINUTES", label: "Auto Reply Drafts (min)" },
  { key: "MAIL_SEND_INTERVAL_MINUTES", label: "Mail Send (min)" },
];

const FOLLOWUP_STATUSES = [
  "PENDING_ACK",
  "REMINDER_DUE",
  "URGENT_FOLLOWUP",
  "STRONG_FOLLOWUP",
  "AI_FOLLOWUP",
  "CRITICAL_ESCALATION",
  "PENDING",
];

function statusBadge(status: string | null | undefined) {
  if (!status) return "text-brand-muted bg-gray-100";
  const upper = status.toUpperCase();
  if (upper === "OK") return "text-green-700 bg-green-50";
  if (upper === "ERROR") return "text-red-700 bg-red-50";
  if (upper === "DISABLED") return "text-amber-700 bg-amber-50";
  return "text-brand-muted bg-gray-100";
}

function formatDateTime(value: string | null | undefined) {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

export default function SettingsPage() {
  const [snapshot, setSnapshot] = useState<MailEngineSnapshot | null>(null);
  const [health, setHealth] = useState<MailEngineHealth | null>(null);
  const [cronJobs, setCronJobs] = useState<CronJobRow[]>([]);
  const [cronLogs, setCronLogs] = useState<CronJobLog[]>([]);
  const [draftRules, setDraftRules] = useState<DraftRule[]>([]);
  const [scheduler, setScheduler] = useState<Record<string, number>>({});
  const [followup, setFollowup] = useState<Record<string, number>>({});
  const [message, setMessage] = useState<string | null>(null);
  const [smtpTest, setSmtpTest] = useState<TestResult | null>(null);
  const [imapTest, setImapTest] = useState<TestResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [busyKey, setBusyKey] = useState<string | null>(null);

  const refreshAll = useCallback(async () => {
    setLoading(true);
    try {
      const [snap, jobsResp, sch, logs, healthSnap, draftResp] = await Promise.all([
        api.getMailEngineSnapshot(),
        api.listCronJobs(),
        api.getSchedulerSettings(),
        api.getCronJobLogs({ limit: 20 }),
        api.getEngineHealth().catch(() => null),
        api.listDraftRules(),
      ]);
      setSnapshot(snap);
      setCronJobs(jobsResp.jobs || []);
      setScheduler(sch.scheduler_intervals_minutes || {});
      setFollowup(sch.followup_intervals_hours || {});
      setCronLogs(logs.logs || []);
      setHealth(healthSnap);
      setDraftRules(draftResp.rules || []);
    } catch (err) {
      setMessage((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshAll();
  }, [refreshAll]);

  async function runWithBusy(key: string, action: () => Promise<void>) {
    setBusyKey(key);
    setMessage(null);
    try {
      await action();
    } catch (err) {
      setMessage((err as Error).message);
    } finally {
      setBusyKey(null);
    }
  }

  async function handleTestSmtp() {
    await runWithBusy("test-smtp", async () => {
      const result = await api.testSmtp();
      setSmtpTest(result as TestResult);
      if ((result as TestResult).ok) setMessage("SMTP connection successful.");
      else setMessage(`SMTP test failed: ${(result as TestResult).error || (result as TestResult).reason || "unknown"}`);
    });
  }

  async function handleTestImap() {
    await runWithBusy("test-imap", async () => {
      const result = await api.testImap();
      setImapTest(result as TestResult);
      if ((result as TestResult).ok) setMessage("Inbox connection successful.");
      else setMessage(`Inbox test failed: ${(result as TestResult).error || (result as TestResult).reason || "unknown"}`);
    });
  }

  async function handleSaveScheduler() {
    await runWithBusy("save-scheduler", async () => {
      const values: Record<string, number> = {};
      SCHEDULER_FIELDS.forEach(({ key }) => {
        const v = Number(scheduler[key]);
        if (Number.isFinite(v) && v >= 1) values[key] = v;
      });
      const res = await api.updateSchedulerIntervals(values);
      setScheduler(res.scheduler_intervals_minutes);
      await refreshAll();
      setMessage("Scheduler intervals saved.");
    });
  }

  async function handleSaveFollowup() {
    await runWithBusy("save-followup", async () => {
      const values: Record<string, number> = {};
      FOLLOWUP_STATUSES.forEach((s) => {
        const v = Number(followup[s]);
        if (Number.isFinite(v) && v >= 1) values[s] = v;
      });
      const res = await api.updateFollowupIntervals(values);
      setFollowup(res.followup_intervals_hours);
      setMessage("Follow-up intervals saved.");
    });
  }

  async function handleSaveDraftRule(rule: DraftRule) {
    await runWithBusy(`save-draft-${rule.id}`, async () => {
      const interval = Number(rule.interval_hours);
      const result = await api.updateDraftRule(rule.id, {
        subject_template: rule.subject_template,
        body_template: rule.body_template,
        active: rule.active,
        interval_hours: Number.isFinite(interval) && interval >= 1 ? interval : undefined,
      });
      setDraftRules((rows) => rows.map((row) => (row.id === rule.id ? result.rule : row)));
      if (result.rule.followup_status && result.rule.interval_hours) {
        setFollowup((values) => ({
          ...values,
          [result.rule.followup_status as string]: result.rule.interval_hours as number,
        }));
      }
      setMessage(`${rule.template_name} draft saved.`);
    });
  }

  async function handleToggleJob(job: CronJobRow, enabled: boolean) {
    await runWithBusy(`toggle-${job.job_name}`, async () => {
      await api.updateCronJob(job.job_name, { enabled });
      await refreshAll();
      setMessage(`${job.display_name} ${enabled ? "enabled" : "disabled"}.`);
    });
  }

  async function handleChangeInterval(job: CronJobRow, minutes: number) {
    await runWithBusy(`interval-${job.job_name}`, async () => {
      await api.updateCronJob(job.job_name, { interval_minutes: minutes });
      await refreshAll();
      setMessage(`${job.display_name} interval set to ${minutes} min.`);
    });
  }

  async function handleRunJob(job: CronJobRow) {
    await runWithBusy(`run-${job.job_name}`, async () => {
      const res = await api.runCronJobNow(job.job_name);
      await refreshAll();
      setMessage(
        `${job.display_name} run completed (${res.status}). Processed: ${res.records_processed ?? "-"}`,
      );
    });
  }

  async function handleRunAllJobs() {
    await runWithBusy("run-all-jobs", async () => {
      const res = await api.runAllCronJobs();
      await refreshAll();
      setMessage(`Ran ${res.ran} enabled job(s).`);
    });
  }

  async function handleEngineAction(action: "start" | "stop" | "restart") {
    await runWithBusy(`engine-${action}`, async () => {
      if (action === "start") await api.startEngine();
      else if (action === "stop") await api.stopEngine();
      else await api.restartEngine();
      await refreshAll();
      setMessage(`Engine ${action} request completed.`);
    });
  }

  const smtp = snapshot?.smtp;
  const imap = snapshot?.imap;

  const queueSummary = useMemo(() => {
    if (!health) return null;
    return health.queue;
  }, [health]);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold">Mail Engine Control</h1>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            disabled={loading || busyKey === "engine-start"}
            onClick={() => handleEngineAction("start")}
            className="text-sm px-3 py-1.5 rounded border border-brand-border bg-white text-brand-dark hover:bg-gray-50 disabled:opacity-50"
          >
            Start
          </button>
          <button
            type="button"
            disabled={loading || busyKey === "engine-stop"}
            onClick={() => handleEngineAction("stop")}
            className="text-sm px-3 py-1.5 rounded border border-brand-border bg-white text-brand-dark hover:bg-gray-50 disabled:opacity-50"
          >
            Stop
          </button>
          <button
            type="button"
            disabled={loading || busyKey === "engine-restart"}
            onClick={() => handleEngineAction("restart")}
            className="text-sm px-3 py-1.5 rounded bg-brand-fg text-white disabled:opacity-50"
          >
            Restart Engine
          </button>
        </div>
      </div>

      {message && (
        <div className="card p-3 text-xs text-brand-muted">{message}</div>
      )}

      {/* SMTP + IMAP cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="card p-5 space-y-3">
          <div className="flex items-center justify-between">
            <div>
              <div className="font-semibold text-sm">SMTP (Outbound)</div>
              <div className="text-xs text-brand-muted">
                Credentials are read from <code>.env</code> at startup. Use the test button to verify reachability.
              </div>
            </div>
            <button
              type="button"
              disabled={busyKey === "test-smtp"}
              onClick={handleTestSmtp}
              className="text-sm px-3 py-1.5 rounded bg-brand-fg text-white disabled:opacity-50"
            >
              {busyKey === "test-smtp" ? "Testing…" : "Test Connection"}
            </button>
          </div>
          <dl className="text-xs grid grid-cols-3 gap-2">
            <dt className="text-brand-muted">Enabled</dt>
            <dd className="col-span-2">{smtp?.enabled ? "Yes" : "No"}</dd>
            <dt className="text-brand-muted">Host</dt>
            <dd className="col-span-2">{smtp?.host || "—"}</dd>
            <dt className="text-brand-muted">Port</dt>
            <dd className="col-span-2">{smtp?.port || "—"}</dd>
            <dt className="text-brand-muted">User</dt>
            <dd className="col-span-2">{smtp?.user || "—"}</dd>
            <dt className="text-brand-muted">Password</dt>
            <dd className="col-span-2">{smtp?.password_masked || "—"}</dd>
            <dt className="text-brand-muted">From</dt>
            <dd className="col-span-2">{smtp?.from || "—"}</dd>
          </dl>
          {smtpTest && (
            <div
              className={`text-xs px-2 py-1 rounded ${statusBadge(smtpTest.ok ? "OK" : "ERROR")}`}
            >
              {smtpTest.ok
                ? `Connection OK${smtpTest.authenticated ? " · authenticated" : ""}`
                : `Failed: ${smtpTest.error || smtpTest.reason || "unknown"}`}
            </div>
          )}
        </div>

        <div className="card p-5 space-y-3">
          <div className="flex items-center justify-between">
            <div>
              <div className="font-semibold text-sm">Inbox ({imap?.protocol || "IMAP"})</div>
              <div className="text-xs text-brand-muted">
                Configured via <code>.env</code>. Verify mailbox access before enabling auto-fetch.
              </div>
            </div>
            <button
              type="button"
              disabled={busyKey === "test-imap"}
              onClick={handleTestImap}
              className="text-sm px-3 py-1.5 rounded bg-brand-fg text-white disabled:opacity-50"
            >
              {busyKey === "test-imap" ? "Testing…" : "Test Connection"}
            </button>
          </div>
          <dl className="text-xs grid grid-cols-3 gap-2">
            <dt className="text-brand-muted">Enabled</dt>
            <dd className="col-span-2">{imap?.enabled ? "Yes" : "No"}</dd>
            <dt className="text-brand-muted">Protocol</dt>
            <dd className="col-span-2">{imap?.protocol || "—"}</dd>
            <dt className="text-brand-muted">SSL</dt>
            <dd className="col-span-2">{imap?.use_ssl ? "Yes" : "No"}</dd>
            <dt className="text-brand-muted">Host</dt>
            <dd className="col-span-2">{imap?.host || "—"}</dd>
            <dt className="text-brand-muted">Port</dt>
            <dd className="col-span-2">{imap?.port || "—"}</dd>
            <dt className="text-brand-muted">User</dt>
            <dd className="col-span-2">{imap?.user || "—"}</dd>
            <dt className="text-brand-muted">Folder</dt>
            <dd className="col-span-2">{imap?.folder || "—"}</dd>
          </dl>
          {imapTest && (
            <div
              className={`text-xs px-2 py-1 rounded ${statusBadge(imapTest.ok ? "OK" : "ERROR")}`}
            >
              {imapTest.ok
                ? `Connection OK${imapTest.mailbox_count !== undefined ? ` · mailbox=${imapTest.mailbox_count}` : ""}`
                : `Failed: ${imapTest.error || imapTest.reason || "unknown"}`}
            </div>
          )}
        </div>
      </div>

      {/* Cron jobs */}
      <div className="card p-5 space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <div className="font-semibold text-sm">Cron Job Registry</div>
            <p className="text-xs text-brand-muted">
              Each job tracks last/next run and is paused individually without restarting the engine.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleRunAllJobs}
              disabled={busyKey === "run-all-jobs"}
              className="text-xs px-2 py-1 rounded bg-brand-dark text-white disabled:opacity-50"
            >
              {busyKey === "run-all-jobs" ? "Running…" : "Run All Jobs"}
            </button>
            <button
              type="button"
              onClick={refreshAll}
              disabled={loading}
              className="text-xs px-2 py-1 rounded border border-brand-border bg-white"
            >
              Refresh
            </button>
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="text-brand-muted">
              <tr className="text-left">
                <th className="py-2 pr-3">Job</th>
                <th className="py-2 pr-3">Enabled</th>
                <th className="py-2 pr-3">Interval (min)</th>
                <th className="py-2 pr-3">Last Run</th>
                <th className="py-2 pr-3">Next Run</th>
                <th className="py-2 pr-3">Status</th>
                <th className="py-2 pr-3">Runs / Failures</th>
                <th className="py-2 pr-3">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-brand-border">
              {cronJobs.map((job) => (
                <tr key={job.job_name}>
                  <td className="py-2 pr-3 align-top">
                    <div className="font-medium">{job.display_name}</div>
                    <div className="text-brand-muted">{job.description}</div>
                  </td>
                  <td className="py-2 pr-3 align-top">
                    <label className="inline-flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={job.enabled}
                        disabled={busyKey === `toggle-${job.job_name}`}
                        onChange={(e) => handleToggleJob(job, e.target.checked)}
                      />
                      <span className="text-xs">{job.enabled ? "On" : "Off"}</span>
                    </label>
                  </td>
                  <td className="py-2 pr-3 align-top">
                    <input
                      type="number"
                      min={1}
                      defaultValue={job.interval_minutes}
                      onBlur={(e) => {
                        const v = Number(e.target.value);
                        if (v >= 1 && v !== job.interval_minutes) handleChangeInterval(job, v);
                      }}
                      className="border border-brand-border rounded px-2 py-1 w-20 text-xs"
                    />
                  </td>
                  <td className="py-2 pr-3 align-top whitespace-nowrap">
                    {formatDateTime(job.last_run_at)}
                  </td>
                  <td className="py-2 pr-3 align-top whitespace-nowrap">
                    {formatDateTime(job.next_run_at)}
                  </td>
                  <td className="py-2 pr-3 align-top">
                    <span className={`px-2 py-0.5 rounded text-xs ${statusBadge(job.last_status)}`}>
                      {job.last_status || "—"}
                    </span>
                    {job.last_message ? (
                      <div className="text-brand-muted mt-1 max-w-[260px] truncate" title={job.last_message}>
                        {job.last_message}
                      </div>
                    ) : null}
                  </td>
                  <td className="py-2 pr-3 align-top">
                    {job.total_runs} / <span className="text-signal-red">{job.failed_runs}</span>
                  </td>
                  <td className="py-2 pr-3 align-top">
                    <button
                      type="button"
                      onClick={() => handleRunJob(job)}
                      disabled={busyKey === `run-${job.job_name}`}
                      className="text-xs px-2 py-1 rounded bg-brand-fg text-white disabled:opacity-50"
                    >
                      {busyKey === `run-${job.job_name}` ? "Running…" : "Run Now"}
                    </button>
                  </td>
                </tr>
              ))}
              {cronJobs.length === 0 && (
                <tr>
                  <td className="py-3 text-brand-muted" colSpan={8}>
                    No cron jobs registered yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Draft templates + signal intervals */}
      <div className="card p-5 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <div className="font-semibold text-sm">Signal Draft Settings</div>
            <p className="text-xs text-brand-muted">
              Edit the draft subject/body used for each signal and the time interval before the next follow-up.
            </p>
          </div>
          <button
            type="button"
            onClick={refreshAll}
            disabled={loading}
            className="text-xs px-2 py-1 rounded border border-brand-border bg-white"
          >
            Refresh
          </button>
        </div>
        <div className="space-y-4">
          {draftRules.map((rule) => {
            const signal = String(rule.signal || "GREEN").toUpperCase();
            const intervalLabel = rule.followup_status || "No interval rule";
            return (
              <div key={rule.id} className="rounded border border-brand-border p-4 space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className={`px-2 py-0.5 rounded-full text-xs ring-1 ${signalClass[signal] || "bg-gray-100 text-brand-dark ring-gray-200"}`}>
                      {signal}
                    </span>
                    <span className="text-sm font-medium">{rule.template_name}</span>
                    {rule.day_no ? (
                      <span className="text-xs text-brand-muted">Day {rule.day_no}</span>
                    ) : null}
                  </div>
                  <div className="flex flex-wrap items-center gap-3">
                    <label className="inline-flex items-center gap-2 text-xs text-brand-muted">
                      <input
                        type="checkbox"
                        checked={rule.active}
                        onChange={(e) =>
                          setDraftRules((rows) =>
                            rows.map((row) =>
                              row.id === rule.id ? { ...row, active: e.target.checked } : row,
                            ),
                          )
                        }
                      />
                      Active
                    </label>
                    <label className="flex items-center gap-2 text-xs text-brand-muted">
                      <span>{intervalLabel}</span>
                      <input
                        type="number"
                        min={1}
                        value={rule.interval_hours ?? ""}
                        onChange={(e) =>
                          setDraftRules((rows) =>
                            rows.map((row) =>
                              row.id === rule.id
                                ? { ...row, interval_hours: Number(e.target.value) }
                                : row,
                            ),
                          )
                        }
                        className="border border-brand-border rounded px-2 py-1 w-20 text-xs"
                      />
                      <span>hours</span>
                    </label>
                    <button
                      type="button"
                      onClick={() => handleSaveDraftRule(rule)}
                      disabled={busyKey === `save-draft-${rule.id}`}
                      className="text-xs px-3 py-1.5 rounded bg-brand-fg text-white disabled:opacity-50"
                    >
                      {busyKey === `save-draft-${rule.id}` ? "Saving..." : "Save Draft"}
                    </button>
                  </div>
                </div>
                <label className="block text-xs text-brand-muted space-y-1">
                  <span>Subject</span>
                  <input
                    type="text"
                    value={rule.subject_template}
                    onChange={(e) =>
                      setDraftRules((rows) =>
                        rows.map((row) =>
                          row.id === rule.id ? { ...row, subject_template: e.target.value } : row,
                        ),
                      )
                    }
                    className="w-full border border-brand-border rounded px-2 py-1.5 text-sm text-brand-dark"
                  />
                </label>
                <label className="block text-xs text-brand-muted space-y-1">
                  <span>Draft Body</span>
                  <textarea
                    value={rule.body_template}
                    onChange={(e) =>
                      setDraftRules((rows) =>
                        rows.map((row) =>
                          row.id === rule.id ? { ...row, body_template: e.target.value } : row,
                        ),
                      )
                    }
                    rows={6}
                    className="w-full border border-brand-border rounded px-2 py-1.5 text-sm text-brand-dark font-mono"
                  />
                </label>
              </div>
            );
          })}
          {draftRules.length === 0 && (
            <div className="text-xs text-brand-muted">No signal draft templates found.</div>
          )}
        </div>
      </div>

      {/* Scheduler defaults + follow-up intervals (legacy) */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="card p-5 space-y-3">
          <div className="font-semibold text-sm">Default Scheduler Intervals</div>
          <p className="text-xs text-brand-muted">
            Fallback values used when an individual job interval is not set.
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {SCHEDULER_FIELDS.map(({ key, label }) => (
              <label key={key} className="text-sm flex flex-col gap-1">
                <span className="text-xs text-brand-muted">{label}</span>
                <input
                  type="number"
                  min={1}
                  disabled={loading}
                  className="border border-brand-border rounded px-2 py-1 text-sm"
                  value={scheduler[key] ?? ""}
                  onChange={(e) =>
                    setScheduler((s) => ({ ...s, [key]: Number(e.target.value) }))
                  }
                />
              </label>
            ))}
          </div>
          <button
            type="button"
            disabled={loading || busyKey === "save-scheduler"}
            onClick={handleSaveScheduler}
            className="text-sm px-3 py-1.5 rounded bg-brand-fg text-white disabled:opacity-50"
          >
            {busyKey === "save-scheduler" ? "Saving…" : "Save scheduler defaults"}
          </button>
        </div>

        <div className="card p-5 space-y-3">
          <div className="font-semibold text-sm">Status-wise Follow-up Intervals (hours)</div>
          <p className="text-xs text-brand-muted">
            Hours until the next follow-up is scheduled after a record enters each status.
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {FOLLOWUP_STATUSES.map((status) => (
              <label key={status} className="text-sm flex flex-col gap-1">
                <span className="text-xs text-brand-muted">{status}</span>
                <input
                  type="number"
                  min={1}
                  disabled={loading}
                  className="border border-brand-border rounded px-2 py-1 text-sm"
                  value={followup[status] ?? ""}
                  onChange={(e) =>
                    setFollowup((s) => ({ ...s, [status]: Number(e.target.value) }))
                  }
                />
              </label>
            ))}
          </div>
          <button
            type="button"
            disabled={loading || busyKey === "save-followup"}
            onClick={handleSaveFollowup}
            className="text-sm px-3 py-1.5 rounded bg-brand-fg text-white disabled:opacity-50"
          >
            {busyKey === "save-followup" ? "Saving…" : "Save follow-up intervals"}
          </button>
        </div>
      </div>

      {/* Health + recent logs */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="card p-5 space-y-3 md:col-span-1">
          <div className="font-semibold text-sm">Engine Health</div>
          <dl className="text-xs grid grid-cols-2 gap-2">
            <dt className="text-brand-muted">Scheduler</dt>
            <dd>{health?.scheduler_running ? "Running" : "Stopped"}</dd>
            <dt className="text-brand-muted">Pending Outbox</dt>
            <dd>{queueSummary?.pending_outbox ?? "—"}</dd>
            <dt className="text-brand-muted">Failed Outbox</dt>
            <dd>{queueSummary?.failed_outbox ?? "—"}</dd>
            <dt className="text-brand-muted">Sent Today</dt>
            <dd>{queueSummary?.sent_today ?? "—"}</dd>
            <dt className="text-brand-muted">SMTP</dt>
            <dd>{health?.smtp?.ok ? "OK" : health?.smtp?.error || health?.smtp?.reason || "—"}</dd>
            <dt className="text-brand-muted">IMAP</dt>
            <dd>{health?.imap?.ok ? "OK" : health?.imap?.error || health?.imap?.reason || "—"}</dd>
            <dt className="text-brand-muted">Last error</dt>
            <dd className="truncate" title={health?.last_error?.message || ""}>
              {health?.last_error?.message || "—"}
            </dd>
            <dt className="text-brand-muted">Checked</dt>
            <dd>{formatDateTime(health?.checked_at)}</dd>
          </dl>
        </div>
        <div className="card p-5 space-y-3 md:col-span-2">
          <div className="flex items-center justify-between">
            <div className="font-semibold text-sm">Recent Job Runs</div>
            <button
              type="button"
              className="text-xs px-2 py-1 rounded border border-brand-border bg-white"
              onClick={refreshAll}
            >
              Refresh
            </button>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="text-brand-muted">
                <tr className="text-left">
                  <th className="py-1 pr-3">Job</th>
                  <th className="py-1 pr-3">Started</th>
                  <th className="py-1 pr-3">Status</th>
                  <th className="py-1 pr-3">Processed</th>
                  <th className="py-1 pr-3">Message</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-brand-border">
                {cronLogs.map((log) => (
                  <tr key={log.id}>
                    <td className="py-1 pr-3">{log.job_name}</td>
                    <td className="py-1 pr-3 whitespace-nowrap">{formatDateTime(log.started_at)}</td>
                    <td className="py-1 pr-3">
                      <span className={`px-2 py-0.5 rounded ${statusBadge(log.status)}`}>{log.status}</span>
                    </td>
                    <td className="py-1 pr-3">{log.records_processed}</td>
                    <td className="py-1 pr-3 truncate max-w-[320px]" title={log.error_detail || log.message || ""}>
                      {log.error_detail || log.message || "—"}
                    </td>
                  </tr>
                ))}
                {cronLogs.length === 0 && (
                  <tr>
                    <td className="py-3 text-brand-muted" colSpan={5}>
                      No runs recorded yet.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div className="card p-5">
        <div className="font-semibold text-sm">Backend API reference</div>
        <ul className="text-xs text-brand-muted mt-2 space-y-1 list-disc list-inside">
          <li>GET /api/settings/mail-engine · POST /api/settings/test-smtp · POST /api/settings/test-imap</li>
          <li>GET/PUT /api/settings/cron-jobs · POST /api/settings/cron-jobs/&lcub;name&rcub;/run · GET /api/settings/cron-jobs/logs</li>
          <li>POST /api/settings/engine/start · /stop · /restart · GET /api/settings/engine/health</li>
          <li>
            Swagger:{" "}
            <a className="text-signal-red" href="http://localhost:8000/docs" target="_blank">
              localhost:8000/docs
            </a>
          </li>
        </ul>
      </div>
    </div>
  );
}

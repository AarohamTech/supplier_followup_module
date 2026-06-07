"use client";

import { useEffect, useState } from "react";
import { Activity, Mail, AlertTriangle, Send, RefreshCcw } from "lucide-react";
import { api } from "@/lib/api";
import type { MailEngineHealth } from "@/lib/types";

export default function MailEngineStatusCard() {
  const [health, setHealth] = useState<MailEngineHealth | null>(null);
  const [loading, setLoading] = useState(false);

  async function load() {
    setLoading(true);
    try {
      setHealth(await api.getEngineHealth());
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    const id = setInterval(load, 30000);
    return () => clearInterval(id);
  }, []);

  const q = health?.queue;
  const running = health?.scheduler_running;

  const stats = [
    {
      label: "Pending Queue",
      value: q?.pending_outbox ?? "—",
      icon: <Mail size={15} className="text-blue-600" />,
      tone: "bg-blue-50",
    },
    {
      label: "Failed Mails",
      value: q?.failed_outbox ?? "—",
      icon: <AlertTriangle size={15} className="text-rose-600" />,
      tone: "bg-rose-50",
    },
    {
      label: "Sent Today",
      value: q?.sent_today ?? "—",
      icon: <Send size={15} className="text-green-600" />,
      tone: "bg-green-50",
    },
  ];

  return (
    <div className="card p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Activity size={16} className="text-brand-dark" />
          <span className="font-semibold text-sm">Mail Engine</span>
          <span
            className={`text-[10px] px-1.5 py-0.5 rounded-full ${
              running ? "bg-green-100 text-green-700" : "bg-rose-100 text-rose-700"
            }`}
          >
            {running ? "Running" : "Stopped"}
          </span>
        </div>
        <button
          type="button"
          onClick={load}
          disabled={loading}
          className="text-brand-muted hover:text-brand-dark"
          aria-label="Refresh engine status"
        >
          <RefreshCcw size={13} className={loading ? "animate-spin" : ""} />
        </button>
      </div>
      <div className="grid grid-cols-3 gap-2">
        {stats.map((s) => (
          <div key={s.label} className={`rounded-lg p-2.5 ${s.tone}`}>
            <div className="flex items-center gap-1.5">{s.icon}</div>
            <div className="text-lg font-semibold mt-1 leading-none">{s.value}</div>
            <div className="text-[10px] text-brand-muted mt-1">{s.label}</div>
          </div>
        ))}
      </div>
      <div className="mt-3 flex items-center justify-between text-[11px] text-brand-muted">
        <span>
          SMTP{" "}
          <span className={health?.smtp.ok ? "text-green-600" : "text-rose-600"}>
            {health?.smtp.ok ? "OK" : health?.smtp.enabled === false ? "Off" : "Down"}
          </span>
        </span>
        <span>
          IMAP{" "}
          <span className={health?.imap.ok ? "text-green-600" : "text-rose-600"}>
            {health?.imap.ok ? "OK" : health?.imap.enabled === false ? "Off" : "Down"}
          </span>
        </span>
        {health?.last_error?.message ? (
          <span className="text-rose-600 truncate max-w-[140px]" title={health.last_error.message}>
            {health.last_error.job_name}: {health.last_error.message}
          </span>
        ) : (
          <span className="text-green-600">No recent errors</span>
        )}
      </div>
    </div>
  );
}

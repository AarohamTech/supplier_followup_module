"use client";

// Global background poller: watches the "recently sent" feed and pops a toast
// whenever the server sends a mail — independent of which page has focus, since
// the sending happens server-side in the scheduler. Mounted once in AppShell.

import { useEffect, useRef, useState } from "react";
import { Mail, X } from "lucide-react";

import { api } from "@/lib/api";

type Toast = { key: string; title: string; detail: string };

const POLL_MS = 12_000;

export default function SendToaster() {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const sinceRef = useRef<string | null>(null);
  const firstRun = useRef(true);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const poll = async () => {
      try {
        const r = await api.sentFeed(sinceRef.current ?? undefined);
        if (firstRun.current) {
          // Seed the watermark — don't toast mail sent before the app opened.
          firstRun.current = false;
        } else if (r.items.length && !cancelled) {
          const fresh = r.items.slice(0, 4).map((it) => ({
            key: `${it.id}`,
            title: it.supplier_name ? `Sent to ${it.supplier_name}` : "Mail sent",
            detail: it.subject || it.to || "",
          }));
          if (r.items.length > 4) {
            fresh.push({
              key: `more-${r.server_time}`,
              title: `+${r.items.length - 4} more sent`,
              detail: "",
            });
          }
          setToasts((cur) => [...fresh, ...cur].slice(0, 5));
        }
        sinceRef.current = r.server_time;
      } catch {
        /* ignore polling errors */
      }
      if (!cancelled) timer = setTimeout(poll, POLL_MS);
    };

    void poll();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, []);

  // Auto-dismiss the stack a few seconds after the last update.
  useEffect(() => {
    if (!toasts.length) return;
    const t = setTimeout(() => setToasts([]), 6000);
    return () => clearTimeout(t);
  }, [toasts]);

  if (!toasts.length) return null;

  return (
    <div className="fixed bottom-4 right-4 z-[60] flex flex-col gap-2">
      {toasts.map((t) => (
        <div
          key={t.key}
          className="animate-slide-down flex items-start gap-2 rounded-lg border border-emerald-200 bg-white px-3 py-2 shadow-lg"
        >
          <span className="mt-0.5 text-emerald-600">
            <Mail className="h-4 w-4" />
          </span>
          <div className="min-w-0">
            <div className="text-xs font-semibold text-brand-dark">{t.title}</div>
            {t.detail && (
              <div className="max-w-[240px] truncate text-[11px] text-brand-muted">{t.detail}</div>
            )}
          </div>
          <button
            type="button"
            onClick={() => setToasts((c) => c.filter((x) => x.key !== t.key))}
            className="ml-1 text-brand-muted hover:text-brand-dark"
            aria-label="Dismiss"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      ))}
    </div>
  );
}

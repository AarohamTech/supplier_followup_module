"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Bell, CheckCheck } from "lucide-react";

import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { AppNotification } from "@/lib/types";

function timeAgo(iso: string): string {
  const d = new Date(iso);
  const secs = Math.max(0, Math.floor((Date.now() - d.getTime()) / 1000));
  if (secs < 60) return "just now";
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

/** Bell + dropdown notification center. Works for both staff and supplier shells. */
export default function NotificationBell() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [unread, setUnread] = useState(0);
  const [items, setItems] = useState<AppNotification[]>([]);
  const [loading, setLoading] = useState(false);
  const ref = useRef<HTMLDivElement | null>(null);

  const loadCount = useCallback(async () => {
    try {
      const r = await api.notificationsUnreadCount();
      setUnread(r.count);
    } catch {
      /* ignore polling errors */
    }
  }, []);

  // Poll unread count.
  useEffect(() => {
    void loadCount();
    const t = setInterval(loadCount, 20000);
    return () => clearInterval(t);
  }, [loadCount]);

  // Close on outside click.
  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  const openPanel = async () => {
    const next = !open;
    setOpen(next);
    if (next) {
      setLoading(true);
      try {
        setItems(await api.listNotifications(30));
      } catch {
        /* ignore */
      } finally {
        setLoading(false);
      }
    }
  };

  const onItem = async (n: AppNotification) => {
    setOpen(false);
    if (!n.is_read) {
      setItems((prev) => prev.map((x) => (x.id === n.id ? { ...x, is_read: true } : x)));
      setUnread((u) => Math.max(0, u - 1));
      try {
        await api.markNotificationRead(n.id);
      } catch {
        /* ignore */
      }
    }
    if (n.link) router.push(n.link);
  };

  const markAll = async () => {
    setItems((prev) => prev.map((x) => ({ ...x, is_read: true })));
    setUnread(0);
    try {
      await api.markAllNotificationsRead();
    } catch {
      /* ignore */
    }
  };

  const display = unread > 99 ? "99+" : String(unread);

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={openPanel}
        className="relative p-2 rounded-md text-brand-muted hover:bg-red-50 hover:text-signal-red"
        title={unread > 0 ? `${unread} unread notification${unread === 1 ? "" : "s"}` : "Notifications"}
        aria-label="Notifications"
      >
        <Bell size={18} />
        {unread > 0 && (
          <span className="absolute -top-0.5 -right-0.5 bg-signal-red text-white text-[10px] font-bold rounded-full px-1 min-w-[16px] text-center">
            {display}
          </span>
        )}
      </button>

      {open && (
        <div className="animate-fade-in absolute right-0 z-50 mt-2 w-[min(22rem,calc(100vw-2rem))] origin-top-right overflow-hidden rounded-lg border border-brand-border bg-card shadow-xl">
          <div className="flex items-center justify-between border-b border-brand-border px-4 py-2.5">
            <span className="text-sm font-semibold text-brand-dark">Notifications</span>
            {items.some((x) => !x.is_read) && (
              <button onClick={markAll} className="inline-flex items-center gap-1 text-xs font-medium text-signal-red hover:underline">
                <CheckCheck size={13} /> Mark all read
              </button>
            )}
          </div>
          <div className="max-h-[60vh] overflow-y-auto">
            {loading && <div className="px-4 py-8 text-center text-sm text-brand-muted">Loading…</div>}
            {!loading && items.length === 0 && (
              <div className="px-4 py-10 text-center text-sm text-brand-muted">You're all caught up.</div>
            )}
            {items.map((n) => (
              <button
                key={n.id}
                onClick={() => onItem(n)}
                className={cn(
                  "flex w-full flex-col gap-0.5 border-b border-brand-border px-4 py-3 text-left hover:bg-subtle",
                  !n.is_read && "bg-red-50/40",
                )}
              >
                <div className="flex items-start gap-2">
                  {!n.is_read && <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-signal-red" />}
                  <div className="min-w-0 flex-1">
                    <div className={cn("text-sm", n.is_read ? "text-brand-dark" : "font-semibold text-brand-dark")}>
                      {n.title}
                    </div>
                    {n.body && <div className="truncate text-xs text-brand-muted">{n.body}</div>}
                    <div className="mt-0.5 text-[10px] uppercase tracking-wide text-brand-muted">{timeAgo(n.created_at)}</div>
                  </div>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

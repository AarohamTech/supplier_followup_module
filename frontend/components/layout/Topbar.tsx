"use client";

import { Bell, LogOut, RadioTower } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

const ROLE_LABEL: Record<string, string> = {
  admin: "Administrator",
  manager: "Manager",
  user: "User",
  viewer: "Viewer",
};

export default function Topbar() {
  const { user, logout } = useAuth();
  const [unread, setUnread] = useState<number>(0);

  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      try {
        const dash = await api.hubDashboard();
        if (!cancelled) setUnread(Number(dash?.unread_inbound ?? 0));
      } catch {
        /* ignore polling errors */
      }
    };
    void tick();
    const t = setInterval(tick, 15000);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, []);

  const display = unread > 99 ? "99+" : String(unread);
  const name = user?.full_name || user?.email || "User";
  const initial = name.charAt(0).toUpperCase();
  const role = ROLE_LABEL[user?.role ?? ""] ?? user?.role ?? "User";

  return (
    <header className="sticky top-0 z-30 border-b border-brand-border/80 bg-white/85 backdrop-blur-xl">
      <div className="mx-auto flex h-16 max-w-[1680px] items-center gap-4 px-4 sm:px-5 lg:px-7">
        <Link href="/" className="group flex min-w-0 items-center gap-3" aria-label="Dashboard">
          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-brand-dark text-white shadow-card">
            <RadioTower size={18} />
          </span>
          <span className="min-w-0">
            <span className="block truncate text-[15px] font-bold leading-tight text-brand-dark">
              Supplier Follow-up Agent
            </span>
            <span className="hidden text-xs leading-tight text-brand-muted sm:block">
              Procurement control tower
            </span>
          </span>
        </Link>

        <div className="ml-auto flex items-center gap-2 sm:gap-3">
          <Link
            href="/mail-history"
            className="relative grid h-9 w-9 place-items-center rounded-lg border border-brand-border bg-white text-brand-muted shadow-sm hover:border-signal-red/30 hover:text-signal-red"
            title={unread > 0 ? `${unread} new supplier mail${unread === 1 ? "" : "s"}` : "No new mails"}
            aria-label="Open communication hub"
          >
            <Bell size={17} />
            {unread > 0 && (
              <span className="absolute -right-1 -top-1 min-w-[18px] rounded-full bg-emerald-600 px-1 text-center text-[10px] font-bold leading-[18px] text-white shadow-sm">
                {display}
              </span>
            )}
          </Link>

          <div className="hidden items-center rounded-lg border border-brand-border bg-white/80 px-2.5 py-1.5 shadow-sm sm:flex">
            <div className="mr-2 text-right">
              <div className="max-w-44 truncate text-sm font-semibold leading-tight text-brand-dark">{name}</div>
              <div className="text-[10px] font-semibold uppercase text-brand-muted">{role}</div>
            </div>
            <div className="grid h-8 w-8 place-items-center rounded-md bg-red-50 text-sm font-bold text-signal-red">
              {initial}
            </div>
          </div>

          <button
            onClick={logout}
            title="Sign out"
            className="grid h-9 w-9 place-items-center rounded-lg border border-brand-border bg-white text-brand-muted shadow-sm hover:border-signal-red/30 hover:bg-red-50 hover:text-signal-red"
            aria-label="Sign out"
          >
            <LogOut size={17} />
          </button>
        </div>
      </div>
    </header>
  );
}

"use client";

import { Bell, Menu } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";

export default function Topbar() {
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

  return (
    <header className="sticky top-0 z-20 bg-white border-b border-brand-border">
      <div className="max-w-[1600px] mx-auto px-6 py-3 flex items-center gap-4">
        <button className="p-2 rounded hover:bg-gray-100"><Menu size={18} /></button>
        <div className="flex flex-col">
          <span className="text-signal-red font-bold text-lg leading-tight">Supplier Follow-up Agent</span>
          <span className="text-xs text-brand-muted leading-tight">PO-wise and Material-wise Automated Follow-up System</span>
        </div>
        <div className="flex-1" />
        <Link
          href="/mail-history"
          className="relative p-2 rounded hover:bg-gray-100"
          title={unread > 0 ? `${unread} new supplier mail${unread === 1 ? "" : "s"}` : "No new mails"}
        >
          <Bell size={18} />
          {unread > 0 && (
            <span className="absolute -top-0.5 -right-0.5 bg-emerald-500 text-white text-[10px] font-bold rounded-full px-1 min-w-[16px] text-center">
              {display}
            </span>
          )}
        </Link>
        <div className="flex items-center gap-3">
          <div className="text-right">
            <div className="text-sm font-medium">Rajesh Kumar</div>
            <div className="text-[10px] uppercase text-brand-muted tracking-wider">Senior Procurement Mgr</div>
          </div>
          <div className="h-9 w-9 rounded-full bg-gray-200" />
        </div>
      </div>
    </header>
  );
}

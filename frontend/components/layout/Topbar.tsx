"use client";

import { LogOut, Menu } from "lucide-react";
import Link from "next/link";

import { Logo } from "@/components/brand/Logo";
import { useAuth } from "@/lib/auth";
import NotificationBell from "@/components/NotificationBell";

const ROLE_LABEL: Record<string, string> = {
  admin: "Administrator",
  manager: "Manager",
  user: "User",
  viewer: "Viewer",
};

export default function Topbar({ onMenuClick }: { onMenuClick?: () => void }) {
  const { user, logout } = useAuth();
  const name = user?.full_name || user?.email || "User";
  const initial = name.charAt(0).toUpperCase();

  return (
    <header className="sticky top-0 z-30 border-b border-brand-border bg-white/95 backdrop-blur">
      <div className="max-w-[1600px] mx-auto px-4 py-3 sm:px-6 lg:px-8 flex items-center gap-4">
        <button
          type="button"
          onClick={onMenuClick}
          className="p-2 rounded-md hover:bg-gray-100 md:hidden"
          aria-label="Open navigation"
        >
          <Menu size={18} />
        </button>
        <Link href="/" className="flex items-center gap-3" aria-label="Home">
          <span className="text-signal-red">
            <Logo size={34} />
          </span>
          <div className="flex flex-col">
            <span className="text-signal-red font-bold text-lg leading-tight">Supplier Follow-up Agent</span>
            <span className="hidden text-xs text-brand-muted leading-tight sm:block">
              Harmony × Hariom · Automated PO &amp; Material Follow-up
            </span>
          </div>
        </Link>
        <div className="flex-1" />
        <NotificationBell />
        <div className="flex items-center gap-3">
          <div className="hidden text-right sm:block">
            <div className="text-sm font-medium">{name}</div>
            <div className="text-[10px] uppercase text-brand-muted tracking-wider">
              {ROLE_LABEL[user?.role ?? ""] ?? user?.role}
            </div>
          </div>
          <div className="h-9 w-9 rounded-full bg-red-50 text-signal-red flex items-center justify-center text-sm font-semibold">
            {initial}
          </div>
          <button
            onClick={logout}
            title="Sign out"
            className="p-2 rounded-md hover:bg-gray-100 text-brand-muted hover:text-signal-red"
          >
            <LogOut size={18} />
          </button>
        </div>
      </div>
    </header>
  );
}

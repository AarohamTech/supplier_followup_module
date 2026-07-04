"use client";

import { useEffect, useState } from "react";
import { ChevronDown, LogOut, Menu } from "lucide-react";
import Link from "next/link";

import { Logo, ZanvarMark } from "@/components/brand/Logo";
import { useAuth } from "@/lib/auth";
import { api } from "@/lib/api";
import type { CompanyBrief } from "@/lib/types";
import NotificationBell from "@/components/NotificationBell";
import ThemeToggle from "@/components/layout/ThemeToggle";

const ROLE_LABEL: Record<string, string> = {
  admin: "Administrator",
  manager: "Manager",
  user: "User",
  viewer: "Viewer",
};

function CompanySwitcher() {
  const { company, switchCompany } = useAuth();
  const [companies, setCompanies] = useState<CompanyBrief[]>([]);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let alive = true;
    api
      .listCompanies()
      .then((rows) => alive && setCompanies(rows))
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, []);

  const current = company?.brand_name || company?.display_name || "H-Connect";
  if (companies.length <= 1) {
    return <span className="hidden text-xs font-semibold text-brand-dark sm:inline">{current}</span>;
  }

  const pick = async (code: string) => {
    if (busy || code === company?.code) {
      setOpen(false);
      return;
    }
    setBusy(true);
    try {
      await switchCompany(code);
      if (typeof window !== "undefined") window.location.reload();
    } finally {
      setBusy(false);
      setOpen(false);
    }
  };

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        disabled={busy}
        className="inline-flex items-center gap-1 rounded-md border border-brand-border bg-card px-2.5 py-1.5 text-xs font-semibold text-brand-dark hover:bg-subtle"
      >
        {current}
        <ChevronDown size={14} className="text-brand-muted" />
      </button>
      {open && (
        <div className="absolute right-0 z-40 mt-1 w-44 overflow-hidden rounded-md border border-brand-border bg-card shadow-card animate-slide-down">
          {companies.map((c) => (
            <button
              key={c.code}
              type="button"
              onClick={() => pick(c.code)}
              className={
                c.code === company?.code
                  ? "block w-full px-3 py-2 text-left text-xs font-semibold text-signal-red bg-signal-red/10"
                  : "block w-full px-3 py-2 text-left text-xs text-brand-dark hover:bg-subtle"
              }
            >
              {c.display_name}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export default function Topbar({ onMenuClick }: { onMenuClick?: () => void }) {
  const { user, company, logout } = useAuth();
  const name = user?.full_name || user?.email || "User";
  const initial = name.charAt(0).toUpperCase();
  const isStaff = !!user && user.supplier_id == null && user.emp_code == null;
  const brandName = company?.brand_name || "H-Connect";

  return (
    <header className="sticky top-0 z-30 border-b border-brand-border bg-card">
      <div className="mx-auto flex h-16 max-w-[1600px] items-center gap-2 px-4 sm:gap-4 sm:px-6 lg:px-8">
        <button
          type="button"
          onClick={onMenuClick}
          className="grid h-9 w-9 place-items-center rounded-md text-brand-muted hover:bg-subtle hover:text-brand-dark md:hidden"
          aria-label="Open navigation"
        >
          <Menu size={18} />
        </button>
        <Link href="/" className="flex min-w-0 items-center gap-2 sm:gap-3" aria-label="Home">
          <ZanvarMark size={32} />
          <span className="shrink-0 text-signal-red">
            <Logo size={30} />
          </span>
          <div className="flex min-w-0 flex-col">
            <span className="truncate text-sm font-semibold leading-tight text-brand-dark sm:text-[15px]">
              {brandName}
            </span>
            <span className="hidden text-xs text-brand-muted leading-tight sm:block">
              Industrial procurement control tower
            </span>
          </div>
        </Link>
        <div className="flex-1" />
        {isStaff && <CompanySwitcher />}
        <ThemeToggle />
        <NotificationBell />
        <div className="hidden h-6 w-px bg-brand-border sm:block" />
        <div className="flex items-center gap-1 sm:gap-2.5">
          <div className="hidden text-right sm:block">
            <div className="text-sm font-medium">{name}</div>
            <div className="text-[10px] uppercase text-brand-muted tracking-wider">
              {ROLE_LABEL[user?.role ?? ""] ?? user?.role}
            </div>
          </div>
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-signal-red/10 text-xs font-semibold text-signal-red ring-1 ring-inset ring-signal-red/20">
            {initial}
          </div>
          <button
            onClick={logout}
            title="Sign out"
            className="grid h-9 w-9 place-items-center rounded-md text-brand-muted hover:bg-subtle hover:text-signal-red"
          >
            <LogOut size={18} />
          </button>
        </div>
      </div>
    </header>
  );
}

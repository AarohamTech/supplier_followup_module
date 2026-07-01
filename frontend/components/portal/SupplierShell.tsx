"use client";

import { usePathname } from "next/navigation";
import { LogOut, Menu } from "lucide-react";

import { Logo, ZanvarMark } from "@/components/brand/Logo";
import { useAuth } from "@/lib/auth";
import SupplierSidebar from "@/components/portal/SupplierSidebar";
import NotificationBell from "@/components/NotificationBell";
import ThemeToggle from "@/components/layout/ThemeToggle";

/**
 * Chrome for supplier portal accounts: a branded topbar + the supplier sidebar.
 * Deliberately omits the staff `StoreBootstrap` (which calls staff-only APIs).
 */
export default function SupplierShell({
  children,
  open,
  onMenuClick,
  onClose,
}: {
  children: React.ReactNode;
  open: boolean;
  onMenuClick: () => void;
  onClose: () => void;
}) {
  const { user, logout } = useAuth();
  const pathname = usePathname();
  const name = user?.supplier_name || user?.full_name || user?.email || "Supplier";
  const initial = name.charAt(0).toUpperCase();

  return (
    <div className="flex min-h-screen flex-col bg-brand-surface">
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
          <div className="flex min-w-0 items-center gap-2 sm:gap-3">
            <ZanvarMark size={32} />
            <span className="shrink-0 text-signal-red">
              <Logo size={30} />
            </span>
            <div className="flex min-w-0 flex-col">
              <span className="truncate text-sm font-semibold leading-tight text-brand-dark sm:text-[15px]">Supplier Portal</span>
              <span className="hidden text-xs text-brand-muted leading-tight sm:block">
                Purchase orders, communication and shipments
              </span>
            </div>
          </div>
          <div className="flex-1" />
          <div className="flex items-center gap-1 sm:gap-2.5">
            <ThemeToggle />
            <NotificationBell />
            <div className="hidden h-6 w-px bg-brand-border sm:block" />
            <div className="hidden text-right sm:block">
              <div className="text-sm font-medium">{name}</div>
              <div className="text-[10px] uppercase text-brand-muted tracking-wider">Supplier</div>
            </div>
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-red-50 text-xs font-semibold text-signal-red ring-1 ring-inset ring-red-100">
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

      <div className="flex-1 flex min-h-0">
        <SupplierSidebar open={open} onClose={onClose} />
        <main
          key={pathname}
          className="mx-auto w-full max-w-[1600px] min-w-0 flex-1 px-4 py-6 sm:px-6 lg:px-8"
        >
          {children}
        </main>
      </div>
    </div>
  );
}

"use client";

import { usePathname } from "next/navigation";
import { LogOut, Menu } from "lucide-react";

import { Logo } from "@/components/brand/Logo";
import { useAuth } from "@/lib/auth";
import SupplierSidebar from "@/components/portal/SupplierSidebar";
import NotificationBell from "@/components/NotificationBell";

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
    <div className="min-h-screen flex flex-col bg-brand-surface">
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
          <div className="flex items-center gap-3">
            <span className="text-signal-red">
              <Logo size={34} />
            </span>
            <div className="flex flex-col">
              <span className="text-signal-red font-bold text-lg leading-tight">Supplier Portal</span>
              <span className="hidden text-xs text-brand-muted leading-tight sm:block">
                Harmony × Hariom · Purchase Orders &amp; Shipments
              </span>
            </div>
          </div>
          <div className="flex-1" />
          <div className="flex items-center gap-3">
            <NotificationBell />
            <div className="hidden text-right sm:block">
              <div className="text-sm font-medium">{name}</div>
              <div className="text-[10px] uppercase text-brand-muted tracking-wider">Supplier</div>
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

      <div className="flex-1 flex min-h-0">
        <SupplierSidebar open={open} onClose={onClose} />
        <main
          key={pathname}
          className="page-enter flex-1 min-w-0 px-4 py-5 sm:px-6 lg:px-8 max-w-[1600px] w-full mx-auto"
        >
          {children}
        </main>
      </div>
    </div>
  );
}

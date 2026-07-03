"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutDashboard, FileSpreadsheet, Inbox, MessagesSquare, ListChecks, ListFilter, Send, Truck, X } from "lucide-react";

import { cn } from "@/lib/utils";

const items = [
  { href: "/eportal", label: "Dashboard", icon: LayoutDashboard },
  { href: "/eportal/pos", label: "My Purchase Orders", icon: FileSpreadsheet },
  { href: "/eportal/followups", label: "Black Follow-ups", icon: ListFilter },
  { href: "/eportal/tasks", label: "My Tasks", icon: ListChecks },
  { href: "/eportal/communication", label: "Communication", icon: MessagesSquare },
  { href: "/eportal/compose", label: "Compose Mail", icon: Send },
  { href: "/eportal/shipments", label: "My Shipments", icon: Truck },
  { href: "/eportal/mails", label: "My Customer Mails", icon: Inbox },
];

function isActive(path: string, href: string) {
  if (href === "/eportal") return path === "/eportal";
  return path === href || path.startsWith(`${href}/`);
}

function NavList({ onNavigate }: { onNavigate?: () => void }) {
  const path = usePathname();
  return (
    <nav aria-label="Employee navigation" className="space-y-1">
      {items.map((it) => {
        const active = isActive(path, it.href);
        const Icon = it.icon;
        return (
          <Link
            key={it.href}
            href={it.href}
            onClick={onNavigate}
            aria-current={active ? "page" : undefined}
            className={cn(
              "group flex items-center gap-3 rounded-md px-3 py-2 text-[13px] font-medium",
              active
                ? "bg-card text-brand-dark shadow-sm ring-1 ring-inset ring-brand-border"
                : "text-brand-muted hover:bg-card hover:text-brand-dark",
            )}
          >
            <Icon
              size={16}
              strokeWidth={1.8}
              className={cn("shrink-0", active ? "text-signal-red" : "text-brand-muted group-hover:text-brand-muted")}
            />
            <span className="truncate">{it.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}

export default function EmployeeSidebar({ open = false, onClose }: { open?: boolean; onClose?: () => void }) {
  return (
    <>
      <aside className="hidden w-64 shrink-0 border-r border-brand-border bg-subtle md:block">
        <div className="sticky top-16 h-[calc(100vh-4rem)] overflow-y-auto px-3 py-5">
          <div className="mb-1.5 px-3 text-[10px] font-semibold uppercase tracking-[0.14em] text-brand-muted">
            Employee Portal
          </div>
          <NavList />
        </div>
      </aside>

      {open && (
        <div className="fixed inset-0 z-40 md:hidden">
          <button type="button" className="mobile-nav-backdrop absolute inset-0 bg-black/30" onClick={onClose} aria-label="Close navigation" />
          <aside className="mobile-nav-drawer relative h-full w-[min(20rem,86vw)] border-r border-brand-border bg-subtle shadow-2xl">
            <div className="flex h-16 items-center justify-between border-b border-brand-border px-4">
              <div>
                <div className="text-sm font-semibold text-brand-dark">Employee Portal</div>
                <div className="text-[11px] text-brand-muted">Your purchase orders</div>
              </div>
              <button type="button" onClick={onClose} className="rounded-md p-2 text-brand-muted hover:bg-subtle" aria-label="Close navigation">
                <X size={18} />
              </button>
            </div>
            <div className="h-[calc(100vh-4rem)] overflow-y-auto px-3 py-5">
              <NavList onNavigate={onClose} />
            </div>
          </aside>
        </div>
      )}
    </>
  );
}

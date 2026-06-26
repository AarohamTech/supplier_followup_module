"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BarChart3,
  FileSpreadsheet,
  Gauge,
  Inbox,
  LayoutDashboard,
  ListChecks,
  Mail,
  MailCheck,
  MessagesSquare,
  Settings,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Truck,
  Users,
  Wand2,
  X,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth";
import type { Role } from "@/lib/types";

type NavItem = {
  href: string;
  label: string;
  icon: typeof LayoutDashboard;
  minRole?: Role;
};

const items: NavItem[] = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/assistant", label: "HI Assistant", icon: Sparkles },
  { href: "/insights", label: "HI Insights", icon: Gauge },
  { href: "/black-followups", label: "Black Follow-ups", icon: ShieldAlert },
  { href: "/po-followups", label: "PO Follow-ups", icon: FileSpreadsheet },
  { href: "/suppliers", label: "Supplier Master", icon: Users },
  { href: "/emails", label: "Email Master", icon: Mail },
  { href: "/mail-history", label: "Comm Hub", icon: MessagesSquare },
  { href: "/asns", label: "Shipments (ASN)", icon: Truck },
  { href: "/customer-mails", label: "Customer Mails", icon: Inbox },
  { href: "/approvals", label: "Approvals", icon: MailCheck, minRole: "manager" },
  { href: "/tasks", label: "Tasks", icon: ListChecks },
  { href: "/reports", label: "Reports", icon: BarChart3 },
  { href: "/ai-prompts", label: "HI Prompts", icon: Wand2, minRole: "manager" },
  { href: "/settings", label: "Settings", icon: Settings, minRole: "manager" },
  { href: "/admin/users", label: "Users", icon: ShieldCheck, minRole: "admin" },
];

function isActivePath(path: string, href: string) {
  if (href === "/") return path === "/";
  return path === href || path.startsWith(`${href}/`);
}

function NavList({ onNavigate }: { onNavigate?: () => void }) {
  const path = usePathname();
  const { hasRole } = useAuth();
  const visible = items.filter((it) => !it.minRole || hasRole(it.minRole));

  return (
    <nav className="space-y-1">
      {visible.map((it) => {
        const active = isActivePath(path, it.href);
        const Icon = it.icon;

        return (
          <Link
            key={it.href}
            href={it.href}
            onClick={onNavigate}
            aria-current={active ? "page" : undefined}
            className={cn(
              "group flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium",
              active
                ? "bg-red-50 text-signal-red shadow-[inset_3px_0_0_#E11D2E]"
                : "text-brand-dark hover:bg-gray-50 hover:text-signal-red",
            )}
          >
            <Icon
              size={16}
              className={cn("shrink-0", active ? "text-signal-red" : "text-brand-muted group-hover:text-signal-red")}
            />
            <span className="truncate">{it.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}

export default function Sidebar({ open = false, onClose }: { open?: boolean; onClose?: () => void }) {
  return (
    <>
      <aside className="hidden w-60 shrink-0 border-r border-brand-border bg-white md:block">
        <div className="sticky top-[65px] h-[calc(100vh-65px)] overflow-y-auto p-3">
          <NavList />
        </div>
      </aside>

      {open && (
        <div className="fixed inset-0 z-40 md:hidden">
          <button
            type="button"
            className="absolute inset-0 bg-black/30"
            onClick={onClose}
            aria-label="Close navigation"
          />
          <aside className="animate-fade-in-up relative h-full w-[min(20rem,86vw)] border-r border-brand-border bg-white shadow-2xl">
            <div className="flex h-[65px] items-center justify-between border-b border-brand-border px-4">
              <div>
                <div className="text-sm font-semibold text-signal-red">Supplier Follow-up</div>
                <div className="text-[11px] text-brand-muted">Navigation</div>
              </div>
              <button type="button" onClick={onClose} className="rounded-md p-2 text-brand-muted hover:bg-gray-100">
                <X size={18} />
              </button>
            </div>
            <div className="h-[calc(100vh-65px)] overflow-y-auto p-3">
              <NavList onNavigate={onClose} />
            </div>
          </aside>
        </div>
      )}
    </>
  );
}

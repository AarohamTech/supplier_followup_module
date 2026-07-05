"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  BarChart3,
  ClipboardList,
  Database,
  FileSpreadsheet,
  Gauge,
  Inbox,
  LayoutDashboard,
  ListChecks,
  Mail,
  MailCheck,
  MessagesSquare,
  PieChart,
  Send,
  Settings,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Truck,
  Users,
  UserCheck,
  UserCog,
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

const groups: { label: string; items: NavItem[] }[] = [
  {
    label: "Overview",
    items: [
      { href: "/", label: "Dashboard", icon: LayoutDashboard },
      { href: "/assistant", label: "HI Assistant", icon: Sparkles },
      { href: "/insights", label: "HI Insights", icon: Gauge },
    ],
  },
  {
    label: "Procurement",
    items: [
      { href: "/black-followups", label: "Black Follow-ups", icon: ShieldAlert },
      { href: "/purchase-orders", label: "Purchase Orders", icon: ClipboardList, minRole: "admin" },
      { href: "/po-followups", label: "PO Follow-ups", icon: FileSpreadsheet },
      { href: "/suppliers", label: "Supplier Master", icon: Users },
      { href: "/emails", label: "Email Master", icon: Mail },
      { href: "/asns", label: "Shipments (ASN)", icon: Truck },
    ],
  },
  {
    label: "Communication",
    items: [
      { href: "/mail-history", label: "Communication Hub", icon: MessagesSquare },
      { href: "/compose", label: "Compose Mail", icon: Send, minRole: "user" },
      { href: "/customer-mails", label: "Customer Mails", icon: Inbox },
      { href: "/approvals", label: "Approvals", icon: MailCheck, minRole: "manager" },
      { href: "/tasks", label: "Tasks", icon: ListChecks },
      { href: "/tasks/analytics", label: "Task Analytics", icon: Activity, minRole: "viewer" },
      { href: "/reports", label: "Reports", icon: BarChart3 },
    ],
  },
  {
    label: "Administration",
    items: [
      { href: "/reports/workload", label: "Workload Report", icon: PieChart, minRole: "admin" },
      { href: "/ai-prompts", label: "HI Prompts", icon: Wand2, minRole: "manager" },
      { href: "/settings", label: "Settings", icon: Settings, minRole: "manager" },
      { href: "/supplier-assignments", label: "Supplier Assignments", icon: UserCheck, minRole: "manager" },
      { href: "/admin/users", label: "Users", icon: ShieldCheck, minRole: "admin" },
      { href: "/employees", label: "Employee Logins", icon: UserCog, minRole: "admin" },
      { href: "/crm-ingestion", label: "CRM Ingestion", icon: Database, minRole: "admin" },
    ],
  },
];

function isActivePath(path: string, href: string) {
  if (href === "/") return path === "/";
  return path === href || path.startsWith(`${href}/`);
}

function NavList({ onNavigate }: { onNavigate?: () => void }) {
  const path = usePathname();
  const { hasRole } = useAuth();
  return (
    <nav aria-label="Primary navigation" className="space-y-5">
      {groups.map((group) => {
        const visible = group.items.filter((item) => !item.minRole || hasRole(item.minRole));
        if (visible.length === 0) return null;

        return (
          <div key={group.label}>
            <div className="mb-1.5 px-3 text-[10px] font-semibold uppercase tracking-[0.14em] text-brand-muted">
              {group.label}
            </div>
            <div className="space-y-1">
              {visible.map((item) => {
                const active = isActivePath(path, item.href);
                const Icon = item.icon;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
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
                    <span className="truncate">{item.label}</span>
                  </Link>
                );
              })}
            </div>
          </div>
        );
      })}
    </nav>
  );
}

export default function Sidebar({ open = false, onClose }: { open?: boolean; onClose?: () => void }) {
  return (
    <>
      <aside className="hidden w-64 shrink-0 border-r border-brand-border bg-subtle md:block">
        <div className="sticky top-16 h-[calc(100vh-4rem)] overflow-y-auto px-3 py-5">
          <NavList />
        </div>
      </aside>

      {open && (
        <div className="fixed inset-0 z-40 md:hidden">
          <button
            type="button"
            className="mobile-nav-backdrop absolute inset-0 bg-black/30"
            onClick={onClose}
            aria-label="Close navigation"
          />
          <aside className="mobile-nav-drawer relative h-full w-[min(20rem,86vw)] border-r border-brand-border bg-subtle shadow-2xl">
            <div className="flex h-16 items-center justify-between border-b border-brand-border px-4">
              <div>
                <div className="text-sm font-semibold text-brand-dark">Supplier Follow-up</div>
                <div className="text-[11px] text-brand-muted">Procurement control tower</div>
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

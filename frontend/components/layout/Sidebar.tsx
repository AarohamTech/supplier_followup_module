"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  FileSpreadsheet,
  Users,
  Mail,
  MessagesSquare,
  BarChart3,
  Settings,
  Inbox,
  ListChecks,
  MailCheck,
  ShieldCheck,
  Sparkles,
  Gauge,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth";
import type { Role } from "@/lib/types";

type Section = "monitor" | "operations" | "governance";

type NavItem = {
  href: string;
  label: string;
  icon: typeof LayoutDashboard;
  section: Section;
  minRole?: Role;
};

const items: NavItem[] = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard, section: "monitor" },
  { href: "/assistant", label: "AI Assistant", icon: Sparkles, section: "monitor" },
  { href: "/insights", label: "AI Insights", icon: Gauge, section: "monitor" },
  { href: "/reports", label: "Reports", icon: BarChart3, section: "monitor" },
  { href: "/po-followups", label: "PO Follow-ups", icon: FileSpreadsheet, section: "operations" },
  { href: "/suppliers", label: "Supplier Master", icon: Users, section: "operations" },
  { href: "/emails", label: "Email Master", icon: Mail, section: "operations" },
  { href: "/mail-history", label: "Comm Hub", icon: MessagesSquare, section: "operations" },
  { href: "/customer-mails", label: "Customer Mails", icon: Inbox, section: "operations" },
  { href: "/tasks", label: "Tasks", icon: ListChecks, section: "operations" },
  { href: "/approvals", label: "Approvals", icon: MailCheck, section: "governance", minRole: "manager" },
  { href: "/settings", label: "Settings", icon: Settings, section: "governance", minRole: "manager" },
  { href: "/admin/users", label: "Users", icon: ShieldCheck, section: "governance", minRole: "admin" },
];

const sections: { key: Section; label: string }[] = [
  { key: "monitor", label: "Monitor" },
  { key: "operations", label: "Operations" },
  { key: "governance", label: "Governance" },
];

function isActive(path: string, href: string) {
  if (href === "/") return path === "/";
  return path === href || path.startsWith(`${href}/`);
}

export default function Sidebar() {
  const path = usePathname();
  const { hasRole } = useAuth();
  const visible = items.filter((it) => !it.minRole || hasRole(it.minRole));

  return (
    <aside className="hidden w-64 shrink-0 border-r border-brand-border/80 bg-white/58 backdrop-blur-xl md:block">
      <nav className="sticky top-16 p-3">
        {sections.map((section) => {
          const group = visible.filter((it) => it.section === section.key);
          if (group.length === 0) return null;

          return (
            <div key={section.key} className="mb-4 last:mb-0">
              <div className="px-3 pb-1.5 text-[11px] font-bold uppercase text-brand-muted">
                {section.label}
              </div>
              <div className="space-y-1">
                {group.map((it) => {
                  const active = isActive(path, it.href);
                  const Icon = it.icon;
                  return (
                    <Link
                      key={it.href}
                      href={it.href}
                      aria-current={active ? "page" : undefined}
                      className={cn(
                        "group flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-semibold",
                        active
                          ? "bg-brand-dark text-white shadow-card"
                          : "text-brand-muted hover:bg-white hover:text-brand-dark hover:shadow-sm",
                      )}
                    >
                      <span
                        className={cn(
                          "grid h-7 w-7 place-items-center rounded-md",
                          active ? "bg-white/10 text-white" : "bg-brand-surface text-brand-muted group-hover:text-signal-red",
                        )}
                      >
                        <Icon size={15} />
                      </span>
                      <span className="truncate">{it.label}</span>
                    </Link>
                  );
                })}
              </div>
            </div>
          );
        })}
      </nav>
    </aside>
  );
}

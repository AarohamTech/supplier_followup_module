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
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth";
import type { Role } from "@/lib/types";

type NavItem = {
  href: string;
  label: string;
  icon: typeof LayoutDashboard;
  minRole?: Role; // omitted = visible to any authenticated user (viewer+)
};

const items: NavItem[] = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/po-followups", label: "PO Follow-ups", icon: FileSpreadsheet },
  { href: "/suppliers", label: "Supplier Master", icon: Users },
  { href: "/emails", label: "Email Master", icon: Mail },
  { href: "/mail-history", label: "Comm Hub", icon: MessagesSquare },
  { href: "/customer-mails", label: "Customer Mails", icon: Inbox },
  { href: "/approvals", label: "Approvals", icon: MailCheck, minRole: "manager" },
  { href: "/tasks", label: "Tasks", icon: ListChecks },
  { href: "/reports", label: "Reports", icon: BarChart3 },
  { href: "/settings", label: "Settings", icon: Settings, minRole: "manager" },
  { href: "/admin/users", label: "Users", icon: ShieldCheck, minRole: "admin" },
];

export default function Sidebar() {
  const path = usePathname();
  const { hasRole } = useAuth();
  const visible = items.filter((it) => !it.minRole || hasRole(it.minRole));

  return (
    <aside className="hidden md:block w-56 border-r border-brand-border bg-white">
      <nav className="p-3 space-y-1 sticky top-[64px]">
        {visible.map((it) => {
          const active = path === it.href;
          const Icon = it.icon;
          return (
            <Link key={it.href} href={it.href}
              className={cn(
                "flex items-center gap-3 px-3 py-2 rounded-md text-sm",
                active ? "bg-red-50 text-signal-red font-medium" : "text-brand-dark hover:bg-gray-50"
              )}>
              <Icon size={16} />
              <span>{it.label}</span>
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}

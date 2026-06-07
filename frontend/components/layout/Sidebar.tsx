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
} from "lucide-react";
import { cn } from "@/lib/utils";

const items = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/po-followups", label: "PO Follow-ups", icon: FileSpreadsheet },
  { href: "/suppliers", label: "Supplier Master", icon: Users },
  { href: "/emails", label: "Email Master", icon: Mail },
  { href: "/mail-history", label: "Comm Hub", icon: MessagesSquare },
  { href: "/customer-mails", label: "Customer Mails", icon: Inbox },
  { href: "/tasks", label: "Tasks", icon: ListChecks },
  { href: "/reports", label: "Reports", icon: BarChart3 },
  { href: "/settings", label: "Settings", icon: Settings },
];

export default function Sidebar() {
  const path = usePathname();
  return (
    <aside className="hidden md:block w-56 border-r border-brand-border bg-white">
      <nav className="p-3 space-y-1 sticky top-[64px]">
        {items.map((it) => {
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

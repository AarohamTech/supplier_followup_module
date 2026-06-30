"use client";
import { ArrowUpRight, Bell, Clock, Edit3, Mail, Zap } from "lucide-react";
import Link from "next/link";

const actions = [
  { icon: Mail, title: "Generate follow-up", desc: "Open the PO mail queue", href: "/po-followups" },
  { icon: Clock, title: "Communication history", desc: "Review drafts and sent mail", href: "/mail-history" },
  { icon: Edit3, title: "Supplier email mapping", desc: "Maintain delivery addresses", href: "/emails" },
  { icon: Bell, title: "Procurement reports", desc: "Review delay patterns", href: "/reports" },
];

export default function ActionCenter() {
  return (
    <div className="card overflow-hidden">
      <div className="flex items-center gap-2 border-b border-brand-border px-4 py-3">
        <Zap size={14} className="text-signal-red" />
        <div className="text-sm font-semibold">Quick actions</div>
      </div>
      <div className="p-2">
        {actions.map((a) => {
          const I = a.icon;
          return (
            <Link key={a.title} href={a.href} className="group flex w-full items-center gap-3 rounded-md p-2.5 text-left hover:bg-subtle">
              <div className="grid h-8 w-8 shrink-0 place-content-center rounded-md bg-subtle text-brand-muted group-hover:text-brand-dark"><I size={14} /></div>
              <div className="min-w-0 flex-1">
                <div className="text-sm font-medium">{a.title}</div>
                <div className="text-xs text-brand-muted">{a.desc}</div>
              </div>
              <ArrowUpRight size={13} className="text-gray-300 group-hover:text-brand-muted" />
            </Link>
          );
        })}
      </div>
    </div>
  );
}

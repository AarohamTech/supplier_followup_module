"use client";
import { Mail, Clock, Edit3, Bell } from "lucide-react";
import Link from "next/link";

const actions = [
  { icon: Mail, title: "Generate Follow-up Mail", desc: "Click any row → Mail icon", tint: "text-signal-red bg-red-50", href: "/po-followups" },
  { icon: Clock, title: "View Mail History", desc: "Drafts and sent mails", tint: "text-blue-600 bg-blue-50", href: "/mail-history" },
  { icon: Edit3, title: "Email Master", desc: "Map supplier emails", tint: "text-emerald-600 bg-emerald-50", href: "/emails" },
  { icon: Bell, title: "Reports", desc: "Delays, supplier-wise", tint: "text-amber-600 bg-amber-50", href: "/reports" },
];

export default function ActionCenter() {
  return (
    <div className="card p-4">
      <div className="flex items-center gap-2 mb-3">
        <div className="h-7 w-7 rounded-md bg-red-50 grid place-content-center text-signal-red">⚡</div>
        <div className="font-semibold text-sm">Action Center</div>
      </div>
      <div className="space-y-2">
        {actions.map((a) => {
          const I = a.icon;
          return (
            <Link key={a.title} href={a.href} className="w-full flex items-start gap-3 p-3 rounded-md hover:bg-gray-50 text-left">
              <div className={"h-8 w-8 rounded-md grid place-content-center " + a.tint}><I size={14} /></div>
              <div>
                <div className="text-sm font-medium">{a.title}</div>
                <div className="text-xs text-brand-muted">{a.desc}</div>
              </div>
            </Link>
          );
        })}
      </div>
    </div>
  );
}

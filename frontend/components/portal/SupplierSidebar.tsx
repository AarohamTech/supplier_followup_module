"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutDashboard, FileSpreadsheet, Truck, X } from "lucide-react";

import { cn } from "@/lib/utils";

const items = [
  { href: "/portal", label: "Dashboard", icon: LayoutDashboard },
  { href: "/portal/pos", label: "My Purchase Orders", icon: FileSpreadsheet },
  { href: "/portal/asn", label: "ASN Portal", icon: Truck },
];

function isActive(path: string, href: string) {
  if (href === "/portal") return path === "/portal";
  return path === href || path.startsWith(`${href}/`);
}

function NavList({ onNavigate }: { onNavigate?: () => void }) {
  const path = usePathname();
  return (
    <nav className="space-y-1">
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

export default function SupplierSidebar({ open = false, onClose }: { open?: boolean; onClose?: () => void }) {
  return (
    <>
      <aside className="hidden w-60 shrink-0 border-r border-brand-border bg-white md:block">
        <div className="sticky top-[65px] h-[calc(100vh-65px)] overflow-y-auto p-3">
          <div className="mb-2 px-3 text-[10px] font-semibold uppercase tracking-wider text-brand-muted">
            Supplier Portal
          </div>
          <NavList />
        </div>
      </aside>

      {open && (
        <div className="fixed inset-0 z-40 md:hidden">
          <button type="button" className="absolute inset-0 bg-black/30" onClick={onClose} aria-label="Close navigation" />
          <aside className="animate-fade-in-up relative h-full w-[min(20rem,86vw)] border-r border-brand-border bg-white shadow-2xl">
            <div className="flex h-[65px] items-center justify-between border-b border-brand-border px-4">
              <div>
                <div className="text-sm font-semibold text-signal-red">Supplier Portal</div>
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

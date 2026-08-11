"use client";

import { useEffect, useState } from "react";
import { ChevronDown } from "lucide-react";

import { useAuth } from "@/lib/auth";
import { api } from "@/lib/api";
import type { CompanyBrief } from "@/lib/types";

/**
 * Active-company dropdown. Shared by the staff topbar and the employee portal
 * topbar — every internal account (staff of any role, and employee portal
 * logins) can move between the group's companies. Supplier portal accounts are
 * pinned to one company and never render this.
 *
 * Collapses to a plain label when only one company is active.
 */
export default function CompanySwitcher({ fallback = "H-Connect" }: { fallback?: string }) {
  const { company, switchCompany } = useAuth();
  const [companies, setCompanies] = useState<CompanyBrief[]>([]);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let alive = true;
    api
      .listCompanies()
      .then((rows) => alive && setCompanies(rows))
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, []);

  const current = company?.brand_name || company?.display_name || fallback;
  if (companies.length <= 1) {
    return <span className="hidden text-xs font-semibold text-brand-dark sm:inline">{current}</span>;
  }

  const pick = async (code: string) => {
    if (busy || code === company?.code) {
      setOpen(false);
      return;
    }
    setBusy(true);
    try {
      await switchCompany(code);
      if (typeof window !== "undefined") window.location.reload();
    } finally {
      setBusy(false);
      setOpen(false);
    }
  };

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        disabled={busy}
        className="inline-flex items-center gap-1 rounded-md border border-brand-border bg-card px-2.5 py-1.5 text-xs font-semibold text-brand-dark hover:bg-subtle"
      >
        {current}
        <ChevronDown size={14} className="text-brand-muted" />
      </button>
      {open && (
        <div className="absolute right-0 z-40 mt-1 w-44 overflow-hidden rounded-md border border-brand-border bg-card shadow-card animate-slide-down">
          {companies.map((c) => (
            <button
              key={c.code}
              type="button"
              onClick={() => pick(c.code)}
              className={
                c.code === company?.code
                  ? "block w-full px-3 py-2 text-left text-xs font-semibold text-signal-red bg-signal-red/10"
                  : "block w-full px-3 py-2 text-left text-xs text-brand-dark hover:bg-subtle"
              }
            >
              {c.display_name}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

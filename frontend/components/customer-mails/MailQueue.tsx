"use client";

import { memo, useState } from "react";
import { Search } from "lucide-react";
import type { CustomerMail } from "@/lib/types";
import { MailCard } from "./MailCard";
import { useRenderCount } from "./hooks";
import type { QueueTab } from "./shared";

interface MailQueueProps {
  tabs: QueueTab[];
  activeTab: string;
  counts: Record<string, number>;
  onTabChange: (key: string) => void;
  searchInput: string;
  onSearchChange: (value: string) => void;
  mails: CustomerMail[];
  selectedId: number | null;
  onSelect: (id: number) => void;
  loading: boolean;
}

const PAGE = 40;

/**
 * Left customer queue. The mail list is already grouped/filtered by the parent
 * (memoized), so this component just paints. Rendered items are capped and
 * extended with "Load more" to avoid a huge DOM when there are many mails.
 */
function MailQueueBase({
  tabs,
  activeTab,
  counts,
  onTabChange,
  searchInput,
  onSearchChange,
  mails,
  selectedId,
  onSelect,
  loading,
}: MailQueueProps) {
  useRenderCount("MailQueue");
  const [visible, setVisible] = useState(PAGE);
  const shown = mails.slice(0, visible);

  return (
    <div className="flex h-full flex-col">
      <div className="px-3 pt-3">
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-brand-muted" />
          <input
            value={searchInput}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="Search subject or sender…"
            className="w-full rounded-lg border border-brand-border bg-white py-2 pl-8 pr-3 text-sm outline-none focus:border-signal-red"
          />
        </div>
      </div>

      <div className="flex gap-1.5 overflow-x-auto px-3 py-2.5 scrollbar-thin">
        {tabs.map((t) => {
          const active = t.key === activeTab;
          return (
            <button
              key={t.key}
              type="button"
              onClick={() => onTabChange(t.key)}
              className={[
                "shrink-0 rounded-full border px-2.5 py-1 text-[11px] font-medium transition-colors",
                active
                  ? "border-signal-red bg-red-50 text-signal-red"
                  : "border-brand-border bg-white text-brand-muted hover:bg-gray-50",
              ].join(" ")}
            >
              {t.label} ({counts[t.key] ?? 0})
            </button>
          );
        })}
      </div>

      <div className="flex-1 space-y-2 overflow-y-auto px-3 pb-3">
        {loading && mails.length === 0 ? (
          <div className="py-8 text-center text-xs text-brand-muted">Loading…</div>
        ) : mails.length === 0 ? (
          <div className="py-8 text-center text-xs text-brand-muted">
            No mails in this queue.
          </div>
        ) : (
          <>
            {shown.map((mail) => (
              <MailCard
                key={mail.id}
                mail={mail}
                selected={mail.id === selectedId}
                onSelect={onSelect}
              />
            ))}
            {visible < mails.length && (
              <button
                type="button"
                onClick={() => setVisible((v) => v + PAGE)}
                className="w-full rounded-lg border border-brand-border bg-white py-2 text-xs text-brand-muted hover:bg-gray-50"
              >
                Load more ({mails.length - visible} remaining)
              </button>
            )}
          </>
        )}
      </div>
    </div>
  );
}

export const MailQueue = memo(MailQueueBase);

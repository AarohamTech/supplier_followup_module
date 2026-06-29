"use client";

import { memo, useState } from "react";
import { Inbox, Search } from "lucide-react";
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
  const activeLabel = tabs.find((tab) => tab.key === activeTab)?.label ?? "this queue";

  return (
    <div className="flex h-full flex-col">
      <div className="px-3 pt-3">
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
          <input
            value={searchInput}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="Search subject or sender…"
            aria-label="Search mails by subject or sender"
            className="w-full rounded-lg border border-brand-border bg-white py-2 pl-8 pr-3 text-sm outline-none focus:border-signal-red/40"
          />
        </div>
      </div>

      <div className="flex flex-wrap gap-1.5 border-b border-brand-border px-3 py-2.5">
        {tabs.map((t) => {
          const active = t.key === activeTab;
          return (
            <button
              key={t.key}
              type="button"
              onClick={() => onTabChange(t.key)}
              className={[
                "inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-semibold transition",
                active
                  ? "bg-red-50 text-signal-red ring-1 ring-signal-red/30"
                  : "text-brand-muted hover:bg-gray-100",
              ].join(" ")}
            >
              {t.label}
              <span
                className={`rounded-full px-1.5 text-[10px] font-bold ${
                  active ? "bg-signal-red text-white" : "bg-gray-100 text-brand-muted"
                }`}
              >
                {counts[t.key] ?? 0}
              </span>
            </button>
          );
        })}
      </div>

      <div className="flex-1 overflow-y-auto">
        {loading && mails.length === 0 ? (
          <div className="py-8 text-center text-xs text-brand-muted">Loading…</div>
        ) : mails.length === 0 ? (
          <div className="flex flex-col items-center px-6 py-10 text-center">
            <span className="mb-3 grid h-9 w-9 place-items-center rounded-lg bg-gray-100 text-gray-400">
              <Inbox className="h-4 w-4" />
            </span>
            <p className="text-xs font-medium text-brand-dark">No conversations in {activeLabel}</p>
            <p className="mt-1 text-[11px] leading-relaxed text-brand-muted">
              New customer messages will appear here automatically.
            </p>
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
                className="w-full border-b border-brand-border py-2.5 text-xs text-brand-muted hover:bg-gray-50"
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

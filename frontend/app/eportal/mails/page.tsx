"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Inbox, Loader2, Sparkles } from "lucide-react";

import { api } from "@/lib/api";
import type { CustomerMail, CustomerReply } from "@/lib/types";
import PageHeader from "@/components/layout/PageHeader";
import { MailQueue } from "@/components/customer-mails/MailQueue";
import { ConversationPanel, type LocalReply } from "@/components/customer-mails/ConversationPanel";
import { QUEUE_TABS } from "@/components/customer-mails/shared";
import { useDebouncedValue } from "@/components/customer-mails/hooks";

/** Employee view: customer mails linked to MY POs or allocated to me — a lean
 * version of the staff Customer Response Workspace (list + conversation +
 * reply + HI draft; no triage/task panels). */
export default function EmployeeMailsPage() {
  const [searchInput, setSearchInput] = useState("");
  const search = useDebouncedValue(searchInput, 350);
  const [activeTab, setActiveTab] = useState(QUEUE_TABS[0].key);
  // Same customer / non-customer split as the admin workspace, employee-scoped.
  const [mailScope, setMailScope] = useState<"customer" | "other">("customer");

  const [items, setItems] = useState<CustomerMail[]>([]);
  const [loadingList, setLoadingList] = useState(false);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [replies, setReplies] = useState<CustomerReply[]>([]);
  const [replyReloadKey, setReplyReloadKey] = useState(0);
  const [sending, setSending] = useState(false);
  const [seed, setSeed] = useState<{ text: string; nonce: number } | undefined>();
  const [drafting, setDrafting] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoadingList(true);
    api
      .eportalListMails({ search: search || undefined, limit: 200, scope: mailScope })
      .then((res) => {
        if (!cancelled) setItems(res.items);
      })
      .catch((err) => {
        if (!cancelled) setToast((err as Error).message);
      })
      .finally(() => {
        if (!cancelled) setLoadingList(false);
      });
    return () => {
      cancelled = true;
    };
  }, [search, mailScope]);

  useEffect(() => {
    setSelectedId((prev) =>
      prev != null && items.some((m) => m.id === prev) ? prev : items[0]?.id ?? null,
    );
  }, [items]);

  const selected = useMemo(
    () => items.find((m) => m.id === selectedId) ?? null,
    [items, selectedId],
  );

  const counts = useMemo(() => {
    const out: Record<string, number> = {};
    for (const tab of QUEUE_TABS) out[tab.key] = 0;
    for (const m of items) for (const tab of QUEUE_TABS) if (tab.match(m)) out[tab.key] += 1;
    return out;
  }, [items]);

  const filteredMails = useMemo(() => {
    const tab = QUEUE_TABS.find((t) => t.key === activeTab) ?? QUEUE_TABS[0];
    return items.filter(tab.match);
  }, [items, activeTab]);

  useEffect(() => {
    if (selectedId == null) {
      setReplies([]);
      return;
    }
    let cancelled = false;
    api
      .eportalGetMailReplies(selectedId)
      .then((res) => {
        if (!cancelled) setReplies(res);
      })
      .catch(() => {
        if (!cancelled) setReplies([]);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedId, replyReloadKey]);

  const handleSend = useCallback(
    (text: string) => {
      if (selectedId == null) return;
      const id = selectedId;
      setSending(true);
      api
        .eportalReplyToMail(id, text)
        .then((res) => {
          setReplyReloadKey((k) => k + 1);
          setItems((prev) => prev.map((m) => (m.id === id ? { ...m, status: res.mail_status } : m)));
          setToast(res.queued ? "Reply queued for send." : "Reply sent.");
        })
        .catch((err) => setToast((err as Error).message))
        .finally(() => setSending(false));
    },
    [selectedId],
  );

  const handleDraft = useCallback(() => {
    if (selectedId == null) return;
    setDrafting(true);
    api
      .eportalDraftMailReply(selectedId, true)
      .then((d) => {
        setSeed((prev) => ({ text: d.body, nonce: (prev?.nonce ?? 0) + 1 }));
        setToast("HI draft ready — review before sending.");
      })
      .catch((err) => setToast((err as Error).message))
      .finally(() => setDrafting(false));
  }, [selectedId]);

  useEffect(() => {
    if (!toast) return;
    const id = setTimeout(() => setToast(null), 2500);
    return () => clearTimeout(id);
  }, [toast]);

  const localReplies: LocalReply[] = useMemo(
    () =>
      replies.map((r) => ({
        id: r.id,
        text: r.body ?? "",
        at: r.sent_at ?? r.created_at,
        status: r.status,
      })),
    [replies],
  );

  return (
    <div className="flex h-[calc(100vh-128px)] flex-col">
      <PageHeader
        className="mb-3"
        title="My Customer Mails"
        description="Customer and other emails linked to your POs or allocated to you."
        icon={Inbox}
        tone="red"
        actions={
          <>
            {toast && <span className="rounded-md bg-brand-dark px-3 py-1.5 text-xs text-white">{toast}</span>}
            <div className="inline-flex shrink-0 rounded-lg border border-brand-border bg-subtle p-0.5 text-xs font-semibold">
              <button
                type="button"
                onClick={() => setMailScope("customer")}
                className={`rounded-md px-3 py-1.5 transition ${mailScope === "customer" ? "bg-card text-signal-red shadow-sm" : "text-brand-muted hover:text-brand-dark"}`}
              >
                Customers
              </button>
              <button
                type="button"
                onClick={() => setMailScope("other")}
                className={`rounded-md px-3 py-1.5 transition ${mailScope === "other" ? "bg-card text-signal-red shadow-sm" : "text-brand-muted hover:text-brand-dark"}`}
              >
                Other Mails
              </button>
            </div>
            {selected && (
              <button
                type="button"
                onClick={handleDraft}
                disabled={drafting}
                className="btn-outline text-xs"
                title="Draft a reply with Harmony Intelligent"
              >
                {drafting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
                HI Draft
              </button>
            )}
          </>
        }
      />

      <div className="flex min-h-0 flex-1 flex-col gap-3 md:flex-row">
        <aside className="max-h-[60vh] w-full shrink-0 overflow-hidden rounded-xl border border-brand-border bg-white shadow-sm md:max-h-none md:w-80">
          <MailQueue
            tabs={QUEUE_TABS}
            activeTab={activeTab}
            counts={counts}
            onTabChange={setActiveTab}
            searchInput={searchInput}
            onSearchChange={setSearchInput}
            mails={filteredMails}
            selectedId={selectedId}
            onSelect={setSelectedId}
            loading={loadingList}
          />
        </aside>

        <section className="flex min-w-0 flex-1 overflow-hidden rounded-xl border border-brand-border bg-white shadow-sm">
          {selected ? (
            <div className="flex h-full w-full flex-col">
              <ConversationPanel
                mail={selected}
                localReplies={localReplies}
                sending={sending}
                seed={seed}
                onSend={handleSend}
                onOpenContext={() => {}}
              />
            </div>
          ) : (
            <div className="flex h-full w-full items-center justify-center text-sm text-brand-muted">
              {loadingList ? "Loading…" : "No customer mails on your POs yet."}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

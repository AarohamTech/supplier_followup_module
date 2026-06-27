"use client";

import { useEffect, useRef, useState } from "react";
import { Loader2, MessagesSquare, SendHorizonal } from "lucide-react";

import { api } from "@/lib/api";
import type { EmployeePo, PortalMessage } from "@/lib/types";

function fmt(d?: string | null) {
  if (!d) return "";
  const x = new Date(d);
  return isNaN(x.getTime()) ? "" : x.toLocaleString();
}

export default function EmployeeCommunicationPage() {
  const [pos, setPos] = useState<EmployeePo[]>([]);
  const [active, setActive] = useState<string | null>(null);
  const [messages, setMessages] = useState<PortalMessage[]>([]);
  const [loadingPos, setLoadingPos] = useState(true);
  const [loadingMsgs, setLoadingMsgs] = useState(false);
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    (async () => {
      try {
        const p = await api.eportalPos();
        setPos(p.items);
        if (p.items[0]) setActive(p.items[0].supplier_po_no);
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setLoadingPos(false);
      }
    })();
  }, []);

  useEffect(() => {
    if (!active) return;
    setLoadingMsgs(true);
    api
      .eportalPoMessages(active)
      .then(setMessages)
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoadingMsgs(false));
  }, [active]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const send = async () => {
    const body = text.trim();
    if (!body || !active || sending) return;
    setSending(true);
    try {
      const m = await api.eportalSendMessage(active, body);
      setMessages((cur) => [...cur, m]);
      setText("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="page-stack">
      <div className="page-header">
        <div>
          <h1 className="page-title">Communication</h1>
          <p className="page-subtitle">Message suppliers on the purchase orders assigned to you.</p>
        </div>
      </div>

      {error && <div className="rounded-md bg-red-50 px-3 py-2 text-xs text-signal-red">{error}</div>}

      <div className="grid gap-4 md:grid-cols-[18rem_1fr]">
        {/* PO list */}
        <div className="card max-h-[70vh] overflow-y-auto p-2">
          {loadingPos ? (
            <div className="p-4 text-center text-sm text-brand-muted">
              <Loader2 className="mx-auto animate-spin" size={16} />
            </div>
          ) : pos.length === 0 ? (
            <div className="p-4 text-center text-sm text-brand-muted">No POs assigned.</div>
          ) : (
            pos.map((p) => (
              <button
                key={p.supplier_po_no}
                onClick={() => setActive(p.supplier_po_no)}
                className={`flex w-full flex-col rounded-md px-3 py-2 text-left text-sm ${
                  active === p.supplier_po_no ? "bg-red-50 text-signal-red" : "text-brand-dark hover:bg-slate-50"
                }`}
              >
                <span className="font-medium">{p.supplier_po_no}</span>
                <span className="truncate text-[11px] text-brand-muted">{p.supplier_name || "—"}</span>
              </button>
            ))
          )}
        </div>

        {/* Thread */}
        <div className="card flex max-h-[70vh] min-h-[24rem] flex-col">
          {!active ? (
            <div className="m-auto text-center text-sm text-brand-muted">
              <MessagesSquare className="mx-auto mb-2" size={20} />
              Select a PO to view its conversation.
            </div>
          ) : (
            <>
              <div className="border-b border-brand-border px-4 py-2 text-sm font-semibold text-brand-dark">PO {active}</div>
              <div className="flex-1 space-y-3 overflow-y-auto p-4">
                {loadingMsgs ? (
                  <div className="text-center text-sm text-brand-muted">
                    <Loader2 className="mx-auto animate-spin" size={16} />
                  </div>
                ) : messages.length === 0 ? (
                  <div className="text-center text-sm text-brand-muted">No messages yet. Start the conversation.</div>
                ) : (
                  messages.map((m) => (
                    <div key={m.id} className={`flex ${m.mine ? "justify-end" : "justify-start"}`}>
                      <div
                        className={`max-w-[80%] rounded-xl px-3 py-2 text-sm ${
                          m.mine ? "bg-brand-dark text-white" : "border border-brand-border bg-brand-surface text-brand-dark"
                        }`}
                      >
                        <div className="mb-0.5 text-[10px] opacity-70">
                          {m.author} · {fmt(m.at)}
                        </div>
                        <div className="whitespace-pre-wrap">{m.body}</div>
                      </div>
                    </div>
                  ))
                )}
                <div ref={endRef} />
              </div>
              <div className="flex items-end gap-2 border-t border-brand-border p-2">
                <textarea
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  rows={1}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      void send();
                    }
                  }}
                  placeholder="Type a message…  (Enter to send)"
                  className="max-h-32 min-h-[40px] flex-1 resize-none bg-transparent px-2 py-2 text-sm outline-none"
                />
                <button
                  onClick={() => void send()}
                  disabled={sending || !text.trim()}
                  className="inline-flex h-9 items-center gap-1.5 rounded-md bg-signal-red px-3 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
                >
                  {sending ? <Loader2 size={15} className="animate-spin" /> : <SendHorizonal size={15} />} Send
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

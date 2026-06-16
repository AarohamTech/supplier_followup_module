"use client";

import { useEffect, useRef, useState } from "react";
import { Bot, Loader2, SendHorizonal, Sparkles, User } from "lucide-react";

import { api } from "@/lib/api";
import type { ChatMessage } from "@/lib/types";

const SUGGESTIONS = [
  "Summarise what a RED signal means in this system.",
  "Draft a polite follow-up to a supplier who is 3 days late.",
  "What should I check before marking a PO dispatched?",
];

export default function AssistantPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.aiHealth().then((h) => setEnabled(h.enabled)).catch(() => setEnabled(false));
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, sending]);

  const send = async (text: string) => {
    const content = text.trim();
    if (!content || sending) return;
    setError(null);
    const next = [...messages, { role: "user" as const, content }];
    setMessages(next);
    setInput("");
    setSending(true);
    try {
      const res = await api.aiChat(next);
      setMessages((prev) => [...prev, { role: "assistant", content: res.reply }]);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSending(false);
    }
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void send(input);
    }
  };

  return (
    <div className="mx-auto flex h-[calc(100vh-128px)] max-w-3xl flex-col">
      {/* Header */}
      <div className="mb-3 flex items-center gap-2">
        <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-red-50 text-signal-red">
          <Sparkles size={16} />
        </span>
        <div>
          <h1 className="text-lg font-semibold text-brand-dark">AI Assistant</h1>
          <p className="text-xs text-brand-muted">
            Ask about follow-ups, POs, suppliers or draft a message. Agentic tools coming soon.
          </p>
        </div>
        {enabled === false && (
          <span className="ml-auto rounded-md bg-amber-50 px-2 py-1 text-xs text-amber-700">
            AI is disabled (set LLM_ENABLED)
          </span>
        )}
      </div>

      {/* Messages */}
      <div className="flex min-h-0 flex-1 flex-col overflow-y-auto rounded-xl border border-brand-border bg-white p-4">
        {messages.length === 0 ? (
          <div className="m-auto max-w-md text-center">
            <Bot className="mx-auto mb-3 h-8 w-8 text-brand-muted" />
            <p className="mb-4 text-sm text-brand-muted">Start a conversation. Try:</p>
            <div className="space-y-2">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => void send(s)}
                  className="block w-full rounded-lg border border-brand-border px-3 py-2 text-left text-sm text-brand-dark hover:bg-gray-50"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            {messages.map((m, i) => (
              <div key={i} className={`flex gap-2.5 ${m.role === "user" ? "flex-row-reverse" : ""}`}>
                <span
                  className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-white ${
                    m.role === "user" ? "bg-brand-dark" : "bg-signal-red"
                  }`}
                >
                  {m.role === "user" ? <User size={14} /> : <Bot size={14} />}
                </span>
                <div
                  className={`max-w-[80%] whitespace-pre-wrap rounded-xl px-3.5 py-2.5 text-sm leading-relaxed ${
                    m.role === "user"
                      ? "bg-brand-dark text-white"
                      : "border border-brand-border bg-brand-surface text-brand-dark"
                  }`}
                >
                  {m.content}
                </div>
              </div>
            ))}
            {sending && (
              <div className="flex items-center gap-2 text-sm text-brand-muted">
                <Bot size={14} className="text-signal-red" />
                <Loader2 size={14} className="animate-spin" /> Thinking…
              </div>
            )}
            <div ref={endRef} />
          </div>
        )}
      </div>

      {error && (
        <div className="mt-2 rounded-md bg-red-50 px-3 py-2 text-xs text-signal-red">{error}</div>
      )}

      {/* Composer */}
      <div className="mt-3 flex items-end gap-2 rounded-xl border border-brand-border bg-white p-2">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          rows={1}
          placeholder="Ask the assistant…  (Enter to send, Shift+Enter for a new line)"
          className="max-h-32 min-h-[40px] flex-1 resize-none bg-transparent px-2 py-2 text-sm outline-none"
        />
        <button
          onClick={() => void send(input)}
          disabled={sending || !input.trim()}
          className="inline-flex h-9 items-center gap-1.5 rounded-md bg-signal-red px-3 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
        >
          {sending ? <Loader2 size={15} className="animate-spin" /> : <SendHorizonal size={15} />}
          Send
        </button>
      </div>
    </div>
  );
}

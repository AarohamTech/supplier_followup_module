"use client";

import { useEffect, useRef, useState } from "react";
import { Bot, Loader2, SendHorizonal, Sparkles, User, Wrench } from "lucide-react";

import { api } from "@/lib/api";
import type { ChatMessage, AiToolUse } from "@/lib/types";
import PageHeader from "@/components/layout/PageHeader";
import AiThinkingIndicator from "@/components/AiThinkingIndicator";

type UiMessage = ChatMessage & { tools?: AiToolUse[] };

const SUGGESTIONS = [
  "Summarise our RED signals right now.",
  "Which purchase orders are most at risk of delay?",
  "How have we handled late supplier deliveries before?",
];

export default function AssistantPage() {
  const [messages, setMessages] = useState<UiMessage[]>([]);
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
    const next: UiMessage[] = [...messages, { role: "user" as const, content }];
    setMessages(next);
    setInput("");
    setSending(true);
    try {
      // Send only {role, content} to the API; tools are display-only metadata.
      const res = await api.aiChat(next.map((m) => ({ role: m.role, content: m.content })));
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: res.reply, tools: res.tools_used },
      ]);
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
      <PageHeader
        className="mb-3"
        title="Harmony Intelligent Assistant"
        description="Agentic assistant that reads live POs, suppliers, mail threads and past-mail memory."
        icon={Sparkles}
        actions={
          enabled === false && (
            <span className="rounded-md bg-amber-50 px-2 py-1 text-xs text-amber-700">
              Harmony Intelligent is disabled (set LLM_ENABLED)
            </span>
          )
        }
      />

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
                <div className={`max-w-[80%] ${m.role === "user" ? "items-end" : ""}`}>
                  <div
                    className={`whitespace-pre-wrap rounded-xl px-3.5 py-2.5 text-sm leading-relaxed ${
                      m.role === "user"
                        ? "bg-brand-dark text-white"
                        : "border border-brand-border bg-brand-surface text-brand-dark"
                    }`}
                  >
                    {m.content}
                  </div>
                  {m.tools && m.tools.length > 0 && (
                    <div className="mt-1.5 flex flex-wrap gap-1">
                      {m.tools.map((t, ti) => (
                        <span
                          key={ti}
                          className="inline-flex items-center gap-1 rounded-full bg-red-50 px-2 py-0.5 text-[11px] text-signal-red"
                          title={JSON.stringify(t.args)}
                        >
                          <Wrench size={10} /> {t.name}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}
            {sending && <AiThinkingIndicator />}
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

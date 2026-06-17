"use client";

import { memo, useEffect, useRef, useState } from "react";
import { Bold, Image as ImageIcon, Paperclip, Send } from "lucide-react";
import { useDebouncedCallback, useRenderCount } from "./hooks";

interface ReplyComposerProps {
  mailId: number;
  recipientName: string;
  /** Increment `nonce` to push suggested text into the composer. */
  seed?: { text: string; nonce: number };
  sending: boolean;
  onSend: (text: string) => void;
}

function draftKey(mailId: number) {
  return `cm-draft-${mailId}`;
}

/**
 * Reply text is kept LOCAL to this component. Typing never re-renders the
 * parent workspace, never hits the API, and autosave to localStorage is
 * debounced. This is the single most important fix for typing lag.
 */
function ReplyComposerBase({
  mailId,
  recipientName,
  seed,
  sending,
  onSend,
}: ReplyComposerProps) {
  useRenderCount("ReplyComposer");
  const [text, setText] = useState("");
  const lastSeedNonce = useRef<number | null>(null);

  // Load any saved draft when switching mails.
  useEffect(() => {
    let saved = "";
    try {
      saved = window.localStorage.getItem(draftKey(mailId)) || "";
    } catch {
      saved = "";
    }
    setText(saved);
  }, [mailId]);

  // Apply a suggested reply only when the user clicks "Use" (nonce changes).
  useEffect(() => {
    if (seed && seed.nonce !== lastSeedNonce.current) {
      lastSeedNonce.current = seed.nonce;
      setText(seed.text);
    }
  }, [seed]);

  const saveDraft = useDebouncedCallback((value: string) => {
    try {
      if (value) window.localStorage.setItem(draftKey(mailId), value);
      else window.localStorage.removeItem(draftKey(mailId));
    } catch {
      /* ignore quota / unavailable storage */
    }
  }, 600);

  function handleChange(value: string) {
    setText(value);
    saveDraft(value);
  }

  function handleSend() {
    const trimmed = text.trim();
    if (!trimmed || sending) return;
    onSend(trimmed);
    setText("");
    try {
      window.localStorage.removeItem(draftKey(mailId));
    } catch {
      /* ignore */
    }
  }

  return (
    <div className="border-t border-brand-border bg-white p-3">
      <textarea
        value={text}
        onChange={(e) => handleChange(e.target.value)}
        placeholder={`Type your response to ${recipientName}…`}
        rows={3}
        className="w-full resize-none rounded-lg border border-brand-border bg-brand-surface px-3 py-2 text-sm outline-none focus:border-signal-red"
      />
      <div className="mt-2 flex items-center justify-between">
        <div className="flex items-center gap-1 text-brand-muted">
          <button type="button" className="rounded p-1.5 hover:bg-gray-100" title="Bold">
            <Bold className="h-4 w-4" />
          </button>
          <button type="button" className="rounded p-1.5 hover:bg-gray-100" title="Attach">
            <Paperclip className="h-4 w-4" />
          </button>
          <button type="button" className="rounded p-1.5 hover:bg-gray-100" title="Image">
            <ImageIcon className="h-4 w-4" />
          </button>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[11px] text-brand-muted">Draft autosaved</span>
          <button
            type="button"
            onClick={handleSend}
            disabled={sending || !text.trim()}
            className="inline-flex items-center gap-1.5 rounded-md bg-signal-red px-3.5 py-1.5 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
          >
            {sending ? "Sending…" : "Send Response"}
            <Send className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
}

export const ReplyComposer = memo(ReplyComposerBase);

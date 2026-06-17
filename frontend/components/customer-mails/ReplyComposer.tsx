"use client";

import { memo, useEffect, useRef, useState } from "react";
import { Bold, Image as ImageIcon, Loader2, Paperclip, Send, Sparkles } from "lucide-react";
import { useDebouncedCallback, useRenderCount } from "./hooks";

interface ReplyComposerProps {
  mailId: number;
  recipientName: string;
  /** Increment `nonce` to push suggested text into the composer. */
  seed?: { text: string; nonce: number };
  sending: boolean;
  onSend: (text: string) => void;
  /** Generate a reply with AI using the current text as the instruction/prompt;
   *  returns the generated body to drop into the composer. */
  onAiGenerate?: (instruction: string) => Promise<string>;
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
  onAiGenerate,
}: ReplyComposerProps) {
  useRenderCount("ReplyComposer");
  const [text, setText] = useState("");
  const [generating, setGenerating] = useState(false);
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

  async function handleAiGenerate() {
    if (!onAiGenerate || generating || sending) return;
    setGenerating(true);
    try {
      // Whatever the agent typed becomes the instruction/prompt (may be empty).
      const out = await onAiGenerate(text.trim());
      if (out) {
        setText(out);
        saveDraft(out);
      }
    } finally {
      setGenerating(false);
    }
  }

  return (
    <div className="mail-composer p-3">
      <textarea
        value={text}
        onChange={(e) => handleChange(e.target.value)}
        placeholder={`Type your response to ${recipientName}`}
        rows={3}
        className="w-full resize-none border border-brand-border bg-white px-3 py-2 text-sm outline-none"
      />
      <div className="mt-2 flex items-center justify-between">
        <div className="flex items-center gap-1 text-brand-muted">
          <button type="button" className="grid h-8 w-8 place-items-center rounded-lg hover:bg-gray-100" title="Bold">
            <Bold className="h-4 w-4" />
          </button>
          <button type="button" className="grid h-8 w-8 place-items-center rounded-lg hover:bg-gray-100" title="Attach">
            <Paperclip className="h-4 w-4" />
          </button>
          <button type="button" className="grid h-8 w-8 place-items-center rounded-lg hover:bg-gray-100" title="Image">
            <ImageIcon className="h-4 w-4" />
          </button>
        </div>
        <div className="flex items-center gap-2">
          <span className="hidden text-[11px] text-brand-muted sm:inline">Draft autosaved</span>
          {onAiGenerate && (
            <button
              type="button"
              onClick={handleAiGenerate}
              disabled={generating || sending}
              title="Generate a reply with AI. Type notes/instructions first (or leave blank) - the AI uses them as the prompt."
              className="inline-flex min-h-9 items-center gap-1.5 rounded-lg border border-violet-300 bg-white px-3 py-1.5 text-sm font-medium text-violet-700 hover:bg-violet-50 disabled:opacity-50"
            >
              {generating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
              {generating ? "Generating..." : "AI Generate"}
            </button>
          )}
          <button
            type="button"
            onClick={handleSend}
            disabled={sending || !text.trim()}
            className="btn-primary min-h-9 px-3.5 py-1.5 disabled:opacity-50"
          >
            {sending ? "Sending..." : "Send Response"}
            <Send className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
}

export const ReplyComposer = memo(ReplyComposerBase);

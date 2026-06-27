"use client";

import { useEffect, useRef, useState } from "react";
import { Bot, Loader2 } from "lucide-react";

// Cycles through descriptive steps so the user sees the agent actively working
// during a long (multi-tool) run, instead of a static "Thinking…". The elapsed
// seconds keep ticking even on the final step so it never looks stalled.
const DEFAULT_STEPS = [
  "Reading your question…",
  "Searching live POs & shipments…",
  "Reviewing supplier history & past mails…",
  "Cross-checking the data…",
  "Composing the answer…",
];

export default function AiThinkingIndicator({ steps = DEFAULT_STEPS }: { steps?: string[] }) {
  const [idx, setIdx] = useState(0);
  const [secs, setSecs] = useState(0);
  const start = useRef(Date.now());

  useEffect(() => {
    const step = setInterval(() => setIdx((p) => Math.min(p + 1, steps.length - 1)), 2200);
    const tick = setInterval(() => setSecs(Math.round((Date.now() - start.current) / 1000)), 1000);
    return () => {
      clearInterval(step);
      clearInterval(tick);
    };
  }, [steps.length]);

  return (
    <div className="flex items-center gap-2 text-sm text-brand-muted" aria-live="polite">
      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-signal-red text-white">
        <Bot size={14} />
      </span>
      <Loader2 size={14} className="animate-spin text-signal-red" />
      <span className="animate-pulse">{steps[idx]}</span>
      {secs >= 3 && <span className="text-[11px] text-brand-muted/70">({secs}s)</span>}
    </div>
  );
}

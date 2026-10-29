"use client";

import { useCallback, useMemo, useRef, useState } from "react";

/**
 * Shows an email's HTML the way it looked in the mailbox, isolated in a
 * sandboxed iframe: no scripts run (no `allow-scripts`), and the mail's CSS
 * can't leak into the app. `allow-same-origin` only lets us measure the
 * content height; links open in a new tab.
 */
export function EmailHtmlView({ html, maxHeight = 720 }: { html: string; maxHeight?: number }) {
  const ref = useRef<HTMLIFrameElement>(null);
  const [height, setHeight] = useState(160);
  const [expanded, setExpanded] = useState(false);

  const srcDoc = useMemo(
    () =>
      '<!doctype html><html><head><meta charset="utf-8"><base target="_blank">' +
      "<style>html,body{margin:0;padding:8px;background:#fff;color:#1f2937;" +
      "font-family:Arial,Helvetica,sans-serif;font-size:14px;overflow-wrap:anywhere}" +
      "img{max-width:100%;height:auto}table{max-width:100%}</style></head><body>" +
      html +
      "</body></html>",
    [html],
  );

  const measure = useCallback(() => {
    const doc = ref.current?.contentDocument;
    if (!doc?.body) return;
    setHeight(Math.max(60, doc.documentElement.scrollHeight, doc.body.scrollHeight));
  }, []);

  const clipped = !expanded && height > maxHeight;
  return (
    <div className="overflow-hidden rounded-lg border border-brand-border bg-white">
      <iframe
        ref={ref}
        title="Email"
        sandbox="allow-same-origin allow-popups allow-popups-to-escape-sandbox"
        srcDoc={srcDoc}
        onLoad={measure}
        className="block w-full"
        style={{ height: clipped ? maxHeight : height, border: 0 }}
      />
      {height > maxHeight && (
        <button
          type="button"
          className="w-full border-t border-brand-border bg-subtle py-1 text-[11px] font-medium text-brand-muted hover:text-brand-dark"
          onClick={() => setExpanded((v) => !v)}
        >
          {expanded ? "Show less" : "Show full email"}
        </button>
      )}
    </div>
  );
}

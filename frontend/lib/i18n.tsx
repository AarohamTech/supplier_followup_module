"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { MR } from "./i18n-mr";

/**
 * Minimal UI translation: English source strings are the keys, so an untranslated
 * string simply renders in English. Marathi covers the employee portal, the
 * Task Manager and the Supplier Portal (topbar + menu so far, page by page);
 * other pages stay English until their strings are added to MR.
 *
 * `t("Due {date}", { date })` fills `{name}` placeholders after lookup.
 */
export type Lang = "en" | "mr";

const STORAGE_KEY = "hc-lang";

type LangState = { lang: Lang; setLang: (l: Lang) => void };

const LangContext = createContext<LangState>({ lang: "en", setLang: () => {} });

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  // Start in English on both server and client, then adopt the saved choice
  // after mount, so the first client render matches the server HTML.
  const [lang, setLangState] = useState<Lang>("en");

  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(STORAGE_KEY);
      if (saved === "mr" || saved === "en") setLangState(saved);
    } catch {
      /* storage blocked — stay English */
    }
  }, []);

  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  const setLang = useCallback((l: Lang) => {
    setLangState(l);
    try {
      window.localStorage.setItem(STORAGE_KEY, l);
    } catch {
      /* per-device convenience only */
    }
  }, []);

  const value = useMemo(() => ({ lang, setLang }), [lang, setLang]);
  return <LangContext.Provider value={value}>{children}</LangContext.Provider>;
}

function fill(text: string, vars?: Record<string, string | number | null | undefined>) {
  if (!vars) return text;
  return text.replace(/\{(\w+)\}/g, (m, k) => (vars[k] === undefined || vars[k] === null ? m : String(vars[k])));
}

export function translate(lang: Lang, text: string, vars?: Record<string, string | number | null | undefined>) {
  const base = lang === "mr" ? MR[text] ?? text : text;
  return fill(base, vars);
}

export function useT() {
  const { lang, setLang } = useContext(LangContext);
  const t = useCallback(
    (text: string, vars?: Record<string, string | number | null | undefined>) => translate(lang, text, vars),
    [lang],
  );
  return { t, lang, setLang };
}

// ── Error messages ──────────────────────────────────────────────────────────
// API errors reach the UI as "<status> <statusText> <detail>" (lib/api.ts);
// statusText is empty over HTTP/2, so it's optional when parsing.
const STATUS_TEXTS = [
  "Bad Request", "Unauthorized", "Forbidden", "Not Found", "Method Not Allowed", "Conflict",
  "Payload Too Large", "Content Too Large", "Unprocessable Entity", "Unprocessable Content",
  "Too Many Requests", "Internal Server Error", "Bad Gateway", "Service Unavailable", "Gateway Timeout",
];

/** Plain-language fallback per HTTP status, used when the server's detail has no translation. */
const STATUS_MESSAGES: Record<number, string> = {
  400: "The request was not accepted.",
  401: "Please sign in again.",
  403: "You do not have permission for this.",
  404: "Not found.",
  409: "This conflicts with a recent change. Refresh and try again.",
  413: "The file is too large.",
  422: "Some details are missing or not valid.",
  429: "Too many requests. Please wait a moment and try again.",
  500: "Something went wrong on the server. Please try again.",
  502: "The server could not complete the request. Please try again.",
  503: "This service is not available right now. Please try again later.",
  504: "The server took too long to respond. Please try again.",
};

/** Browser messages for a request that never reached the server. */
const NETWORK_ERRORS = new Set(["Failed to fetch", "NetworkError when attempting to fetch resource.", "Load failed"]);

/** Server messages that carry a value: pattern → dictionary key (+ the value's placeholder name). */
const ERROR_PATTERNS: [RegExp, string, string?][] = [
  [/^File too large \(max (\d+) MB\)\.$/, "File too large (max {n} MB).", "n"],
  [/^Unknown stage '(.+)'$/, "Unknown stage '{stage}'", "stage"],
  [/^CRM PO PDF fetch failed \((\d+)\)$/, "Could not download the PO PDF from the CRM ({code}).", "code"],
  [/^transport_mode must be one of /, "Choose a valid transport mode."],
  [/^AI is disabled\b/, "Harmony Intelligent is currently unavailable."],
  [/^Assistant request failed: /, "The assistant could not answer right now. Please try again."],
];

function knownError(text: string): string | null {
  if (NETWORK_ERRORS.has(text)) return MR["Could not reach the server. Check your connection and try again."] ?? null;
  if (MR[text]) return MR[text];
  for (const [re, key, name] of ERROR_PATTERNS) {
    const m = text.match(re);
    if (m && MR[key]) return fill(MR[key], name ? { [name]: m[1] } : undefined);
  }
  return null;
}

/**
 * An error message in the chosen language. English returns it unchanged.
 * Marathi translates known server/browser messages; for an unknown server
 * detail it shows a Marathi line for the HTTP status and keeps the original
 * detail in brackets, so nothing the buyer may need to see is lost. Messages
 * the UI already translated pass through untouched.
 */
export function translateError(lang: Lang, message?: string | null): string {
  const msg = (message ?? "").trim();
  if (lang !== "mr" || !msg) return msg;
  const direct = knownError(msg);
  if (direct) return direct;

  const m = msg.match(/^(\d{3})\s+([\s\S]*)$/);
  if (!m) return msg;
  const status = Number(m[1]);
  let detail = m[2].trim();
  const statusText = STATUS_TEXTS.find((s) => detail === s || detail.startsWith(`${s} `));
  if (statusText) detail = detail.slice(statusText.length).trim();
  if (detail === "[object Object]") detail = ""; // validation error lists aren't readable text

  if (detail) {
    const known = knownError(detail);
    if (known) return known;
  }
  const generic = STATUS_MESSAGES[status]
    ? translate(lang, STATUS_MESSAGES[status])
    : translate(lang, "Request failed ({code}).", { code: status });
  return detail ? `${generic} (${detail})` : generic;
}

/** `errorText(message)` — translateError bound to the chosen language. */
export function useErrorText() {
  const { lang } = useContext(LangContext);
  return useCallback((message?: string | null) => translateError(lang, message), [lang]);
}

/** EN / मराठी segmented switch for a topbar or page header. */
export function LanguageToggle({ className }: { className?: string }) {
  const { lang, setLang, t } = useT();
  return (
    <div
      className={`inline-flex shrink-0 overflow-hidden rounded-md border border-brand-border text-xs font-semibold ${className ?? ""}`}
      role="group"
      aria-label={t("Language")}
    >
      {(
        [
          ["en", "EN"],
          ["mr", "मराठी"],
        ] as const
      ).map(([code, label]) => (
        <button
          key={code}
          type="button"
          onClick={() => setLang(code)}
          aria-pressed={lang === code}
          className={`px-2 py-1 transition ${
            lang === code ? "bg-ink text-white" : "bg-card text-brand-muted hover:text-brand-dark"
          }`}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

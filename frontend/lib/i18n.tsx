"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { MR } from "./i18n-mr";

/**
 * Minimal UI translation: English source strings are the keys, so an untranslated
 * string simply renders in English. Marathi covers the employee portal and the
 * Task Manager; other pages stay English until their strings are added to MR.
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

/** EN / मराठी segmented switch for a topbar or page header. */
export function LanguageToggle({ className }: { className?: string }) {
  const { lang, setLang } = useT();
  return (
    <div
      className={`inline-flex shrink-0 overflow-hidden rounded-md border border-brand-border text-xs font-semibold ${className ?? ""}`}
      role="group"
      aria-label="Language"
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

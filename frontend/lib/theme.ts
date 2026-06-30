"use client";

import { create } from "zustand";

export type Theme = "light" | "dark" | "system";

const STORAGE_KEY = "theme";

function systemPrefersDark(): boolean {
  if (typeof window === "undefined") return false;
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

function resolveDark(theme: Theme): boolean {
  return theme === "dark" || (theme === "system" && systemPrefersDark());
}

/** Apply the resolved theme by toggling `.dark` on <html>. */
function applyTheme(theme: Theme): void {
  if (typeof document === "undefined") return;
  document.documentElement.classList.toggle("dark", resolveDark(theme));
}

interface ThemeState {
  theme: Theme;
  /** Whether the dark palette is currently active (resolved from theme + OS). */
  isDark: boolean;
  setTheme: (theme: Theme) => void;
  /** Toggle between explicit light and dark (drops back from "system"). */
  toggle: () => void;
  /** Sync store from localStorage + start watching OS preference. Call once. */
  init: () => void;
}

export const useTheme = create<ThemeState>((set, get) => ({
  theme: "system",
  isDark: false,
  setTheme: (theme) => {
    try {
      localStorage.setItem(STORAGE_KEY, theme);
    } catch {
      /* private mode / storage disabled — non-fatal */
    }
    applyTheme(theme);
    set({ theme, isDark: resolveDark(theme) });
  },
  toggle: () => get().setTheme(get().isDark ? "light" : "dark"),
  init: () => {
    let saved: Theme = "system";
    try {
      saved = (localStorage.getItem(STORAGE_KEY) as Theme) || "system";
    } catch {
      /* ignore */
    }
    applyTheme(saved);
    set({ theme: saved, isDark: resolveDark(saved) });
    // Track OS changes only while following the system preference.
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    mq.addEventListener("change", () => {
      if (get().theme === "system") {
        applyTheme("system");
        set({ isDark: resolveDark("system") });
      }
    });
  },
}));

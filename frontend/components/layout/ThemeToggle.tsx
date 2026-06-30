"use client";

import { Moon, Sun } from "lucide-react";
import { useTheme } from "@/lib/theme";

/** Minimalist light/dark switch for the portal topbars. */
export default function ThemeToggle({ className = "" }: { className?: string }) {
  const isDark = useTheme((s) => s.isDark);
  const toggle = useTheme((s) => s.toggle);
  return (
    <button
      type="button"
      onClick={toggle}
      title={isDark ? "Switch to light mode" : "Switch to dark mode"}
      aria-label="Toggle dark mode"
      className={`rounded-md p-2 text-brand-muted hover:bg-subtle hover:text-brand-dark ${className}`}
    >
      {isDark ? <Sun size={18} /> : <Moon size={18} />}
    </button>
  );
}

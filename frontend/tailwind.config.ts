import type { Config } from "tailwindcss";

// Colors are driven by CSS variables (see globals.css :root / .dark) so the whole
// app re-themes by toggling one class on <html>. The `rgb(var(--x) / <alpha>)`
// form keeps Tailwind opacity modifiers (e.g. bg-brand-red/10) working.
const v = (name: string) => `rgb(var(${name}) / <alpha-value>)`;

export default {
  darkMode: "class",
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          red: v("--brand-red"),
          dark: v("--brand-dark"),     // primary text (flips light in dark)
          muted: v("--brand-muted"),   // secondary text
          surface: v("--brand-surface"), // page background
          border: v("--brand-border"),
        },
        signal: {
          green: v("--signal-green"),
          yellow: v("--signal-yellow"),
          red: v("--signal-red"),
          black: v("--signal-black"),
        },
        // Theme-aware surfaces for the hardcoded-color sweep.
        card: v("--card"),       // elevated/card background (replaces bg-white)
        subtle: v("--subtle"),   // subtle/hover background (replaces bg-gray-50/100)
        ink: v("--ink"),         // always-dark background (former bg-brand-dark uses)
      },
      boxShadow: {
        card: "0 1px 2px rgba(16,24,40,.04), 0 1px 3px rgba(16,24,40,.06)",
      },
    },
  },
  plugins: [],
} satisfies Config;

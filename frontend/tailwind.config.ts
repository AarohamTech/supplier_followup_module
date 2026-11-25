import type { Config } from "tailwindcss";
import plugin from "tailwindcss/plugin";
import palette from "tailwindcss/colors";

// Dark-mode remap for the light pastel tints used across the app
// (bg-emerald-50, text-amber-700, border-rose-200 …). Most of those classes were
// written for light mode only, so in dark mode they rendered as glaring pastel
// blocks with dark text. This turns them into translucent tints with light text.
// Explicit `dark:` variants still win (same specificity, emitted later).
const TINTS = ["emerald", "green", "amber", "yellow", "orange", "blue", "sky", "indigo",
  "violet", "purple", "rose", "pink", "teal", "cyan", "slate", "lime", "fuchsia"] as const;
const hexA = (hex: string, a: number) => {
  const n = parseInt(hex.slice(1), 16);
  return `rgb(${(n >> 16) & 255} ${(n >> 8) & 255} ${n & 255} / ${a})`;
};
const darkTints = plugin(({ addBase }) => {
  const rules: Record<string, Record<string, string>> = {};
  const add = (sel: string, decl: Record<string, string>) => {
    rules[`.dark .${sel}`] = decl;
  };
  const shades = palette as unknown as Record<string, Record<string, string>>;
  for (const c of TINTS) {
    const p = shades[c];
    add(`bg-${c}-50`, { "background-color": hexA(p["500"], 0.1) });
    add(`bg-${c}-100`, { "background-color": hexA(p["500"], 0.16) });
    add(`hover\\:bg-${c}-50:hover`, { "background-color": hexA(p["500"], 0.14) });
    add(`hover\\:bg-${c}-100:hover`, { "background-color": hexA(p["500"], 0.2) });
    for (const s of ["100", "200", "300"]) add(`border-${c}-${s}`, { "border-color": hexA(p["500"], 0.3) });
    for (const s of ["600", "700", "800", "900"]) add(`text-${c}-${s}`, { color: p["300"] });
  }
  // red-* are CSS variables (company 101 re-points them to blue), so stay on vars.
  add("bg-red-50", { "background-color": "rgb(var(--red-500) / 0.1)" });
  add("bg-red-100", { "background-color": "rgb(var(--red-500) / 0.16)" });
  add("hover\\:bg-red-50:hover", { "background-color": "rgb(var(--red-500) / 0.14)" });
  add("hover\\:bg-red-100:hover", { "background-color": "rgb(var(--red-500) / 0.2)" });
  for (const s of ["100", "200", "300"]) add(`border-red-${s}`, { "border-color": "rgb(var(--red-500) / 0.3)" });
  for (const s of ["700", "800", "900"]) add(`text-red-${s}`, { color: "rgb(var(--red-300))" });
  addBase(rules);
});

// Colors are driven by CSS variables (see globals.css :root / .dark) so the whole
// app re-themes by toggling one class on <html>. The `rgb(var(--x) / <alpha>)`
// form keeps Tailwind opacity modifiers (e.g. bg-brand-red/10) working.
const v = (name: string) => `rgb(var(${name}) / <alpha-value>)`;

export default {
  darkMode: "class",
  // Only apply :hover styles on devices that really hover. On touch screens a
  // tap otherwise leaves the button stuck in its hover colour.
  future: { hoverOnlyWhenSupported: true },
  // NOTE: lib/** must be scanned too — signal/ASN colour classes live in
  // lib/format.ts (signalClass, signalDot) and lib/asn.ts (STAGE_META, signalBadge).
  // Leaving it out purges those dynamic classes, so pills/badges render uncoloured.
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
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
        red: {
          50: v("--red-50"),
          100: v("--red-100"),
          200: v("--red-200"),
          300: v("--red-300"),
          400: v("--red-400"),
          500: v("--red-500"),
          600: v("--red-600"),
          700: v("--red-700"),
          800: v("--red-800"),
          900: v("--red-900"),
          950: v("--red-950"),
        },
        // Theme-aware surfaces for the hardcoded-color sweep.
        card: v("--card"),       // elevated/card background (replaces bg-white)
        subtle: v("--subtle"),   // subtle/hover background (replaces bg-gray-50/100)
        ink: v("--ink"),         // always-dark background (former bg-brand-dark uses)
      },
      transitionTimingFunction: {
        out: "cubic-bezier(0.23, 1, 0.32, 1)",
        "in-out": "cubic-bezier(0.77, 0, 0.175, 1)",
        drawer: "cubic-bezier(0.32, 0.72, 0, 1)",
      },
      boxShadow: {
        card: "0 1px 2px rgba(16,24,40,.04), 0 1px 3px rgba(16,24,40,.06)",
      },
    },
  },
  plugins: [darkTints],
} satisfies Config;

import type { Config } from "tailwindcss";

export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          red: "#E11D2E",
          dark: "#111827",
          muted: "#6B7280",
          surface: "#F7F8FA",
          border: "#E5E7EB",
        },
        signal: {
          green: "#16A34A",
          yellow: "#F59E0B",
          red: "#E11D2E",
          black: "#111827",
        },
      },
      boxShadow: {
        card: "0 1px 2px rgba(16,24,40,.04), 0 1px 3px rgba(16,24,40,.06)",
      },
    },
  },
  plugins: [],
} satisfies Config;

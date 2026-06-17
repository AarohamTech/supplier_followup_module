import type { Config } from "tailwindcss";

export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          red: "#D81F2F",
          fg: "#101418",
          dark: "#101418",
          muted: "#66717A",
          surface: "#EEF3F2",
          border: "#DFE5E7",
        },
        signal: {
          green: "#14845F",
          yellow: "#B7791F",
          red: "#D81F2F",
          black: "#101418",
        },
      },
      boxShadow: {
        card: "0 18px 44px rgba(30,42,49,.08), 0 1px 2px rgba(16,20,24,.05)",
      },
    },
  },
  plugins: [],
} satisfies Config;

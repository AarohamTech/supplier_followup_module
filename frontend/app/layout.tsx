import "./globals.css";
import type { Metadata } from "next";
import { AuthProvider } from "@/lib/auth";
import AppShell from "@/components/layout/AppShell";
import ThemeInit from "@/components/layout/ThemeInit";

export const metadata: Metadata = {
  title: "Supplier Follow-up Agent",
  description: "PO-wise and Material-wise Automated Follow-up System",
};

// Set <html class="dark"> before first paint so there's no flash of the wrong
// theme. Reads the same localStorage key + OS preference the theme store uses.
const noFlashTheme = `(function(){try{var t=localStorage.getItem('theme')||'system';var d=t==='dark'||(t==='system'&&window.matchMedia('(prefers-color-scheme: dark)').matches);if(d)document.documentElement.classList.add('dark');}catch(e){}})();`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: noFlashTheme }} />
      </head>
      <body>
        <ThemeInit />
        <AuthProvider>
          <AppShell>{children}</AppShell>
        </AuthProvider>
      </body>
    </html>
  );
}

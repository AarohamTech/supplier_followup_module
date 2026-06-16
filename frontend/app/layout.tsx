import "./globals.css";
import type { Metadata } from "next";
import { AuthProvider } from "@/lib/auth";
import AppShell from "@/components/layout/AppShell";

export const metadata: Metadata = {
  title: "Supplier Follow-up Agent",
  description: "PO-wise and Material-wise Automated Follow-up System",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <AuthProvider>
          <AppShell>{children}</AppShell>
        </AuthProvider>
      </body>
    </html>
  );
}

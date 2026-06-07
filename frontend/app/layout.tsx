import "./globals.css";
import type { Metadata } from "next";
import Sidebar from "@/components/layout/Sidebar";
import Topbar from "@/components/layout/Topbar";
import StoreBootstrap from "@/components/StoreBootstrap";
import MailDraftModal from "@/components/MailDraftModal";

export const metadata: Metadata = {
  title: "Supplier Follow-up Agent",
  description: "PO-wise and Material-wise Automated Follow-up System",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <StoreBootstrap />
        <div className="min-h-screen flex flex-col">
          <Topbar />
          <div className="flex-1 flex">
            <Sidebar />
            <main className="flex-1 p-6 max-w-[1600px] w-full mx-auto">{children}</main>
          </div>
        </div>
        <MailDraftModal />
      </body>
    </html>
  );
}

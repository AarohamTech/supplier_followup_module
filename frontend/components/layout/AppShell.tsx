"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";

import { useAuth } from "@/lib/auth";
import Sidebar from "@/components/layout/Sidebar";
import Topbar from "@/components/layout/Topbar";
import StoreBootstrap from "@/components/StoreBootstrap";
import MailDraftModal from "@/components/MailDraftModal";
import SendToaster from "@/components/SendToaster";
import SupplierShell from "@/components/portal/SupplierShell";
import PortalChangePassword from "@/components/portal/PortalChangePassword";

const PUBLIC_PATHS = ["/login"];

function FullScreen({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen flex items-center justify-center text-sm text-brand-muted">
      {children}
    </div>
  );
}

/**
 * Client-side gate around the whole app:
 *  - /login renders bare (no shell)
 *  - supplier accounts get the portal shell (scoped to /portal/*)
 *  - staff accounts get the internal shell (everything else)
 */
export default function AppShell({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const isPublic = PUBLIC_PATHS.includes(pathname);
  const isSupplier = !!user && user.supplier_id != null;
  const inPortal = pathname === "/portal" || pathname.startsWith("/portal/");

  // Redirect rules run after render to keep hooks order stable.
  useEffect(() => {
    if (loading) return;
    if (!user && !isPublic) router.replace("/login");
    if (user && isPublic) router.replace(isSupplier ? "/portal" : "/");
    // Keep each account type inside its own surface.
    if (user && isSupplier && !isPublic && !inPortal) router.replace("/portal");
    if (user && !isSupplier && inPortal) router.replace("/");
  }, [loading, user, isPublic, isSupplier, inPortal, router]);

  useEffect(() => {
    setSidebarOpen(false);
  }, [pathname]);

  if (loading) return <FullScreen>Loading...</FullScreen>;

  // Login and any future public pages render without the app chrome.
  if (isPublic) {
    if (user) return <FullScreen>Redirecting...</FullScreen>;
    return <>{children}</>;
  }

  // Not authenticated on a protected route - show a light state while redirecting.
  if (!user) return <FullScreen>Redirecting to sign in...</FullScreen>;

  // ── Supplier portal ─────────────────────────────────────────────────────────
  if (isSupplier) {
    // Force the first-login / post-reset password change before anything else.
    if (user.must_change_password) return <PortalChangePassword />;
    if (!inPortal) return <FullScreen>Opening your portal...</FullScreen>;
    return (
      <SupplierShell open={sidebarOpen} onMenuClick={() => setSidebarOpen(true)} onClose={() => setSidebarOpen(false)}>
        {children}
      </SupplierShell>
    );
  }

  // ── Internal staff app ───────────────────────────────────────────────────────
  if (inPortal) return <FullScreen>Redirecting...</FullScreen>;

  return (
    <>
      <StoreBootstrap />
      <div className="min-h-screen flex flex-col bg-brand-surface">
        <Topbar onMenuClick={() => setSidebarOpen(true)} />
        <div className="flex-1 flex min-h-0">
          <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />
          <main
            key={pathname}
            className="page-enter flex-1 min-w-0 px-4 py-5 sm:px-6 lg:px-8 max-w-[1600px] w-full mx-auto"
          >
            {children}
          </main>
        </div>
      </div>
      <MailDraftModal />
      <SendToaster />
    </>
  );
}

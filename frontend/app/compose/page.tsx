"use client";

import api from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { ShieldCheck } from "lucide-react";
import ComposeWorkspace, { type ComposeAdapter } from "@/components/compose/ComposeWorkspace";

// Staff compose — suppliers or customers, full recipient auto-fill.
const staffAdapter: ComposeAdapter = {
  allowCustomer: true,
  compose: (body) => api.hubCompose(body),
  composeDraft: (body) => api.hubComposeDraft(body),
  loadSupplierContacts: () =>
    api.listSupplierEmails().then((rows) =>
      rows.map((r) => ({
        supplier_name: r.supplier_name ?? "",
        to_emails: r.to_emails ?? [],
        cc_emails: r.cc_emails ?? [],
      })),
    ),
};

export default function ComposePage() {
  const { hasRole } = useAuth();
  // Writers only (admin / manager / user); viewers, suppliers and customers excluded.
  if (!hasRole("user")) {
    return (
      <div className="empty-state">
        <ShieldCheck className="mx-auto mb-2 h-6 w-6 text-brand-muted" />
        You need writer access (admin, manager or user) to compose mail.
      </div>
    );
  }
  return <ComposeWorkspace adapter={staffAdapter} />;
}

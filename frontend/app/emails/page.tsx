"use client";

import { useMemo } from "react";

import { useStore } from "@/lib/store";
import { useAuth } from "@/lib/auth";
import api from "@/lib/api";
import EmailMasterView, { type EmailMasterAdapter } from "@/components/emails/EmailMasterView";

export default function Page() {
  const reloadStore = useStore((s) => s.loadSuppliers);
  const { hasRole } = useAuth();
  const isAdmin = hasRole("admin");

  const adapter = useMemo<EmailMasterAdapter>(
    () => ({
      listSuppliers: () => api.listSuppliers(),
      listMappings: () => api.listSupplierEmails(),
      create: (body) => api.createSupplierEmail(body),
      update: (id, body) => api.updateSupplierEmail(id, body),
      remove: (id) => api.deleteSupplierEmail(id),
    }),
    [],
  );

  return (
    <EmailMasterView
      adapter={adapter}
      // Any writer (admin/manager/user) can ADD a mapping; changing or deleting
      // one, supplier logins and the change log are admin-only (backend enforces).
      permissions={{
        canAdd: hasRole("user"),
        canEdit: isAdmin,
        canDelete: isAdmin,
        canManageLogins: isAdmin,
        canViewAudit: isAdmin,
      }}
      // Other staff pages read mappings from the shared store; keep it in sync.
      onChanged={reloadStore}
    />
  );
}

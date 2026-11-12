"use client";

import { useMemo } from "react";

import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useT } from "@/lib/i18n";
import EmailMasterView, { type EmailMasterAdapter } from "@/components/emails/EmailMasterView";

/** Employee portal: Email Master, shown when the employee holds the
 *  can_manage_email_master permission (granted by default; the server enforces
 *  it on every call). Employees can list, add and edit mappings; deleting a
 *  mapping, supplier logins and the change log stay with admins. */
export default function EmployeeEmailMasterPage() {
  const { t } = useT();
  const { user } = useAuth();
  const allowed = user?.can_manage_email_master !== false;

  const adapter = useMemo<EmailMasterAdapter>(
    () => ({
      listSuppliers: () => api.eportalManageSuppliers(),
      listMappings: () => api.eportalManageSupplierEmails(),
      create: (body) => api.eportalManageCreateSupplierEmail(body),
      update: (id, body) => api.eportalManageUpdateSupplierEmail(id, body),
    }),
    [],
  );

  if (!allowed) {
    return (
      <div className="page-stack">
        <div className="card p-6 text-sm text-brand-muted">
          {t("Your account does not have access to Email Master. Ask an admin to enable it.")}
        </div>
      </div>
    );
  }
  return (
    <EmailMasterView
      adapter={adapter}
      permissions={{ canAdd: true, canEdit: true, canDelete: false, canManageLogins: false, canViewAudit: false }}
    />
  );
}

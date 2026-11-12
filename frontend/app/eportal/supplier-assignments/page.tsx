"use client";

import { useMemo } from "react";

import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useT } from "@/lib/i18n";
import SupplierAssignmentsView, {
  type SupplierAssignmentsAdapter,
} from "@/components/supplier-assignments/SupplierAssignmentsView";

/** Employee portal: Supplier Assignment, shown when the employee holds the
 *  can_manage_supplier_assignments permission (granted by default; the server
 *  enforces it on every call). */
export default function EmployeeSupplierAssignmentsPage() {
  const { t } = useT();
  const { user } = useAuth();
  const allowed = user?.can_manage_supplier_assignments !== false;

  const adapter = useMemo<SupplierAssignmentsAdapter>(
    () => ({
      list: (params) => api.eportalManageSupplierAssignments(params),
      assignableUsers: () => api.eportalManageAssignableUsers(),
      setAssignees: (supplierId, userIds) => api.eportalManageSetAssignees(supplierId, userIds),
    }),
    [],
  );

  if (!allowed) {
    return (
      <div className="page-stack">
        <div className="card p-6 text-sm text-brand-muted">
          {t("Your account does not have access to Supplier Assignment. Ask an admin to enable it.")}
        </div>
      </div>
    );
  }
  return <SupplierAssignmentsView adapter={adapter} canEdit />;
}

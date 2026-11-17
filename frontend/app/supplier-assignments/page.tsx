"use client";

import { useMemo } from "react";

import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import SupplierAssignmentsView, {
  type SupplierAssignmentsAdapter,
} from "@/components/supplier-assignments/SupplierAssignmentsView";

export default function SupplierAssignmentsPage() {
  const { hasRole } = useAuth();

  const adapter = useMemo<SupplierAssignmentsAdapter>(
    () => ({
      list: (params) => api.listSupplierAssignments(params),
      assignableUsers: () => api.assignableUsers(),
      setAssignees: (supplierId, userIds) => api.setSupplierAssignees(supplierId, userIds),
    }),
    [],
  );

  // Staff: any user with write access (not a viewer) can change assignees.
  return <SupplierAssignmentsView adapter={adapter} canEdit={hasRole("user")} />;
}

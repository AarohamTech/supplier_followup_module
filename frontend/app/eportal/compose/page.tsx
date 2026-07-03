"use client";

import api from "@/lib/api";
import ComposeWorkspace, { type ComposeAdapter } from "@/components/compose/ComposeWorkspace";

// Employee compose — scoped to the employee's own suppliers/POs; no customer audience.
const employeeAdapter: ComposeAdapter = {
  allowCustomer: false,
  compose: (body) => api.eportalCompose(body),
  composeDraft: (body) => api.eportalComposeDraft(body),
  loadSupplierContacts: () => api.eportalHubSupplierEmails(),
};

export default function EmployeeComposePage() {
  return (
    <ComposeWorkspace
      adapter={employeeAdapter}
      description="Write and send an email to one of your suppliers — delivered in your branded HTML format."
    />
  );
}

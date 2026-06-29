"use client";

import { api } from "@/lib/api";
import PortalTaskWorkspace, { type PortalTaskAdapter } from "@/components/portal/PortalTaskWorkspace";

const employeeAdapter: PortalTaskAdapter = {
  listTasks: (filters) => api.eportalTasks(filters),
  dashboard: () => api.eportalTasksDashboard(),
  updateTask: (id, patch) => api.eportalUpdateTask(id, patch),
  createTask: (payload) => api.eportalCreateTask(payload),
  deleteTask: (id) => api.eportalDeleteTask(id),
  listAssignees: () => api.eportalAssignees(),
  listComments: (id) => api.eportalTaskComments(id),
  addComment: (id, comment) => api.eportalAddTaskComment(id, comment),
};

export default function EmployeeTasksPage() {
  return (
    <PortalTaskWorkspace
      adapter={employeeAdapter}
      permissions={{ canCreate: true, canEdit: true, canAssign: true, canDelete: true, canComment: true, readOnly: false }}
      scopeLabel="My Tasks"
    />
  );
}

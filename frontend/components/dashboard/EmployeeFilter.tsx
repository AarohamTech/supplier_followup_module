"use client";
import { useEffect, useState } from "react";
import api from "@/lib/api";
import { useStore } from "@/lib/store";
import type { AuthUser } from "@/lib/types";

/** Admin-dashboard control: scope the whole dashboard (KPIs, signal + supplier
 * pies, and the PO table) to a single employee/desk by owner_emp_code. */
export default function EmployeeFilter() {
  const owner = useStore((s) => s.filters.owner_emp_code);
  const setFilters = useStore((s) => s.setFilters);
  const [emps, setEmps] = useState<AuthUser[]>([]);

  useEffect(() => {
    let on = true;
    api
      .listEmployeeLogins()
      .then((r) => {
        if (on) setEmps(r);
      })
      .catch(() => {
        /* non-fatal: the dropdown just stays at "All employees" */
      });
    return () => {
      on = false;
    };
  }, []);

  const options = emps
    .filter((e) => e.emp_code)
    .sort((a, b) => (a.full_name || a.username || "").localeCompare(b.full_name || b.username || ""));

  return (
    <div className="flex flex-col gap-1">
      <label className="text-[10px] font-semibold uppercase tracking-wider text-brand-muted">Employee</label>
      <select
        value={owner ?? ""}
        onChange={(e) => setFilters({ owner_emp_code: e.target.value })}
        className="input py-1.5"
      >
        <option value="">All employees</option>
        {options.map((e) => (
          <option key={e.emp_code!} value={e.emp_code!}>
            {e.full_name || e.username || e.emp_code}
          </option>
        ))}
      </select>
    </div>
  );
}

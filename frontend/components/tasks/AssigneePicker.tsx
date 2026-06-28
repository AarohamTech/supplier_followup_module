"use client";

import { useMemo, useState } from "react";
import type { TaskAssignee } from "@/lib/types";

export function AssigneePicker({
  value,
  onChange,
  assignees,
  placeholder = "Unassigned",
}: {
  value: number | null | undefined;
  onChange: (id: number | null) => void;
  assignees: TaskAssignee[];
  placeholder?: string;
}) {
  return (
    <select
      className="w-full rounded-md border border-brand-border px-2 py-1.5 text-sm"
      value={value ?? ""}
      onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)}
    >
      <option value="">{placeholder}</option>
      {assignees.map((a) => (
        <option key={a.id} value={a.id}>
          {a.label} ({a.type === "employee" ? "emp" : a.role})
        </option>
      ))}
    </select>
  );
}

export function WatcherPicker({
  value,
  onChange,
  assignees,
}: {
  value: number[];
  onChange: (ids: number[]) => void;
  assignees: TaskAssignee[];
}) {
  const [open, setOpen] = useState(false);
  const selected = useMemo(() => new Set(value), [value]);
  const toggle = (id: number) => {
    const next = new Set(selected);
    next.has(id) ? next.delete(id) : next.add(id);
    onChange([...next]);
  };
  const labels = assignees.filter((a) => selected.has(a.id)).map((a) => a.label);
  return (
    <div className="relative">
      <button
        type="button"
        className="w-full rounded-md border border-brand-border px-2 py-1.5 text-left text-sm"
        onClick={() => setOpen((o) => !o)}
      >
        {labels.length ? labels.join(", ") : "No watchers"}
      </button>
      {open && (
        <div className="absolute z-10 mt-1 max-h-48 w-full overflow-y-auto rounded-md border border-brand-border bg-white shadow">
          {assignees.map((a) => (
            <label
              key={a.id}
              className="flex items-center gap-2 px-2 py-1 text-sm hover:bg-gray-50"
            >
              <input
                type="checkbox"
                checked={selected.has(a.id)}
                onChange={() => toggle(a.id)}
              />
              {a.label}
            </label>
          ))}
        </div>
      )}
    </div>
  );
}

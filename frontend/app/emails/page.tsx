"use client";

import { useState } from "react";
import { useStore } from "@/lib/store";
import api from "@/lib/api";
import type { SupplierEmail } from "@/lib/types";
import { Mail, Pencil, Trash2, Plus, X, Save } from "lucide-react";
import PageHeader from "@/components/layout/PageHeader";

const EMPTY: Partial<SupplierEmail> = {
  supplier_id: undefined,
  supplier_name: "",
  to_emails: [],
  cc_emails: [],
  bcc_emails: [],
  escalation_emails: [],
  contact_person: "",
  phone: "",
  remarks: "",
  is_active: true,
};

export default function Page() {
  const supplierMasters = useStore((s) => s.supplierMasters);
  const mappings = useStore((s) => s.suppliers);
  const reload = useStore((s) => s.loadSuppliers);
  const [editing, setEditing] = useState<Partial<SupplierEmail> | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const save = async () => {
    if (!editing?.supplier_id) {
      setError("Select a supplier.");
      return;
    }
    if (!editing.to_emails?.length) {
      setError("Add at least one TO email.");
      return;
    }
    const duplicate = mappings.some((mapping) =>
      mapping.id !== editing.id &&
      mapping.supplier_id === editing.supplier_id &&
      mapping.is_active &&
      (editing.is_active ?? true)
    );
    if (duplicate) {
      setError("This supplier already has an active email mapping.");
      return;
    }

    setBusy(true);
    setError(null);
    try {
      if (editing.id) await api.updateSupplierEmail(editing.id, editing);
      else await api.createSupplierEmail(editing);
      setEditing(null);
      await reload();
    } catch (e: any) {
      setError(e.message ?? "Unable to save email mapping.");
    } finally {
      setBusy(false);
    }
  };

  const remove = async (id: number) => {
    if (!confirm("Delete this email mapping?")) return;
    await api.deleteSupplierEmail(id);
    await reload();
  };

  const edit = (mapping: SupplierEmail) => {
    setError(null);
    setEditing({
      ...mapping,
      to_emails: mapping.to_emails ?? [],
      cc_emails: mapping.cc_emails ?? [],
      bcc_emails: mapping.bcc_emails ?? [],
      escalation_emails: mapping.escalation_emails ?? [],
    });
  };

  return (
    <div className="page-stack">
      <PageHeader
        title="Email Master"
        description="Maintain supplier recipient, CC, BCC and escalation mappings."
        icon={Mail}
        actions={
          <button onClick={() => { setError(null); setEditing({ ...EMPTY }); }} className="btn-primary">
            <Plus size={14} /> Add Mapping
          </button>
        }
      />
      {error && !editing && (
        <div className="rounded-md bg-red-50 px-3 py-2 text-xs text-signal-red">{error}</div>
      )}

      <div className="card overflow-hidden">
        <table className="min-w-full text-sm">
          <thead className="bg-gray-50">
            <tr>
              {["Supplier", "Primary", "CC", "BCC", "Escalation", "Active", "Actions"].map((h) => (
                <th key={h} className="text-left px-4 py-3 table-header whitespace-nowrap">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {mappings.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-10 text-center text-brand-muted">No mappings yet.</td>
              </tr>
            )}
            {mappings.map((mapping) => (
              <tr key={mapping.id} className="border-t border-brand-border hover:bg-gray-50">
                <td className="px-4 py-3 font-medium">{mapping.supplier_name}</td>
                <td className="px-4 py-3 text-xs">{joinEmails(mapping.to_emails)}</td>
                <td className="px-4 py-3 text-xs">{joinEmails(mapping.cc_emails)}</td>
                <td className="px-4 py-3 text-xs">{joinEmails(mapping.bcc_emails)}</td>
                <td className="px-4 py-3 text-xs">{joinEmails(mapping.escalation_emails)}</td>
                <td className="px-4 py-3">
                  {mapping.is_active
                    ? <span className="badge badge-track">YES</span>
                    : <span className="badge badge-overdue">NO</span>}
                </td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    <button title="Edit" onClick={() => edit(mapping)} className="p-1 rounded hover:bg-gray-100">
                      <Pencil size={14} />
                    </button>
                    <button title="Delete" onClick={() => remove(mapping.id)} className="p-1 rounded hover:bg-red-50 text-signal-red">
                      <Trash2 size={14} />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {editing && (
        <div className="fixed inset-0 z-50 bg-black/40 grid place-items-center p-4" onClick={() => setEditing(null)}>
          <div className="bg-white rounded-lg shadow-xl w-full max-w-2xl" onClick={(e) => e.stopPropagation()}>
            <div className="px-5 py-3 border-b border-brand-border flex items-center justify-between">
              <div className="font-semibold">{editing.id ? "Edit" : "Add"} Email Mapping</div>
              <button className="p-1 rounded hover:bg-gray-100" onClick={() => setEditing(null)}><X size={18} /></button>
            </div>
            <div className="p-5 space-y-4">
              {error && <div className="text-sm text-signal-red bg-red-50 border border-red-100 rounded-md px-3 py-2">{error}</div>}
              <div>
                <div className="text-[10px] uppercase tracking-wider text-brand-muted font-semibold mb-1">Supplier Dropdown *</div>
                <select
                  className="w-full border border-brand-border rounded-md px-3 py-2 text-sm bg-white"
                  value={editing.supplier_id ?? ""}
                  onChange={(event) => {
                    const supplierId = Number(event.target.value);
                    const supplier = supplierMasters.find((item) => item.id === supplierId);
                    setEditing({
                      ...editing,
                      supplier_id: supplier?.id,
                      supplier_name: supplier?.supplier_name ?? "",
                    });
                  }}
                >
                  <option value="">Select supplier</option>
                  {supplierMasters.map((supplier) => (
                    <option key={supplier.id} value={supplier.id}>{supplier.supplier_name}</option>
                  ))}
                </select>
              </div>

              <TagsInput label="TO Emails *" values={editing.to_emails ?? []} onChange={(values) => setEditing({ ...editing, to_emails: values })} />
              <TagsInput label="CC Emails" values={editing.cc_emails ?? []} onChange={(values) => setEditing({ ...editing, cc_emails: values })} />
              <TagsInput label="BCC Emails" values={editing.bcc_emails ?? []} onChange={(values) => setEditing({ ...editing, bcc_emails: values })} />
              <TagsInput label="Escalation Emails" values={editing.escalation_emails ?? []} onChange={(values) => setEditing({ ...editing, escalation_emails: values })} />

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <Field label="Contact Person" value={editing.contact_person ?? ""} onChange={(value) => setEditing({ ...editing, contact_person: value })} />
                <Field label="Phone" value={editing.phone ?? ""} onChange={(value) => setEditing({ ...editing, phone: value })} />
              </div>
              <Field label="Remarks" value={editing.remarks ?? ""} onChange={(value) => setEditing({ ...editing, remarks: value })} />
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={editing.is_active ?? true}
                  onChange={(event) => setEditing({ ...editing, is_active: event.target.checked })}
                />
                Active
              </label>
            </div>
            <div className="px-5 py-3 border-t border-brand-border flex items-center justify-end gap-2">
              <button className="btn-ghost" onClick={() => setEditing(null)}>Cancel</button>
              <button className="btn-primary" disabled={busy} onClick={save}><Save size={14} /> Save</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function joinEmails(values?: string[]) {
  return values?.length ? values.join(", ") : "-";
}

function Field({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-brand-muted font-semibold mb-1">{label}</div>
      <input
        className="w-full border border-brand-border rounded-md px-3 py-2 text-sm"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </div>
  );
}

function TagsInput({ label, values, onChange }: { label: string; values: string[]; onChange: (values: string[]) => void }) {
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);

  const add = (raw: string) => {
    const parts = raw.split(",").map((part) => part.trim()).filter(Boolean);
    if (parts.length === 0) return;

    const next = [...values];
    for (const email of parts) {
      if (!isEmail(email)) {
        setError(`${email} is not a valid email.`);
        return;
      }
      if (!next.some((item) => item.toLowerCase() === email.toLowerCase())) {
        next.push(email);
      }
    }
    setError(null);
    onChange(next);
    setDraft("");
  };

  const remove = (email: string) => {
    onChange(values.filter((item) => item !== email));
  };

  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-brand-muted font-semibold mb-1">{label}</div>
      <div className="min-h-10 w-full border border-brand-border rounded-md px-2 py-1.5 flex flex-wrap items-center gap-1.5 bg-white">
        {values.map((email) => (
          <span key={email} className="chip py-0.5">
            {email}
            <button type="button" onClick={() => remove(email)} className="hover:text-signal-red">
              <X size={12} />
            </button>
          </span>
        ))}
        <input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onBlur={() => add(draft)}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === "," || event.key === "Tab") {
              event.preventDefault();
              add(draft);
            }
          }}
          className="flex-1 min-w-[180px] outline-none text-sm px-1 py-1"
        />
      </div>
      {error && <div className="mt-1 text-xs text-signal-red">{error}</div>}
    </div>
  );
}

function isEmail(value: string) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
}

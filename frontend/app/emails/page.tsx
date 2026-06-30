"use client";

import { forwardRef, useImperativeHandle, useRef, useState } from "react";
import { useStore } from "@/lib/store";
import { useAuth } from "@/lib/auth";
import api from "@/lib/api";
import type { LoginProvisioningSummary, SupplierEmail } from "@/lib/types";
import { Mail, Pencil, Trash2, Plus, X, Save, KeyRound, History } from "lucide-react";
import PageHeader from "@/components/layout/PageHeader";
import SupplierLoginsModal from "@/components/emails/SupplierLoginsModal";
import EmailAuditModal from "@/components/emails/EmailAuditModal";

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
  const { hasRole } = useAuth();
  const isAdmin = hasRole("admin");
  const canEdit = hasRole("user"); // admin/manager/user (writers); viewers read-only
  const [showAudit, setShowAudit] = useState(false);
  const [editing, setEditing] = useState<Partial<SupplierEmail> | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [provisioning, setProvisioning] = useState<LoginProvisioningSummary | null>(null);
  const [loginsFor, setLoginsFor] = useState<SupplierEmail | null>(null);
  // Refs so Save can flush a typed-but-not-yet-added email from each tag box.
  const toRef = useRef<TagsHandle>(null);
  const ccRef = useRef<TagsHandle>(null);
  const bccRef = useRef<TagsHandle>(null);
  const escRef = useRef<TagsHandle>(null);

  const save = async () => {
    if (!editing?.supplier_id) {
      setError("Select a supplier.");
      return;
    }
    // Commit any pending draft in each tag box so a typed email isn't lost.
    const to_emails = toRef.current?.commit() ?? editing.to_emails ?? [];
    const cc_emails = ccRef.current?.commit() ?? editing.cc_emails ?? [];
    const bcc_emails = bccRef.current?.commit() ?? editing.bcc_emails ?? [];
    const escalation_emails = escRef.current?.commit() ?? editing.escalation_emails ?? [];

    if (!to_emails.length) {
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

    const payload = { ...editing, to_emails, cc_emails, bcc_emails, escalation_emails };
    setBusy(true);
    setError(null);
    try {
      const saved = editing.id
        ? await api.updateSupplierEmail(editing.id, payload)
        : await api.createSupplierEmail(payload);
      setEditing(null);
      setProvisioning(saved.provisioning ?? null);
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
          <div className="flex items-center gap-2">
            {isAdmin && (
              <button onClick={() => setShowAudit(true)} className="btn-ghost" title="View who changed what">
                <History size={14} /> Change Log
              </button>
            )}
            {canEdit && (
              <button onClick={() => { setError(null); setEditing({ ...EMPTY }); }} className="btn-primary">
                <Plus size={14} /> Add Mapping
              </button>
            )}
          </div>
        }
      />
      {error && !editing && (
        <div className="rounded-md bg-red-50 px-3 py-2 text-xs text-signal-red">{error}</div>
      )}

      {provisioning && (
        <div className="card p-4 text-sm">
          <div className="mb-2 flex items-center justify-between">
            <div className="font-semibold text-brand-dark">Supplier login provisioning</div>
            <button className="p-1 rounded hover:bg-subtle" onClick={() => setProvisioning(null)}><X size={16} /></button>
          </div>
          {provisioning.created.length === 0 &&
          provisioning.reactivated.length === 0 &&
          provisioning.deactivated.length === 0 &&
          provisioning.conflicts.length === 0 ? (
            <div className="text-xs text-brand-muted">No login changes — all TO emails were already provisioned.</div>
          ) : (
            <div className="space-y-2">
              {provisioning.created.length > 0 && (
                <div>
                  <div className="text-[11px] font-semibold uppercase tracking-wider text-emerald-700">Logins created</div>
                  <div className="mt-1 overflow-x-auto">
                    <table className="text-xs">
                      <tbody>
                        {provisioning.created.map((c) => (
                          <tr key={c.email}>
                            <td className="pr-4 py-0.5">{c.email}</td>
                            <td className="py-0.5 font-mono font-semibold">{c.temp_password}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <div className="mt-1 text-[11px] text-brand-muted">
                    {provisioning.emailed.length > 0
                      ? `Credentials emailed to: ${provisioning.emailed.join(", ")}.`
                      : "Email not sent (SMTP off) — share the temporary passwords securely."}
                  </div>
                </div>
              )}
              {provisioning.reactivated.length > 0 && (
                <div className="text-xs"><span className="font-semibold">Reactivated:</span> {provisioning.reactivated.join(", ")}</div>
              )}
              {provisioning.deactivated.length > 0 && (
                <div className="text-xs"><span className="font-semibold">Deactivated:</span> {provisioning.deactivated.join(", ")}</div>
              )}
              {provisioning.conflicts.length > 0 && (
                <div className="text-xs text-signal-red">
                  <span className="font-semibold">Skipped (conflict):</span>{" "}
                  {provisioning.conflicts.map((c) => `${c.email} (${c.reason})`).join(", ")}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      <div className="card overflow-hidden">
        <table className="min-w-full text-sm">
          <thead className="bg-subtle">
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
              <tr key={mapping.id} className="border-t border-brand-border hover:bg-subtle">
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
                    {isAdmin && (
                      <button title="Supplier logins" onClick={() => setLoginsFor(mapping)} className="p-1 rounded hover:bg-subtle">
                        <KeyRound size={14} />
                      </button>
                    )}
                    {canEdit && (
                      <button title="Edit" onClick={() => edit(mapping)} className="p-1 rounded hover:bg-subtle">
                        <Pencil size={14} />
                      </button>
                    )}
                    {isAdmin && (
                      <button title="Delete (admin only)" onClick={() => remove(mapping.id)} className="p-1 rounded hover:bg-red-50 text-signal-red">
                        <Trash2 size={14} />
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {editing && (
        <div className="fixed inset-0 z-50 bg-black/40 grid place-items-center p-4" onClick={() => setEditing(null)}>
          <div className="bg-card rounded-lg shadow-xl w-full max-w-2xl" onClick={(e) => e.stopPropagation()}>
            <div className="px-5 py-3 border-b border-brand-border flex items-center justify-between">
              <div className="font-semibold">{editing.id ? "Edit" : "Add"} Email Mapping</div>
              <button className="p-1 rounded hover:bg-subtle" onClick={() => setEditing(null)}><X size={18} /></button>
            </div>
            <div className="p-5 space-y-4">
              {error && <div className="text-sm text-signal-red bg-red-50 border border-red-100 rounded-md px-3 py-2">{error}</div>}
              <div>
                <div className="text-[10px] uppercase tracking-wider text-brand-muted font-semibold mb-1">Supplier Dropdown *</div>
                <select
                  className="w-full border border-brand-border rounded-md px-3 py-2 text-sm bg-card"
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

              <div>
                <TagsInput ref={toRef} label="TO Emails *" values={editing.to_emails ?? []} onChange={(values) => setEditing({ ...editing, to_emails: values })} />
                <p className="mt-1 text-[11px] text-brand-muted">
                  Each TO email gets a Supplier Portal login (a temporary password is emailed; they’re asked to change it on first login).
                </p>
              </div>
              <TagsInput ref={ccRef} label="CC Emails" values={editing.cc_emails ?? []} onChange={(values) => setEditing({ ...editing, cc_emails: values })} />
              <TagsInput ref={bccRef} label="BCC Emails" values={editing.bcc_emails ?? []} onChange={(values) => setEditing({ ...editing, bcc_emails: values })} />
              <TagsInput ref={escRef} label="Escalation Emails" values={editing.escalation_emails ?? []} onChange={(values) => setEditing({ ...editing, escalation_emails: values })} />

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

      {loginsFor && <SupplierLoginsModal mapping={loginsFor} onClose={() => setLoginsFor(null)} />}
      {showAudit && <EmailAuditModal onClose={() => setShowAudit(false)} />}
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

type TagsHandle = { commit: () => string[] };

const TagsInput = forwardRef<TagsHandle, { label: string; values: string[]; onChange: (values: string[]) => void }>(
  function TagsInput({ label, values, onChange }, ref) {
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

  // Called by the parent on Save: fold any valid typed-but-unadded email into
  // the list and return the final array synchronously (no state-timing races).
  useImperativeHandle(ref, () => ({
    commit: () => {
      const parts = draft.split(",").map((p) => p.trim()).filter(Boolean);
      if (parts.length === 0) return values;
      const next = [...values];
      let changed = false;
      for (const email of parts) {
        if (!isEmail(email)) continue; // ignore an incomplete entry on save
        if (!next.some((item) => item.toLowerCase() === email.toLowerCase())) {
          next.push(email);
          changed = true;
        }
      }
      if (changed) {
        onChange(next);
        setDraft("");
      }
      return next;
    },
  }));

  const remove = (email: string) => {
    onChange(values.filter((item) => item !== email));
  };

  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-brand-muted font-semibold mb-1">{label}</div>
      <div className="min-h-10 w-full border border-brand-border rounded-md px-2 py-1.5 flex flex-wrap items-center gap-1.5 bg-card">
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
});

function isEmail(value: string) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
}

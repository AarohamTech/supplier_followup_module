"use client";

import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react";
import { History, KeyRound, Mail, Pencil, Plus, RefreshCw, Save, Trash2, X } from "lucide-react";

import type { LoginProvisioningSummary, SupplierEmail } from "@/lib/types";
import { useT } from "@/lib/i18n";
import PageHeader from "@/components/layout/PageHeader";
import Pager from "@/components/ui/Pager";
import SupplierLoginsModal from "@/components/emails/SupplierLoginsModal";
import EmailAuditModal from "@/components/emails/EmailAuditModal";

const SIZE = 50;

export type SupplierOption = { id: number; supplier_name: string; is_active?: boolean };

/** Data access for the Email Master screen. The staff page and the employee
 *  portal pass different endpoints; the screen itself is the same. */
export type EmailMasterAdapter = {
  listSuppliers: () => Promise<SupplierOption[]>;
  listMappings: () => Promise<SupplierEmail[]>;
  create: (body: Partial<SupplierEmail>) => Promise<SupplierEmail>;
  update: (id: number, body: Partial<SupplierEmail>) => Promise<SupplierEmail>;
  remove?: (id: number) => Promise<void>;
};

export type EmailMasterPermissions = {
  canAdd: boolean;
  canEdit: boolean;
  canDelete: boolean;
  canManageLogins: boolean;
  canViewAudit: boolean;
};

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

function errText(e: unknown, fallback: string): string {
  const msg = (e as Error)?.message;
  return msg && msg.trim() ? msg : fallback;
}

export default function EmailMasterView({
  adapter,
  permissions,
  onChanged,
}: {
  adapter: EmailMasterAdapter;
  permissions: EmailMasterPermissions;
  /** Called after a successful save/delete (the staff page refreshes its shared store). */
  onChanged?: () => void | Promise<void>;
}) {
  const { t } = useT();
  const { canAdd, canEdit, canDelete, canManageLogins, canViewAudit } = permissions;

  const [supplierMasters, setSupplierMasters] = useState<SupplierOption[]>([]);
  const [mappings, setMappings] = useState<SupplierEmail[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [showAudit, setShowAudit] = useState(false);
  const [editing, setEditing] = useState<Partial<SupplierEmail> | null>(null);
  const [busy, setBusy] = useState(false);
  // Error inside the edit dialog (save failures) vs. on the page (delete / refresh).
  const [error, setError] = useState<string | null>(null);
  const [pageError, setPageError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [provisioning, setProvisioning] = useState<LoginProvisioningSummary | null>(null);
  const [loginsFor, setLoginsFor] = useState<SupplierEmail | null>(null);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  // Refs so Save can flush a typed-but-not-yet-added email from each tag box.
  const toRef = useRef<TagsHandle>(null);
  const ccRef = useRef<TagsHandle>(null);
  const bccRef = useRef<TagsHandle>(null);
  const escRef = useRef<TagsHandle>(null);

  const reload = useCallback(async (): Promise<string | null> => {
    try {
      const [masters, rows] = await Promise.all([adapter.listSuppliers(), adapter.listMappings()]);
      setSupplierMasters(Array.isArray(masters) ? masters : []);
      setMappings(Array.isArray(rows) ? rows : []);
      setLoadError(null);
      return null;
    } catch (e) {
      const msg = errText(e, t("Could not load email mappings."));
      setLoadError(msg);
      return msg;
    } finally {
      setLoading(false);
    }
  }, [adapter, t]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const save = async () => {
    if (!editing?.supplier_id) {
      setError(t("Select a supplier."));
      return;
    }
    // Commit any pending draft in each tag box so a typed email isn't lost.
    const to_emails = toRef.current?.commit() ?? editing.to_emails ?? [];
    const cc_emails = ccRef.current?.commit() ?? editing.cc_emails ?? [];
    const bcc_emails = bccRef.current?.commit() ?? editing.bcc_emails ?? [];
    const escalation_emails = escRef.current?.commit() ?? editing.escalation_emails ?? [];

    if (!to_emails.length) {
      setError(t("Add at least one TO email."));
      return;
    }
    const duplicate = mappings.some((mapping) =>
      mapping.id !== editing.id &&
      mapping.supplier_id === editing.supplier_id &&
      mapping.is_active &&
      (editing.is_active ?? true),
    );
    if (duplicate) {
      setError(t("This supplier already has an active email mapping."));
      return;
    }

    // Send only the editable fields (not id/timestamps/last provisioning result).
    const payload: Partial<SupplierEmail> = {
      supplier_id: editing.supplier_id,
      to_emails,
      cc_emails,
      bcc_emails,
      escalation_emails,
      contact_person: editing.contact_person ?? "",
      phone: editing.phone ?? "",
      remarks: editing.remarks ?? "",
      is_active: editing.is_active ?? true,
    };
    setBusy(true);
    setError(null);
    setPageError(null);
    setNotice(null);
    try {
      const saved = editing.id
        ? await adapter.update(editing.id, payload)
        : await adapter.create(payload);
      // Show the saved row at once, even before the list refresh returns.
      setMappings((prev) => {
        const rest = prev.filter((m) => m.id !== saved.id);
        return [...rest, saved].sort((a, b) => (a.supplier_name || "").localeCompare(b.supplier_name || ""));
      });
      setEditing(null);
      setProvisioning(saved.provisioning ?? null);
      setNotice(t("Saved email mapping for {name}.", { name: saved.supplier_name }));
      const refreshError = await reload();
      if (refreshError) {
        setPageError(t("Saved, but the list could not be refreshed: {error}", { error: refreshError }));
      }
      try {
        await onChanged?.();
      } catch {
        /* the shared store refresh is best-effort */
      }
    } catch (e) {
      setError(errText(e, t("Unable to save email mapping.")));
    } finally {
      setBusy(false);
    }
  };

  const remove = async (id: number) => {
    if (!adapter.remove) return;
    if (!confirm(t("Delete this email mapping?"))) return;
    setPageError(null);
    setNotice(null);
    try {
      await adapter.remove(id);
      const refreshError = await reload();
      if (refreshError) setPageError(t("Deleted, but the list could not be refreshed: {error}", { error: refreshError }));
      try {
        await onChanged?.();
      } catch {
        /* best-effort */
      }
    } catch (e) {
      setPageError(errText(e, t("Unable to delete email mapping.")));
    }
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

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return mappings;
    return mappings.filter((m) =>
      `${m.supplier_name} ${(m.to_emails ?? []).join(" ")} ${m.contact_person ?? ""}`.toLowerCase().includes(q),
    );
  }, [mappings, search]);
  useEffect(() => setPage(1), [search]);
  const paged = useMemo(() => filtered.slice((page - 1) * SIZE, page * SIZE), [filtered, page]);

  // The editing supplier may be missing from the dropdown list (e.g. it failed to
  // load); keep it selectable so the select never silently shows "Select supplier".
  const supplierOptions = useMemo(() => {
    if (!editing?.supplier_id || supplierMasters.some((s) => s.id === editing.supplier_id)) return supplierMasters;
    return [{ id: editing.supplier_id, supplier_name: editing.supplier_name || `#${editing.supplier_id}` }, ...supplierMasters];
  }, [supplierMasters, editing?.supplier_id, editing?.supplier_name]);

  const showActions = canManageLogins || canEdit || (canDelete && !!adapter.remove);
  const relinked = provisioning?.relinked ?? [];

  return (
    <div className="page-stack">
      <PageHeader
        title={t("Email Master")}
        description={t("Maintain supplier recipient, CC, BCC and escalation mappings.")}
        icon={Mail}
        actions={
          <div className="flex items-center gap-2">
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={t("Search supplier / email…")}
              className="input max-w-xs"
            />
            {canViewAudit && (
              <button onClick={() => setShowAudit(true)} className="btn-ghost" title={t("View who changed what")}>
                <History size={14} /> {t("Change Log")}
              </button>
            )}
            {canAdd && (
              <button onClick={() => { setError(null); setEditing({ ...EMPTY }); }} className="btn-primary">
                <Plus size={14} /> {t("Add Mapping")}
              </button>
            )}
          </div>
        }
      />

      {loadError && (
        <div className="flex items-center justify-between gap-3 rounded-md bg-red-50 px-3 py-2 text-xs text-signal-red">
          <span>{t("Could not load email mappings.")} {loadError}</span>
          <button className="btn-ghost text-xs" onClick={() => { setLoading(true); void reload(); }}>
            <RefreshCw size={12} /> {t("Retry")}
          </button>
        </div>
      )}
      {pageError && (
        <div className="rounded-md bg-red-50 px-3 py-2 text-xs text-signal-red">{pageError}</div>
      )}
      {notice && !pageError && (
        <div className="rounded-md bg-emerald-50 px-3 py-2 text-xs text-emerald-700">{notice}</div>
      )}

      {provisioning && (
        <div className="card p-4 text-sm">
          <div className="mb-2 flex items-center justify-between">
            <div className="font-semibold text-brand-dark">{t("Supplier login provisioning")}</div>
            <button className="p-1 rounded hover:bg-subtle" onClick={() => setProvisioning(null)}><X size={16} /></button>
          </div>
          {provisioning.created.length === 0 &&
          provisioning.reactivated.length === 0 &&
          relinked.length === 0 &&
          provisioning.deactivated.length === 0 &&
          provisioning.conflicts.length === 0 ? (
            <div className="text-xs text-brand-muted">{t("No login changes — all TO emails were already provisioned.")}</div>
          ) : (
            <div className="space-y-2">
              {provisioning.created.length > 0 && (
                <div>
                  <div className="text-[11px] font-semibold uppercase tracking-wider text-emerald-700">{t("Logins created")}</div>
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
                      ? t("Credentials emailed to: {emails}.", { emails: provisioning.emailed.join(", ") })
                      : t("Email not sent (SMTP off) — share the temporary passwords securely.")}
                  </div>
                </div>
              )}
              {provisioning.reactivated.length > 0 && (
                <div className="text-xs"><span className="font-semibold">{t("Reactivated:")}</span> {provisioning.reactivated.join(", ")}</div>
              )}
              {relinked.length > 0 && (
                <div className="text-xs">
                  <span className="font-semibold">{t("Re-linked to this supplier:")}</span> {relinked.join(", ")}
                  <span className="text-brand-muted"> {t("(the login pointed at an old or duplicate supplier record; its password is unchanged)")}</span>
                </div>
              )}
              {provisioning.deactivated.length > 0 && (
                <div className="text-xs"><span className="font-semibold">{t("Deactivated:")}</span> {provisioning.deactivated.join(", ")}</div>
              )}
              {provisioning.conflicts.length > 0 && (
                <div className="text-xs text-signal-red">
                  <div className="font-semibold">{t("Skipped (conflict):")}</div>
                  <ul className="mt-0.5 list-disc pl-5">
                    {provisioning.conflicts.map((c) => (
                      <li key={c.email}>{c.email} — {c.reason}</li>
                    ))}
                  </ul>
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
              {[t("Supplier"), t("Primary"), "CC", "BCC", t("Escalation"), t("Active"), ...(showActions ? [t("Actions")] : [])].map((h) => (
                <th key={h} className="text-left px-4 py-3 table-header whitespace-nowrap">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={7} className="px-4 py-10 text-center text-brand-muted">{t("Loading…")}</td>
              </tr>
            )}
            {!loading && filtered.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-10 text-center text-brand-muted">
                  {loadError ? t("Could not load email mappings.") : mappings.length === 0 ? t("No mappings yet.") : t("No mappings match your search.")}
                </td>
              </tr>
            )}
            {paged.map((mapping) => (
              <tr key={mapping.id} className="border-t border-brand-border hover:bg-subtle">
                <td className="px-4 py-3 font-medium">{mapping.supplier_name}</td>
                <td className="px-4 py-3 text-xs">{joinEmails(mapping.to_emails)}</td>
                <td className="px-4 py-3 text-xs">{joinEmails(mapping.cc_emails)}</td>
                <td className="px-4 py-3 text-xs">{joinEmails(mapping.bcc_emails)}</td>
                <td className="px-4 py-3 text-xs">{joinEmails(mapping.escalation_emails)}</td>
                <td className="px-4 py-3">
                  {mapping.is_active
                    ? <span className="badge badge-track">{t("YES")}</span>
                    : <span className="badge badge-overdue">{t("NO")}</span>}
                </td>
                {showActions && (
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      {canManageLogins && (
                        <button title={t("Supplier logins")} onClick={() => setLoginsFor(mapping)} className="p-1 rounded hover:bg-subtle">
                          <KeyRound size={14} />
                        </button>
                      )}
                      {canEdit && (
                        <button title={t("Edit")} onClick={() => edit(mapping)} className="p-1 rounded hover:bg-subtle">
                          <Pencil size={14} />
                        </button>
                      )}
                      {canDelete && adapter.remove && (
                        <button title={t("Delete (admin only)")} onClick={() => remove(mapping.id)} className="p-1 rounded hover:bg-red-50 text-signal-red">
                          <Trash2 size={14} />
                        </button>
                      )}
                    </div>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Pager page={page} size={SIZE} total={filtered.length} onPage={setPage} unit="mappings" />

      {editing && (
        <div className="fixed inset-0 z-50 bg-black/40 grid place-items-center p-4" onClick={() => !busy && setEditing(null)}>
          <div className="bg-card rounded-lg shadow-xl w-full max-w-2xl" onClick={(e) => e.stopPropagation()}>
            <div className="px-5 py-3 border-b border-brand-border flex items-center justify-between">
              <div className="font-semibold">{editing.id ? t("Edit Email Mapping") : t("Add Email Mapping")}</div>
              <button className="p-1 rounded hover:bg-subtle" onClick={() => setEditing(null)}><X size={18} /></button>
            </div>
            <div className="p-5 space-y-4">
              {error && <div className="text-sm text-signal-red bg-red-50 border border-red-100 rounded-md px-3 py-2" role="alert">{error}</div>}
              <div>
                <div className="text-[10px] uppercase tracking-wider text-brand-muted font-semibold mb-1">{t("Supplier Dropdown *")}</div>
                <select
                  className="w-full border border-brand-border rounded-md px-3 py-2 text-sm bg-card"
                  value={editing.supplier_id ?? ""}
                  onChange={(event) => {
                    const supplierId = Number(event.target.value);
                    const supplier = supplierOptions.find((item) => item.id === supplierId);
                    setEditing({
                      ...editing,
                      supplier_id: supplier?.id,
                      supplier_name: supplier?.supplier_name ?? "",
                    });
                  }}
                >
                  <option value="">{t("Select supplier")}</option>
                  {supplierOptions.map((supplier) => (
                    <option key={supplier.id} value={supplier.id}>
                      {supplier.supplier_name}{supplier.is_active === false ? ` (${t("inactive")})` : ""}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <TagsInput ref={toRef} label={t("TO Emails *")} values={editing.to_emails ?? []} onChange={(values) => setEditing((cur) => (cur ? { ...cur, to_emails: values } : cur))} />
                <p className="mt-1 text-[11px] text-brand-muted">
                  {t("Each TO email gets a Supplier Portal login (a temporary password is emailed; they’re asked to change it on first login).")}
                </p>
              </div>
              <TagsInput ref={ccRef} label={t("CC Emails")} values={editing.cc_emails ?? []} onChange={(values) => setEditing((cur) => (cur ? { ...cur, cc_emails: values } : cur))} />
              <TagsInput ref={bccRef} label={t("BCC Emails")} values={editing.bcc_emails ?? []} onChange={(values) => setEditing((cur) => (cur ? { ...cur, bcc_emails: values } : cur))} />
              <TagsInput ref={escRef} label={t("Escalation Emails")} values={editing.escalation_emails ?? []} onChange={(values) => setEditing((cur) => (cur ? { ...cur, escalation_emails: values } : cur))} />

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <Field label={t("Contact Person")} value={editing.contact_person ?? ""} onChange={(value) => setEditing((cur) => (cur ? { ...cur, contact_person: value } : cur))} />
                <Field label={t("Phone")} value={editing.phone ?? ""} onChange={(value) => setEditing((cur) => (cur ? { ...cur, phone: value } : cur))} />
              </div>
              <Field label={t("Remarks")} value={editing.remarks ?? ""} onChange={(value) => setEditing((cur) => (cur ? { ...cur, remarks: value } : cur))} />
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={editing.is_active ?? true}
                  onChange={(event) => {
                    const checked = event.target.checked;
                    setEditing((cur) => (cur ? { ...cur, is_active: checked } : cur));
                  }}
                />
                {t("Active")}
              </label>
            </div>
            <div className="px-5 py-3 border-t border-brand-border flex items-center justify-end gap-2">
              <button className="btn-ghost" onClick={() => setEditing(null)}>{t("Cancel")}</button>
              <button className="btn-primary" disabled={busy} onClick={save}>
                {busy ? <RefreshCw size={14} className="animate-spin" /> : <Save size={14} />} {busy ? t("Saving…") : t("Save")}
              </button>
            </div>
          </div>
        </div>
      )}

      {loginsFor && canManageLogins && <SupplierLoginsModal mapping={loginsFor} onClose={() => setLoginsFor(null)} />}
      {showAudit && canViewAudit && <EmailAuditModal onClose={() => setShowAudit(false)} />}
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
    const { t } = useT();
    const [draft, setDraft] = useState("");
    const [error, setError] = useState<string | null>(null);

    const add = (raw: string) => {
      const parts = raw.split(",").map((part) => part.trim()).filter(Boolean);
      if (parts.length === 0) return;

      const next = [...values];
      for (const email of parts) {
        if (!isEmail(email)) {
          setError(t("{email} is not a valid email.", { email }));
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
  },
);

function isEmail(value: string) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
}

"use client";

import { useEffect, useState } from "react";
import { KeyRound, Power, RefreshCw, X } from "lucide-react";

import { api } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import type { SupplierEmail, SupplierLogin } from "@/lib/types";

export default function SupplierLoginsModal({
  mapping,
  onClose,
}: {
  mapping: SupplierEmail;
  onClose: () => void;
}) {
  const [logins, setLogins] = useState<SupplierLogin[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [tempResult, setTempResult] = useState<{ email: string; temp_password: string; emailed: boolean } | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      setLogins(await api.listSupplierLogins(mapping.supplier_id));
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mapping.supplier_id]);

  const reset = async (id: number) => {
    setBusyId(id);
    setTempResult(null);
    try {
      const res = await api.resetSupplierLogin(id);
      setTempResult({ email: res.email, temp_password: res.temp_password, emailed: res.emailed });
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusyId(null);
    }
  };

  const toggle = async (login: SupplierLogin) => {
    setBusyId(login.id);
    try {
      if (login.is_active) await api.deactivateSupplierLogin(login.id);
      else await api.activateSupplierLogin(login.id);
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/40 grid place-items-center p-4" onClick={onClose}>
      <div className="bg-white rounded-lg shadow-xl w-full max-w-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="px-5 py-3 border-b border-brand-border flex items-center justify-between">
          <div>
            <div className="font-semibold">Supplier Logins</div>
            <div className="text-xs text-brand-muted">{mapping.supplier_name}</div>
          </div>
          <button className="p-1 rounded hover:bg-gray-100" onClick={onClose}><X size={18} /></button>
        </div>

        <div className="p-5 space-y-4">
          {error && <div className="rounded-md bg-red-50 px-3 py-2 text-xs text-signal-red">{error}</div>}

          {tempResult && (
            <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
              New temporary password for <span className="font-semibold">{tempResult.email}</span>:{" "}
              <span className="font-mono font-semibold">{tempResult.temp_password}</span>
              {tempResult.emailed ? " — emailed to the supplier." : " — share it securely (email not sent)."}
            </div>
          )}

          <div className="table-shell">
            <table className="min-w-full text-sm">
              <thead className="bg-gray-50">
                <tr>
                  {["Email", "Active", "First login", "Last login", "Actions"].map((h) => (
                    <th key={h} className="px-3 py-2 text-left table-header whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {loading && <tr><td colSpan={5} className="px-3 py-8 text-center text-brand-muted">Loading…</td></tr>}
                {!loading && logins.length === 0 && (
                  <tr><td colSpan={5} className="px-3 py-8 text-center text-brand-muted">No logins yet. Saving the mapping creates one per TO email.</td></tr>
                )}
                {logins.map((l) => (
                  <tr key={l.id} className="border-t border-brand-border">
                    <td className="px-3 py-2">{l.email}</td>
                    <td className="px-3 py-2">
                      {l.is_active ? <span className="badge badge-track">YES</span> : <span className="badge badge-overdue">NO</span>}
                    </td>
                    <td className="px-3 py-2 text-xs">
                      {l.must_change_password ? <span className="badge badge-due">Pending change</span> : <span className="text-brand-muted">Done</span>}
                    </td>
                    <td className="px-3 py-2 text-xs text-brand-muted">{l.last_login_at ? fmtDate(l.last_login_at) : "—"}</td>
                    <td className="px-3 py-2">
                      <div className="flex items-center gap-1">
                        <button title="Reset password" disabled={busyId === l.id} onClick={() => reset(l.id)} className="p-1 rounded hover:bg-gray-100">
                          {busyId === l.id ? <RefreshCw size={14} className="animate-spin" /> : <KeyRound size={14} />}
                        </button>
                        <button title={l.is_active ? "Deactivate" : "Activate"} disabled={busyId === l.id} onClick={() => toggle(l)} className="p-1 rounded hover:bg-gray-100 text-brand-muted">
                          <Power size={14} className={l.is_active ? "text-emerald-600" : "text-signal-red"} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="px-5 py-3 border-t border-brand-border flex justify-end">
          <button className="btn-ghost" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  );
}

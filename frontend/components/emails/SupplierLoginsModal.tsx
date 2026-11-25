"use client";

import { useEffect, useRef, useState } from "react";
import { KeyRound, Power, RefreshCw, X } from "lucide-react";

import { api } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import type { SupplierEmail, SupplierLogin } from "@/lib/types";

const LOAD_TIMEOUT_MS = 20000;

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

  // Guards against a request that never answers (proxy/tunnel stall) leaving
  // the table on "Loading…" forever, and against setting state after close.
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  const load = async () => {
    setLoading(true);
    setError(null);
    let timer: ReturnType<typeof setTimeout> | undefined;
    try {
      const timeout = new Promise<never>((_, reject) => {
        timer = setTimeout(
          () => reject(new Error(`The server did not answer within ${LOAD_TIMEOUT_MS / 1000} seconds.`)),
          LOAD_TIMEOUT_MS,
        );
      });
      const rows = await Promise.race([api.listSupplierLogins(mapping.supplier_id), timeout]);
      if (!alive.current) return;
      if (!Array.isArray(rows)) throw new Error("Unexpected response from the server.");
      setLogins(rows);
    } catch (e) {
      if (!alive.current) return;
      setLogins([]);
      setError(`Could not load supplier logins: ${(e as Error).message || "unknown error"}`);
    } finally {
      if (timer) clearTimeout(timer);
      if (alive.current) setLoading(false);
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
    <div className="modal-overlay fixed inset-0 z-50 bg-black/40 grid place-items-center p-4" onClick={onClose}>
      <div className="modal-panel bg-card rounded-lg shadow-xl w-full max-w-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="px-5 py-3 border-b border-brand-border flex items-center justify-between">
          <div>
            <div className="font-semibold">Supplier Logins</div>
            <div className="text-xs text-brand-muted">{mapping.supplier_name}</div>
          </div>
          <button className="p-1 rounded hover:bg-subtle" onClick={onClose}><X size={18} /></button>
        </div>

        <div className="p-5 space-y-4">
          {error && (
            <div className="flex items-center justify-between gap-3 rounded-md bg-red-50 px-3 py-2 text-xs text-signal-red" role="alert">
              <span>{error}</span>
              <button className="btn-ghost text-xs" disabled={loading} onClick={() => void load()}>
                <RefreshCw size={12} /> Retry
              </button>
            </div>
          )}

          {tempResult && (
            <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
              New temporary password for <span className="font-semibold">{tempResult.email}</span>:{" "}
              <span className="font-mono font-semibold">{tempResult.temp_password}</span>
              {tempResult.emailed ? " — emailed to the supplier." : " — share it securely (email not sent)."}
            </div>
          )}

          <div className="table-shell">
            <table className="min-w-full text-sm">
              <thead className="bg-subtle">
                <tr>
                  {["Email", "Active", "First login", "Last login", "Actions"].map((h) => (
                    <th key={h} className="px-3 py-2 text-left table-header whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {loading && <tr><td colSpan={5} className="px-3 py-8 text-center text-brand-muted">Loading…</td></tr>}
                {!loading && !error && logins.length === 0 && (
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
                        <button title="Reset password" disabled={busyId === l.id} onClick={() => reset(l.id)} className="p-1 rounded hover:bg-subtle">
                          {busyId === l.id ? <RefreshCw size={14} className="animate-spin" /> : <KeyRound size={14} />}
                        </button>
                        <button title={l.is_active ? "Deactivate" : "Activate"} disabled={busyId === l.id} onClick={() => toggle(l)} className="p-1 rounded hover:bg-subtle text-brand-muted">
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

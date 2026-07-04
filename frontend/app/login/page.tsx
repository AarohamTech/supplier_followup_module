"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { Logo, ZanvarMark } from "@/components/brand/Logo";
import { useAuth } from "@/lib/auth";
import { api } from "@/lib/api";
import type { CompanyBrief } from "@/lib/types";

export default function LoginPage() {
  const { login } = useAuth();
  const router = useRouter();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const [companies, setCompanies] = useState<CompanyBrief[]>([]);
  const [companyCode, setCompanyCode] = useState<string>("");

  // Load the selectable companies (open endpoint) for the picker.
  useEffect(() => {
    let alive = true;
    api
      .listCompanies()
      .then((rows) => {
        if (!alive) return;
        setCompanies(rows);
        const preferred = rows.find((c) => c.theme === "red") ?? rows[0];
        if (preferred) setCompanyCode(preferred.code);
      })
      .catch(() => {
        /* picker just won't show; login still works with the default company */
      });
    return () => {
      alive = false;
    };
  }, []);

  // Preview the selected company's theme on <html> while on the login screen.
  useEffect(() => {
    if (typeof document === "undefined" || !companyCode) return;
    document.documentElement.setAttribute("data-company", companyCode);
  }, [companyCode]);

  const selected = companies.find((c) => c.code === companyCode) ?? null;
  const brandName = selected?.brand_name || "H-Connect";

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email.trim(), password, companyCode || undefined);
      router.replace("/");
    } catch (err) {
      setError((err as Error).message || "Login failed");
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-brand-surface px-4">
      <div className="w-full max-w-sm rounded-lg border border-brand-border bg-card p-8 shadow-card">
        <div className="mb-6 text-center">
          <div className="mx-auto mb-3 flex items-center justify-center gap-3">
            <ZanvarMark size={48} />
            <span className="flex h-16 w-16 items-center justify-center rounded-2xl bg-signal-red/10 text-signal-red">
              <Logo size={40} />
            </span>
          </div>
          <div className="text-sm font-bold tracking-tight text-brand-dark">{brandName}</div>
          <h1 className="text-lg font-bold text-signal-red">Supplier Follow-up Agent</h1>
          <p className="mt-1 text-xs text-brand-muted">Sign in to your account</p>
        </div>

        {companies.length > 1 && (
          <div className="mb-4">
            <label className="mb-1 block text-xs font-medium text-brand-dark">Company</label>
            <div className="grid grid-cols-2 gap-2">
              {companies.map((c) => {
                const active = c.code === companyCode;
                return (
                  <button
                    key={c.code}
                    type="button"
                    onClick={() => setCompanyCode(c.code)}
                    className={
                      active
                        ? "rounded-md border border-signal-red bg-signal-red/10 px-3 py-2 text-sm font-medium text-signal-red"
                        : "rounded-md border border-brand-border bg-card px-3 py-2 text-sm text-brand-muted hover:bg-subtle"
                    }
                  >
                    {c.display_name}
                  </button>
                );
              })}
            </div>
          </div>
        )}

        <form onSubmit={onSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block text-xs font-medium text-brand-dark">Email or username</label>
            <input
              type="text"
              required
              autoFocus
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="input"
              placeholder="you@example.com or PRAMOD"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-brand-dark">Password</label>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="input"
              placeholder="Password"
            />
          </div>

          {error && (
            <div className="rounded-md bg-signal-red/10 px-3 py-2 text-xs text-signal-red">{error}</div>
          )}

          <button type="submit" disabled={submitting} className="btn-primary w-full">
            {submitting && (
              <span className="text-white">
                <Logo size={16} animated />
              </span>
            )}
            {submitting ? "Signing in..." : "Sign in"}
          </button>
        </form>
      </div>
    </div>
  );
}

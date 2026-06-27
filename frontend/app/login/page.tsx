"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { Logo } from "@/components/brand/Logo";
import { useAuth } from "@/lib/auth";

export default function LoginPage() {
  const { login } = useAuth();
  const router = useRouter();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email.trim(), password);
      router.replace("/");
    } catch (err) {
      setError((err as Error).message || "Login failed");
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-brand-surface px-4">
      <div className="w-full max-w-sm rounded-lg border border-brand-border bg-white p-8 shadow-card">
        <div className="mb-6 text-center">
          <div className="mx-auto mb-3 flex h-16 w-16 items-center justify-center rounded-2xl bg-red-50 text-signal-red">
            <Logo size={40} />
          </div>
          <div className="text-sm font-bold tracking-tight text-brand-dark">
            Harmony <span className="font-semibold text-brand-muted">×</span> Hariom
          </div>
          <h1 className="text-lg font-bold text-signal-red">Supplier Follow-up Agent</h1>
          <p className="mt-1 text-xs text-brand-muted">Sign in to your account</p>
        </div>

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
            <div className="rounded-md bg-red-50 px-3 py-2 text-xs text-signal-red">{error}</div>
          )}

          <button
            type="submit"
            disabled={submitting}
            className="btn-primary w-full"
          >
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

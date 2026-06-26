"use client";

import { useCallback, useEffect, useState } from "react";
import { Wand2, Loader2, RotateCcw, Save } from "lucide-react";

import { LogoLoader } from "@/components/brand/Logo";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { AiPromptsMap } from "@/lib/types";

export default function AiPromptsPage() {
  const { hasRole } = useAuth();
  const isManager = hasRole("manager");

  const [prompts, setPrompts] = useState<AiPromptsMap>({});
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  const hydrate = useCallback((map: AiPromptsMap) => {
    setPrompts(map);
    setDrafts(Object.fromEntries(Object.entries(map).map(([k, p]) => [k, p.value])));
  }, []);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    api
      .getAiPrompts()
      .then((r) => hydrate(r.prompts))
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }, [hydrate]);

  useEffect(() => {
    if (isManager) load();
    else setLoading(false);
  }, [isManager, load]);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 2800);
    return () => clearTimeout(t);
  }, [toast]);

  const dirty = Object.keys(prompts).some((k) => (drafts[k] ?? "") !== prompts[k].value);

  const save = () => {
    setSaving(true);
    setError(null);
    // Value equal to the default → send null so it resets to default (not "custom").
    const payload: Record<string, string | null> = {};
    for (const [k, p] of Object.entries(prompts)) {
      const v = (drafts[k] ?? "").trim();
      payload[k] = !v || v === p.default.trim() ? null : v;
    }
    api
      .saveAiPrompts(payload)
      .then((r) => {
        hydrate(r.prompts);
        setToast("Prompts saved. New Harmony Intelligent output uses them immediately.");
      })
      .catch((e) => setError((e as Error).message))
      .finally(() => setSaving(false));
  };

  if (!isManager) {
    return (
      <div className="empty-state">Manager access required to edit Harmony Intelligent prompts.</div>
    );
  }

  return (
    <div className="page-stack">
      <div className="page-header">
        <div className="flex items-center gap-2">
          <span className="icon-tile bg-violet-100 text-violet-700">
            <Wand2 size={16} />
          </span>
          <div>
            <h1 className="page-title">Harmony Intelligent Prompts</h1>
            <p className="page-subtitle">
              Tune how Harmony Intelligent writes — changes apply to new output instantly, no deploy needed.
            </p>
          </div>
        </div>
        <div className="page-actions">
          {toast && <span className="rounded-md bg-brand-dark px-3 py-1.5 text-xs text-white">{toast}</span>}
          <button onClick={save} disabled={saving || !dirty} className="btn-primary disabled:opacity-50">
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
            Save changes
          </button>
        </div>
      </div>

      {error && <div className="rounded-md bg-red-50 px-3 py-2 text-xs text-signal-red">{error}</div>}

      {loading ? (
        <div className="empty-state">
          <LogoLoader size={56} label="Loading prompts…" />
        </div>
      ) : (
        <div className="space-y-4">
          {Object.entries(prompts).map(([key, p]) => {
            const value = drafts[key] ?? "";
            const changed = value !== p.value;
            const atDefault = value.trim() === p.default.trim();
            return (
              <div key={key} className="card p-4">
                <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <div className="text-sm font-semibold text-brand-dark">{p.label}</div>
                    <div className="text-[11px] text-brand-muted">
                      <code className="rounded bg-gray-100 px-1">{key}</code>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span
                      className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                        p.is_custom ? "bg-violet-100 text-violet-700" : "bg-gray-100 text-brand-muted"
                      }`}
                    >
                      {p.is_custom ? "Custom" : "Default"}
                    </span>
                    <button
                      type="button"
                      onClick={() => setDrafts((d) => ({ ...d, [key]: p.default }))}
                      disabled={atDefault}
                      className="inline-flex items-center gap-1 text-[11px] text-brand-muted hover:text-brand-dark disabled:opacity-40"
                      title="Reset this prompt to the built-in default"
                    >
                      <RotateCcw className="h-3 w-3" /> Reset to default
                    </button>
                  </div>
                </div>
                <textarea
                  value={value}
                  onChange={(e) => setDrafts((d) => ({ ...d, [key]: e.target.value }))}
                  rows={5}
                  className="w-full resize-y rounded-md border border-brand-border bg-white px-3 py-2 text-xs leading-relaxed text-brand-dark outline-none focus:border-violet-400"
                />
                <div className="mt-1 flex items-center justify-between text-[10px] text-brand-muted">
                  <span>{value.length} chars</span>
                  {changed && <span className="text-violet-600">● unsaved change</span>}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

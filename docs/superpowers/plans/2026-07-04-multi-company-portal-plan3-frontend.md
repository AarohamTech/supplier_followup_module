# Multi-Company Portal — Plan 3: Frontend (Login Picker, Switcher, Light-Blue Theme) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the frontend a company picker at login, a top-bar company switcher for staff, and a light-blue Enterprise (101) theme + branding — running on the already-merged Plan 1/2 backend (`/api/auth/companies`, login `company` claim, `POST /api/auth/switch-company`).

**Architecture:** The whole app is themed by CSS variables on `<html>` (`--brand-red`, `--signal-red`, `--focus-ring`, etc.). We add a `data-company` attribute on `<html>` and a `[data-company="101"]` variable override (light-blue) — no component restyle needed. The active company (a `CompanyBrief`) is tracked in the auth context, persisted to `localStorage`, and applied to `<html>` on login/switch/reload. Login gains a company toggle (from `GET /api/auth/companies`); the top bar gains a switcher (`POST /api/auth/switch-company`).

**Tech Stack:** Next.js 14 (app router), React, TypeScript, Tailwind (CSS-variable driven), Zustand (existing theme store). No new dependencies.

## Global Constraints

- **Run frontend tooling from `frontend/`.** Verify each task with `npx tsc --noEmit` (fast typecheck); the final task runs `npm run build` (Next production build). There is **no** frontend unit-test framework in this repo — typecheck + build passing is the acceptance gate (matches `docs/progress.md` convention).
- **102 (Hariom Tech) is the default and must look/behave exactly as today** when no company or company `102` is active (red theme, "H-Connect"). The blue theme applies only under `data-company="101"`.
- **Portal accounts (supplier/employee) are pinned server-side** — the login picker is harmless for them (the backend ignores the requested company for portal accounts). The top-bar switcher shows only for staff accounts (`supplier_id == null && emp_code == null`).
- **Follow existing patterns:** API calls go through the `http<T>()` helper in `lib/api.ts`; auth state lives in `lib/auth.tsx`; theme tokens live in `app/globals.css`; the token store is `lib/auth-token.ts`.
- **No new dependencies.**
- Backend contracts (already live): `GET /api/auth/companies` → `CompanyBrief[]` (open); `POST /api/auth/login` body may include `company` (code string); response is `LoginResponse` now carrying `company: CompanyBrief | null`; `POST /api/auth/switch-company` body `{company: code}` → `LoginResponse`.
- `CompanyBrief` = `{ code: string; display_name: string; theme: string; brand_name: string; logo_url?: string | null }`.

---

### Task 1: Types + API client

**Files:**
- Modify: `frontend/lib/types.ts` (add `CompanyBrief`; add `company` to `LoginResponse`)
- Modify: `frontend/lib/api.ts` (extend `login`; add `listCompanies`, `switchCompany`)

**Interfaces:**
- Produces:
  - `CompanyBrief` type.
  - `LoginResponse.company?: CompanyBrief | null`.
  - `api.listCompanies(): Promise<CompanyBrief[]>`
  - `api.login(identifier, password, company?): Promise<LoginResponse>` (adds `company` to the request body when provided).
  - `api.switchCompany(company: string): Promise<LoginResponse>`

- [ ] **Step 1: Add the type + extend `LoginResponse`**

In `frontend/lib/types.ts`, in the `// ─── Auth / Users ───` section (right before `LoginResponse`), add:

```typescript
export interface CompanyBrief {
  code: string;
  display_name: string;
  theme: string;      // "red" (Hariom) | "blue" (Enterprise)
  brand_name: string;
  logo_url?: string | null;
}
```

And change `LoginResponse` to include the active company:

```typescript
export interface LoginResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: AuthUser;
  company?: CompanyBrief | null;
}
```

- [ ] **Step 2: Extend the API client**

In `frontend/lib/api.ts`, add `CompanyBrief` to the type import block (with the other `from "./types"` imports). Replace the `login` helper and add two more (in the `// ─── Auth ───` section):

```typescript
  login: (identifier: string, password: string, company?: string) => {
    // Staff/suppliers sign in by email; employees by username (no '@').
    const base = identifier.includes("@")
      ? { email: identifier, password }
      : { username: identifier, password };
    const body = company ? { ...base, company } : base;
    return http<LoginResponse>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  listCompanies: () => http<CompanyBrief[]>("/api/auth/companies"),

  switchCompany: (company: string) =>
    http<LoginResponse>("/api/auth/switch-company", {
      method: "POST",
      body: JSON.stringify({ company }),
    }),
```

- [ ] **Step 3: Typecheck**

Run (from `frontend/`): `npx tsc --noEmit`
Expected: no errors (the new `company` field is optional, so existing call sites still compile).

- [ ] **Step 4: Commit**

```bash
git add frontend/lib/types.ts frontend/lib/api.ts
git commit -m "feat(mc-fe): CompanyBrief type + companies/switch-company API client"
```

---

### Task 2: Active-company state, persistence, and theming in auth context

**Files:**
- Modify: `frontend/lib/auth.tsx`
- Test: (typecheck only)

**Interfaces:**
- Consumes: `api.login`, `api.switchCompany`, `CompanyBrief` (Task 1).
- Produces (on the `useAuth()` value):
  - `company: CompanyBrief | null`
  - `login(identifier, password, company?) : Promise<void>` (now takes an optional company)
  - `switchCompany(code: string): Promise<void>`
  - Applies `document.documentElement` `data-company` = the active company code on login/switch/hydrate; clears it on logout. Persists the active company to `localStorage` (`"active_company"`) so a reload keeps the theme (the `/auth/me` response does not carry the company).

- [ ] **Step 1: Implement**

Replace the body of `frontend/lib/auth.tsx` with this (keeps `roleAtLeast` + the same exports, adds company handling):

```tsx
"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import type { AuthUser, CompanyBrief, Role } from "./types";
import { api } from "./api";
import { getToken, setToken } from "./auth-token";

const ROLE_RANK: Record<Role, number> = { viewer: 1, user: 2, manager: 3, admin: 4 };

export function roleAtLeast(role: Role | "supplier" | "employee" | undefined | null, minimum: Role): boolean {
  if (!role) return false;
  return (ROLE_RANK[role as Role] ?? 0) >= (ROLE_RANK[minimum] ?? 0);
}

const COMPANY_KEY = "active_company";

function loadCompany(): CompanyBrief | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(COMPANY_KEY);
    return raw ? (JSON.parse(raw) as CompanyBrief) : null;
  } catch {
    return null;
  }
}

function persistCompany(company: CompanyBrief | null): void {
  if (typeof window === "undefined") return;
  try {
    if (company) localStorage.setItem(COMPANY_KEY, JSON.stringify(company));
    else localStorage.removeItem(COMPANY_KEY);
  } catch {
    /* private mode — non-fatal */
  }
}

/** Apply the active company to <html data-company> so the CSS-variable theme swaps. */
function applyCompany(company: CompanyBrief | null): void {
  if (typeof document === "undefined") return;
  const el = document.documentElement;
  if (company?.code) el.setAttribute("data-company", company.code);
  else el.removeAttribute("data-company");
}

interface AuthState {
  user: AuthUser | null;
  company: CompanyBrief | null;
  loading: boolean;
  login: (identifier: string, password: string, company?: string) => Promise<void>;
  switchCompany: (code: string) => Promise<void>;
  logout: () => void;
  refresh: () => Promise<void>;
  hasRole: (minimum: Role) => boolean;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [company, setCompany] = useState<CompanyBrief | null>(null);
  const [loading, setLoading] = useState(true);

  const setActiveCompany = useCallback((c: CompanyBrief | null) => {
    setCompany(c);
    persistCompany(c);
    applyCompany(c);
  }, []);

  const refresh = useCallback(async () => {
    if (!getToken()) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      const me = await api.me();
      setUser(me);
      // /auth/me doesn't return the company; restore it from localStorage + theme.
      const stored = loadCompany();
      setCompany(stored);
      applyCompany(stored);
    } catch {
      setToken(null);
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const login = useCallback(
    async (identifier: string, password: string, companyCode?: string) => {
      const res = await api.login(identifier, password, companyCode);
      setToken(res.access_token);
      setUser(res.user);
      setActiveCompany(res.company ?? null);
    },
    [setActiveCompany],
  );

  const switchCompany = useCallback(
    async (code: string) => {
      const res = await api.switchCompany(code);
      setToken(res.access_token);
      setUser(res.user);
      setActiveCompany(res.company ?? null);
    },
    [setActiveCompany],
  );

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
    setActiveCompany(null);
    if (typeof window !== "undefined") window.location.href = "/login";
  }, [setActiveCompany]);

  const hasRole = useCallback((minimum: Role) => roleAtLeast(user?.role, minimum), [user]);

  const value = useMemo<AuthState>(
    () => ({ user, company, loading, login, switchCompany, logout, refresh, hasRole }),
    [user, company, loading, login, switchCompany, logout, refresh, hasRole],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within <AuthProvider>");
  return ctx;
}
```

- [ ] **Step 2: Typecheck**

Run (from `frontend/`): `npx tsc --noEmit`
Expected: FAILS in `app/login/page.tsx` (it calls `login(email, password)` — still valid since `company` is optional, so this should actually pass) — confirm no NEW type errors. If `tsc` reports an error about `switchCompany`/`company` not existing on the context, that's expected to be consumed in Tasks 4-5; the context itself must compile clean here.
Expected: PASS (the added fields are additive; `login`'s 3rd arg is optional).

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/auth.tsx
git commit -m "feat(mc-fe): track active company in auth context (persist + apply data-company theme)"
```

---

### Task 3: Light-blue Enterprise theme

**Files:**
- Modify: `frontend/app/globals.css`

**Interfaces:**
- Produces: `[data-company="101"]` CSS-variable overrides that repaint the red brand accent light-blue, for both light and dark palettes. No component changes — every `--brand-red`/`--signal-red`/`--focus-ring` consumer re-themes automatically.

- [ ] **Step 1: Add the overrides**

In `frontend/app/globals.css`, inside `@layer base` (right after the `.dark { ... }` block, before `html { ... }`), add:

```css
  /* Company 101 (Enterprise) — light-blue accent. Applied via <html data-company="101">.
     Only the red-accent tokens are re-pointed; signal green/yellow/black stay as-is. */
  :root[data-company="101"] {
    --brand-red: 37 99 235;   /* blue-600 */
    --signal-red: 37 99 235;
    --focus-ring: 37 99 235;
  }
  .dark[data-company="101"] {
    --brand-red: 96 165 250;  /* blue-400 — brighter for dark contrast */
    --signal-red: 96 165 250;
    --focus-ring: 96 165 250;
  }
```

- [ ] **Step 2: Typecheck (CSS has no types; run the build guard)**

Run (from `frontend/`): `npx tsc --noEmit`
Expected: PASS (CSS-only change; no TS impact).

- [ ] **Step 3: Commit**

```bash
git add frontend/app/globals.css
git commit -m "feat(mc-fe): light-blue Enterprise theme via [data-company=101] variables"
```

---

### Task 4: Login company picker + branding

**Files:**
- Modify: `frontend/app/login/page.tsx`

**Interfaces:**
- Consumes: `api.listCompanies`, `useAuth().login`, `CompanyBrief`.
- Produces: a segmented company toggle on the login screen; the chosen company's `code` is passed to `login(...)`; the brand name shown updates to the selected company's `brand_name`; selecting a company previews its theme (`data-company` on `<html>`).

- [ ] **Step 1: Implement**

Replace `frontend/app/login/page.tsx` with:

```tsx
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
        /* picker just won't show; login still works with default company */
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
```

Notes: `bg-red-50` was swapped to `bg-signal-red/10` in two spots so those tints follow the theme (blue under 101). The picker only renders when more than one company exists — so a single-company deploy looks exactly like today.

- [ ] **Step 2: Typecheck**

Run (from `frontend/`): `npx tsc --noEmit`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/login/page.tsx
git commit -m "feat(mc-fe): login company picker + per-company branding/theme preview"
```

---

### Task 5: Top-bar company display + switcher (staff)

**Files:**
- Modify: `frontend/components/layout/Topbar.tsx`

**Interfaces:**
- Consumes: `useAuth()` (`user`, `company`, `switchCompany`), `api.listCompanies`.
- Produces: the top bar shows the active company's `brand_name` (falling back to "H-Connect"); staff accounts get a small dropdown to switch company (calls `switchCompany`, then reloads so all data re-fetches under the new company). Portal accounts (supplier/employee) see the name but no switcher.

- [ ] **Step 1: Implement**

Replace `frontend/components/layout/Topbar.tsx` with:

```tsx
"use client";

import { useEffect, useState } from "react";
import { ChevronDown, LogOut, Menu } from "lucide-react";
import Link from "next/link";

import { Logo, ZanvarMark } from "@/components/brand/Logo";
import { useAuth } from "@/lib/auth";
import { api } from "@/lib/api";
import type { CompanyBrief } from "@/lib/types";
import NotificationBell from "@/components/NotificationBell";
import ThemeToggle from "@/components/layout/ThemeToggle";

const ROLE_LABEL: Record<string, string> = {
  admin: "Administrator",
  manager: "Manager",
  user: "User",
  viewer: "Viewer",
};

function CompanySwitcher() {
  const { company, switchCompany } = useAuth();
  const [companies, setCompanies] = useState<CompanyBrief[]>([]);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let alive = true;
    api
      .listCompanies()
      .then((rows) => alive && setCompanies(rows))
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, []);

  const current = company?.brand_name || company?.display_name || "H-Connect";
  if (companies.length <= 1) {
    return <span className="hidden text-xs font-semibold text-brand-dark sm:inline">{current}</span>;
  }

  const pick = async (code: string) => {
    if (busy || code === company?.code) {
      setOpen(false);
      return;
    }
    setBusy(true);
    try {
      await switchCompany(code);
      // Reload so every page re-fetches its data under the new company.
      if (typeof window !== "undefined") window.location.reload();
    } finally {
      setBusy(false);
      setOpen(false);
    }
  };

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        disabled={busy}
        className="inline-flex items-center gap-1 rounded-md border border-brand-border bg-card px-2.5 py-1.5 text-xs font-semibold text-brand-dark hover:bg-subtle"
      >
        {current}
        <ChevronDown size={14} className="text-brand-muted" />
      </button>
      {open && (
        <div className="absolute right-0 z-40 mt-1 w-44 overflow-hidden rounded-md border border-brand-border bg-card shadow-card animate-slide-down">
          {companies.map((c) => (
            <button
              key={c.code}
              type="button"
              onClick={() => pick(c.code)}
              className={
                c.code === company?.code
                  ? "block w-full px-3 py-2 text-left text-xs font-semibold text-signal-red bg-signal-red/10"
                  : "block w-full px-3 py-2 text-left text-xs text-brand-dark hover:bg-subtle"
              }
            >
              {c.display_name}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export default function Topbar({ onMenuClick }: { onMenuClick?: () => void }) {
  const { user, company, logout } = useAuth();
  const name = user?.full_name || user?.email || "User";
  const initial = name.charAt(0).toUpperCase();
  const isStaff = !!user && user.supplier_id == null && user.emp_code == null;
  const brandName = company?.brand_name || "H-Connect";

  return (
    <header className="sticky top-0 z-30 border-b border-brand-border bg-card">
      <div className="mx-auto flex h-16 max-w-[1600px] items-center gap-2 px-4 sm:gap-4 sm:px-6 lg:px-8">
        <button
          type="button"
          onClick={onMenuClick}
          className="grid h-9 w-9 place-items-center rounded-md text-brand-muted hover:bg-subtle hover:text-brand-dark md:hidden"
          aria-label="Open navigation"
        >
          <Menu size={18} />
        </button>
        <Link href="/" className="flex min-w-0 items-center gap-2 sm:gap-3" aria-label="Home">
          <ZanvarMark size={32} />
          <span className="shrink-0 text-signal-red">
            <Logo size={30} />
          </span>
          <div className="flex min-w-0 flex-col">
            <span className="truncate text-sm font-semibold leading-tight text-brand-dark sm:text-[15px]">
              {brandName}
            </span>
            <span className="hidden text-xs text-brand-muted leading-tight sm:block">
              Industrial procurement control tower
            </span>
          </div>
        </Link>
        <div className="flex-1" />
        {isStaff && <CompanySwitcher />}
        <ThemeToggle />
        <NotificationBell />
        <div className="hidden h-6 w-px bg-brand-border sm:block" />
        <div className="flex items-center gap-1 sm:gap-2.5">
          <div className="hidden text-right sm:block">
            <div className="text-sm font-medium">{name}</div>
            <div className="text-[10px] uppercase text-brand-muted tracking-wider">
              {ROLE_LABEL[user?.role ?? ""] ?? user?.role}
            </div>
          </div>
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-signal-red/10 text-xs font-semibold text-signal-red ring-1 ring-inset ring-signal-red/20">
            {initial}
          </div>
          <button
            onClick={logout}
            title="Sign out"
            className="grid h-9 w-9 place-items-center rounded-md text-brand-muted hover:bg-subtle hover:text-signal-red"
          >
            <LogOut size={18} />
          </button>
        </div>
      </div>
    </header>
  );
}
```

Notes: `AuthUser` (in `types.ts`) already has `supplier_id?`/`emp_code?` fields (used for the `isStaff` check — verify the exact field names in `types.ts` `AuthUser` and match them; if they're named differently, use those). The avatar's `bg-red-50`/`ring-red-100` were swapped to `signal-red/10`/`signal-red/20` so they follow the theme.

- [ ] **Step 2: Typecheck**

Run (from `frontend/`): `npx tsc --noEmit`
Expected: PASS. If `user.supplier_id`/`user.emp_code` don't exist on `AuthUser`, read `types.ts` for the real field names and adjust the `isStaff` expression, then re-run.

- [ ] **Step 3: Commit**

```bash
git add frontend/components/layout/Topbar.tsx
git commit -m "feat(mc-fe): top-bar company name + staff company switcher"
```

---

### Task 6: Production build verification

**Files:** none (verification only)

- [ ] **Step 1: Full typecheck + production build**

Run (from `frontend/`):
```bash
npx tsc --noEmit
npm run build
```
Expected: `tsc` clean; `next build` succeeds (all routes compile, including `/login`). Report any error and fix in the owning task's file.

- [ ] **Step 2: Manual visual check (dev server)**

```bash
# from frontend/ (backend must be reachable per NEXT_PUBLIC_API_BASE)
npm run dev
```
Verify by eye:
1. `/login` shows the **Company** toggle (Enterprise / Hariom Tech) when both exist; picking **Enterprise** turns the accent **light-blue**; picking **Hariom Tech** is **red**; the brand name updates.
2. Log in as staff with **Hariom Tech** → app is red, top bar shows "H-Connect" + a switcher.
3. Use the top-bar switcher → **Enterprise** → page reloads, app is **light-blue**, top bar shows "Enterprise", and the data shown is 101's (empty until 101 has data).
4. Reload the page → the light-blue theme persists (from `localStorage`).
5. Log out → theme resets to red; `/login` clean.

- [ ] **Step 3: Commit (if any fixes were needed)**

```bash
git add -A frontend/
git commit -m "fix(mc-fe): Plan 3 build/typecheck fixes"
```
(If no fixes were needed, skip this commit.)

---

## Self-Review

**1. Spec coverage (against the design doc's Plan 3 scope):**
- Login company picker → Task 4. ✅
- Top-bar company switcher (staff only) → Task 5. ✅
- Light-blue Enterprise theme → Tasks 2 (apply `data-company`) + 3 (blue variables). ✅
- Company-driven branding (name) → Tasks 4, 5. ✅
- Persist active company across reloads (since `/auth/me` lacks it) → Task 2 (localStorage). ✅
- 102 unchanged when single-company / company 102 → picker hidden when ≤1 company; blue only under `data-company="101"`. ✅

**2. Placeholder scan:** No TBD/TODO. Two spots say "verify the exact `AuthUser` field names in `types.ts` and match them" (`supplier_id`/`emp_code`) — a named-file lookup, not missing implementation.

**3. Type consistency:** `CompanyBrief`, `LoginResponse.company`, `api.listCompanies`, `api.switchCompany`, `api.login(…, company?)`, `useAuth().company`, `useAuth().switchCompany`, `useAuth().login(…, company?)`, `data-company`, `active_company` (localStorage key) are named identically across the tasks that define and consume them. ✅

**Risk note:** All changes are additive and behind a `>1 company` guard or `data-company="101"`, so a single-company (102-only) deploy is visually unchanged. The only shared-file edits are `types.ts`/`api.ts`/`auth.tsx` (additive) and `globals.css` (new scoped rules).

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-07-04-multi-company-portal-plan3-frontend.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — fresh subagent per task, review between tasks (verify = `tsc`/`build`, not pytest).

**2. Inline Execution** — batch execution with checkpoints.

**Which approach?**

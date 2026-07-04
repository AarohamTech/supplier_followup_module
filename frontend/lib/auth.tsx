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

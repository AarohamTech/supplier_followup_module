"use client";
import { create } from "zustand";
import api from "@/lib/api";
import type {
  ProcurementRecord, ProcurementListResponse, DashboardKpis,
  SupplierMaster, SupplierEmail, ProcurementFilters,
} from "@/lib/types";

// 'staff' → the global PO Follow-ups page (all POs, /api/procurement).
// 'employee' → the employee portal page (owned POs only, /api/eportal/procurement).
// Same store, same components; only the data source differs.
type Scope = "staff" | "employee";

interface State {
  kpis?: DashboardKpis;
  list?: ProcurementListResponse;
  supplierMasters: SupplierMaster[];
  suppliers: SupplierEmail[];
  filters: ProcurementFilters;
  scope: Scope;
  loading: boolean;
  error?: string;
  supplierError?: string;
  selectedRecordId?: number;
  selectedPoKey?: { supplier_name: string; supplier_po_no: string };

  setFilters: (p: Partial<ProcurementFilters>) => void;
  clearFilters: () => void;
  setScope: (scope: Scope) => void;
  refresh: () => Promise<void>;
  loadSuppliers: () => Promise<void>;
  selectRecord: (id?: number) => void;
  selectPoGroup: (key?: { supplier_name: string; supplier_po_no: string }) => void;
}

export const useStore = create<State>((set, get) => ({
  supplierMasters: [],
  suppliers: [],
  filters: { page: 1, size: 25 },
  scope: "staff",
  loading: false,

  setFilters: (p) => {
    set({ filters: { ...get().filters, ...p, page: p.page ?? 1 } });
    void get().refresh();
  },
  clearFilters: () => {
    set({ filters: { page: 1, size: 25 } });
    void get().refresh();
  },
  // Switch the data source for the PO Follow-ups page. Does NOT auto-refresh:
  // the page sets scope then calls refresh() so the right endpoints are hit.
  setScope: (scope) => set({ scope }),
  selectRecord: (id) => set({ selectedRecordId: id, selectedPoKey: undefined }),
  selectPoGroup: (key) => set({ selectedPoKey: key, selectedRecordId: undefined }),

  refresh: async () => {
    set({ loading: true, error: undefined });
    const employee = get().scope === "employee";
    try {
      const [kpis, list] = await Promise.all([
        employee ? api.eportalDashboard() : api.dashboard(),
        employee ? api.eportalProcurement(get().filters) : api.listProcurement(get().filters),
      ]);
      set({ kpis, list, loading: false });
    } catch (e: any) {
      set({ error: e.message ?? "Failed to load data", loading: false });
    }
  },

  loadSuppliers: async () => {
    try {
      const [supplierMasters, suppliers] = await Promise.all([
        api.listSuppliers(),
        api.listSupplierEmails(),
      ]);
      set({ supplierMasters, suppliers });
    } catch (e: any) {
      // Keep this separate from `error` so a supplier-load failure doesn't
      // overwrite a procurement-data error (they run concurrently).
      set({ supplierError: e.message });
    }
  },
}));

"use client";
import { create } from "zustand";
import api from "@/lib/api";
import type {
  ProcurementRecord, ProcurementListResponse, DashboardKpis,
  SupplierMaster, SupplierEmail, ProcurementFilters,
} from "@/lib/types";

interface State {
  kpis?: DashboardKpis;
  list?: ProcurementListResponse;
  supplierMasters: SupplierMaster[];
  suppliers: SupplierEmail[];
  filters: ProcurementFilters;
  loading: boolean;
  error?: string;
  selectedRecordId?: number;
  selectedPoKey?: { supplier_name: string; supplier_po_no: string };

  setFilters: (p: Partial<ProcurementFilters>) => void;
  clearFilters: () => void;
  refresh: () => Promise<void>;
  loadSuppliers: () => Promise<void>;
  selectRecord: (id?: number) => void;
  selectPoGroup: (key?: { supplier_name: string; supplier_po_no: string }) => void;
}

export const useStore = create<State>((set, get) => ({
  supplierMasters: [],
  suppliers: [],
  filters: { page: 1, size: 25 },
  loading: false,

  setFilters: (p) => {
    set({ filters: { ...get().filters, ...p, page: p.page ?? 1 } });
    void get().refresh();
  },
  clearFilters: () => {
    set({ filters: { page: 1, size: 25 } });
    void get().refresh();
  },
  selectRecord: (id) => set({ selectedRecordId: id, selectedPoKey: undefined }),
  selectPoGroup: (key) => set({ selectedPoKey: key, selectedRecordId: undefined }),

  refresh: async () => {
    set({ loading: true, error: undefined });
    try {
      const [kpis, list] = await Promise.all([
        api.dashboard(),
        api.listProcurement(get().filters),
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
      set({ error: e.message });
    }
  },
}));

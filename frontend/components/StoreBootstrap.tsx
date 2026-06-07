"use client";
import { useEffect } from "react";
import { useStore } from "@/lib/store";

/** Mounts once at the root and keeps store in sync. */
export default function StoreBootstrap() {
  const refresh = useStore((s) => s.refresh);
  const loadSuppliers = useStore((s) => s.loadSuppliers);
  useEffect(() => {
    void refresh();
    void loadSuppliers();
  }, [refresh, loadSuppliers]);
  return null;
}

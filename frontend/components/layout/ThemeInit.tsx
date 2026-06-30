"use client";

import { useEffect } from "react";
import { useTheme } from "@/lib/theme";

/** Mounts once at the app root to sync the theme store with localStorage + OS.
 * The actual <html class="dark"> is set pre-paint by the inline script in
 * layout.tsx (no flash); this just keeps the store/toggle in sync. */
export default function ThemeInit() {
  const init = useTheme((s) => s.init);
  useEffect(() => {
    init();
  }, [init]);
  return null;
}

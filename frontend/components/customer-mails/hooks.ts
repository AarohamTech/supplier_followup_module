"use client";

import { useEffect, useRef, useState } from "react";

/**
 * Flip to `true` temporarily while debugging to log render counts per
 * component. Keep `false` in normal use so the console stays clean and there is
 * zero runtime cost.
 */
export const RENDER_DEBUG = false;

/** Logs how many times a component has rendered (only when RENDER_DEBUG). */
export function useRenderCount(name: string) {
  const count = useRef(0);
  count.current += 1;
  if (RENDER_DEBUG) {
    // eslint-disable-next-line no-console
    console.log(`[render] ${name} #${count.current}`);
  }
}

/** Returns a value that only updates after `delay` ms of no changes. */
export function useDebouncedValue<T>(value: T, delay = 300): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(id);
  }, [value, delay]);
  return debounced;
}

/** Runs a debounced side effect (e.g. autosave) without re-rendering. */
export function useDebouncedCallback<A extends unknown[]>(
  fn: (...args: A) => void,
  delay = 600,
) {
  const fnRef = useRef(fn);
  fnRef.current = fn;
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );

  return useRef((...args: A) => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => fnRef.current(...args), delay);
  }).current;
}

/** True only on the date matching today (local time). */
export function isToday(value: string | null | undefined): boolean {
  if (!value) return false;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return false;
  const now = new Date();
  return (
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate()
  );
}

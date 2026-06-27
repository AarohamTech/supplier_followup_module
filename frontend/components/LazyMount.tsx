"use client";

import { useEffect, useRef, useState } from "react";

/**
 * Defers rendering (and therefore the data-fetching) of its children until they
 * scroll near the viewport. Keeps the initial page paint fast by not firing a
 * burst of API calls for below-the-fold widgets at once — which matters more
 * here because the DB is cross-region (each call has real latency).
 */
export default function LazyMount({
  children,
  minHeight = 200,
}: {
  children: React.ReactNode;
  minHeight?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [show, setShow] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el || show) return;
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          setShow(true);
          io.disconnect();
        }
      },
      { rootMargin: "250px" },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [show]);

  return (
    <div ref={ref} style={show ? undefined : { minHeight }}>
      {show ? children : null}
    </div>
  );
}

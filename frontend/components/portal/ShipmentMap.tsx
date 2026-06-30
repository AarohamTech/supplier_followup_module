"use client";

import dynamic from "next/dynamic";
import type { AsnEvent } from "@/lib/types";

// Leaflet touches `window`, so the actual map must never render on the server.
const ShipmentMapInner = dynamic(() => import("./ShipmentMapInner"), {
  ssr: false,
  loading: () => (
    <div className="grid h-64 place-items-center rounded-lg border border-brand-border bg-subtle text-xs text-brand-muted">
      Loading map…
    </div>
  ),
});

export default function ShipmentMap({ events }: { events: AsnEvent[] }) {
  return <ShipmentMapInner events={events} />;
}

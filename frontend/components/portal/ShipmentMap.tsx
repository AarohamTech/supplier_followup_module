"use client";

import dynamic from "next/dynamic";
import { useT } from "@/lib/i18n";
import type { AsnEvent } from "@/lib/types";

function MapLoading() {
  const { t } = useT();
  return (
    <div className="grid h-64 place-items-center rounded-lg border border-brand-border bg-subtle text-xs text-brand-muted">
      {t("Loading map…")}
    </div>
  );
}

// Leaflet touches `window`, so the actual map must never render on the server.
const ShipmentMapInner = dynamic(() => import("./ShipmentMapInner"), {
  ssr: false,
  loading: () => <MapLoading />,
});

export default function ShipmentMap({ events }: { events: AsnEvent[] }) {
  return <ShipmentMapInner events={events} />;
}

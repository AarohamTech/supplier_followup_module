"use client";

import { useMemo } from "react";
import { MapContainer, Marker, Polyline, Popup, TileLayer } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

import { fmtDate } from "@/lib/format";
import type { AsnEvent } from "@/lib/types";

// Fix the default marker icon paths (broken under bundlers like Next/webpack).
const icon = L.icon({
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowSize: [41, 41],
});

type Point = { lat: number; lng: number; label: string; sub: string };

export default function ShipmentMapInner({ events }: { events: AsnEvent[] }) {
  const points = useMemo<Point[]>(() => {
    return [...events]
      .filter((e) => e.lat != null && e.lng != null)
      .sort((a, b) => +new Date(a.occurred_at) - +new Date(b.occurred_at))
      .map((e) => ({
        lat: Number(e.lat),
        lng: Number(e.lng),
        label: e.location || e.status_label || e.stage,
        sub: `${e.status_label || e.stage} · ${fmtDate(e.occurred_at)}`,
      }));
  }, [events]);

  if (points.length === 0) {
    return (
      <div className="grid h-64 place-items-center rounded-lg border border-brand-border bg-subtle text-xs text-brand-muted">
        No mappable checkpoints yet.
      </div>
    );
  }

  const latest = points[points.length - 1];
  const line: [number, number][] = points.map((p) => [p.lat, p.lng]);
  // Rough fit: center on the latest point; Leaflet handles a sensible zoom.
  const center: [number, number] = [latest.lat, latest.lng];

  return (
    <div className="h-64 overflow-hidden rounded-lg border border-brand-border">
      <MapContainer center={center} zoom={5} scrollWheelZoom={false} style={{ height: "100%", width: "100%" }}>
        <TileLayer
          attribution='&copy; OpenStreetMap contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        {line.length > 1 && <Polyline positions={line} pathOptions={{ color: "#e11d2e", weight: 3 }} />}
        {points.map((p, i) => (
          <Marker key={i} position={[p.lat, p.lng]} icon={icon}>
            <Popup>
              <div className="text-xs">
                <div className="font-semibold">{p.label}</div>
                <div>{p.sub}</div>
                {i === points.length - 1 && <div className="mt-1 font-medium text-rose-600">Current location</div>}
              </div>
            </Popup>
          </Marker>
        ))}
      </MapContainer>
    </div>
  );
}

// Shared ASN stage metadata for the UI — mirrors backend services/asn_service.STAGE_META.
import type { AsnStatus } from "./types";

export interface StageMeta {
  label: string;
  progress: number;
  // Tailwind classes for the status badge.
  badge: string;
  // Progress-bar fill color.
  bar: string;
}

export const STAGE_META: Record<AsnStatus, StageMeta> = {
  DRAFT: { label: "Draft", progress: 0, badge: "bg-gray-100 text-gray-600", bar: "bg-gray-300" },
  SUBMITTED: { label: "Created", progress: 10, badge: "bg-blue-50 text-blue-600", bar: "bg-blue-400" },
  DISPATCHED: { label: "On Board / Departed", progress: 25, badge: "bg-blue-50 text-blue-600", bar: "bg-blue-500" },
  IN_TRANSIT: { label: "In Transit", progress: 55, badge: "bg-indigo-50 text-indigo-600", bar: "bg-indigo-500" },
  AT_CUSTOMS: { label: "At Customs", progress: 70, badge: "bg-amber-50 text-amber-600", bar: "bg-amber-500" },
  INBOUND_HUB: { label: "Inbound Hub", progress: 85, badge: "bg-amber-50 text-amber-700", bar: "bg-amber-500" },
  OUT_FOR_DELIVERY: { label: "Arriving Soon", progress: 95, badge: "bg-emerald-50 text-emerald-600", bar: "bg-emerald-500" },
  DELIVERED: { label: "Delivered", progress: 100, badge: "bg-emerald-50 text-emerald-700", bar: "bg-emerald-500" },
  CANCELLED: { label: "Cancelled", progress: 0, badge: "bg-gray-100 text-gray-500", bar: "bg-gray-300" },
};

// Order suppliers/staff advance a shipment through (excludes DRAFT/CANCELLED).
export const ADVANCE_STAGES: AsnStatus[] = [
  "DISPATCHED",
  "IN_TRANSIT",
  "AT_CUSTOMS",
  "INBOUND_HUB",
  "OUT_FOR_DELIVERY",
  "DELIVERED",
];

export const TRANSPORT_MODES = ["SEA", "AIR", "ROAD", "RAIL"] as const;

export function stageMeta(status: string): StageMeta {
  return STAGE_META[(status as AsnStatus)] ?? STAGE_META.DRAFT;
}

// Courier providers supported by the tracking API (provider slug → display label).
export const SUPPORTED_COURIERS: { code: string; label: string }[] = [
  { code: "delhivery", label: "Delhivery" },
  { code: "bluedart", label: "Blue Dart" },
  { code: "ekart", label: "Ekart" },
  { code: "dtdc", label: "DTDC" },
  { code: "ecom", label: "Ecom Express" },
  { code: "dhl", label: "DHL" },
];

// Worst-first signal colour, reused by PO rows.
export function signalBadge(signal?: string | null): string {
  switch ((signal || "").toUpperCase()) {
    case "BLACK":
      return "bg-black text-white";
    case "RED":
      return "bg-red-50 text-signal-red";
    case "YELLOW":
      return "bg-amber-50 text-amber-600";
    case "GREEN":
      return "bg-emerald-50 text-emerald-600";
    default:
      return "bg-gray-100 text-gray-500";
  }
}

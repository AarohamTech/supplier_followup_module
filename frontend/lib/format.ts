export function fmtDate(s?: string | null): string {
  if (!s) return "—";
  const d = new Date(s);
  if (isNaN(d.getTime())) return s;
  return d.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
}

export function fmtNum(n?: number | null, opts: Intl.NumberFormatOptions = {}): string {
  if (n === null || n === undefined) return "—";
  return new Intl.NumberFormat("en-IN", opts).format(Number(n));
}

export function fmtCurrency(n?: number | null): string {
  if (n === null || n === undefined) return "—";
  return new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(Number(n));
}

export function daysBetween(from?: string | null, to: Date = new Date()): number | null {
  if (!from) return null;
  const d = new Date(from);
  if (isNaN(d.getTime())) return null;
  return Math.floor((to.getTime() - d.getTime()) / (1000 * 60 * 60 * 24));
}

export function overdueDays(shipment_date?: string | null): number {
  const d = daysBetween(shipment_date);
  return d === null ? 0 : Math.max(0, d);
}

export const signalClass: Record<string, string> = {
  GREEN: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  YELLOW: "bg-amber-50 text-amber-700 ring-amber-200",
  RED: "bg-red-50 text-red-700 ring-red-200",
  BLACK: "bg-gray-900 text-white ring-gray-900",
};

export const signalDot: Record<string, string> = {
  GREEN: "bg-emerald-500",
  YELLOW: "bg-amber-500",
  RED: "bg-red-600",
  BLACK: "bg-gray-900",
};

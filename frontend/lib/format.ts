import type { PoAckStatus } from "./types";

/** UI language as used by lib/i18n (kept as a literal here to avoid importing the client module). */
type DateLang = "en" | "mr";

/** Marathi month names with ordinary 0-9 digits, so dates line up with PO
 *  numbers and quantities, which stay in those digits too. */
function dateLocale(lang?: DateLang): string {
  return lang === "mr" ? "mr-IN-u-nu-latn" : "en-IN";
}

/** "20 Apr 2026" — or "20 एप्रि, 2026" when `lang` is "mr". */
export function fmtDate(s?: string | null, lang?: DateLang): string {
  if (!s) return "—";
  const d = new Date(s);
  if (isNaN(d.getTime())) return s;
  return d.toLocaleDateString(dateLocale(lang), { day: "2-digit", month: "short", year: "numeric" });
}

/** Date and time ("20 Apr 2026, 04:00 pm"); `year: false` drops the year,
 *  `timeZone` pins the clock (e.g. "Asia/Kolkata" for labels marked IST). */
export function fmtDateTime(
  s?: string | null,
  lang?: DateLang,
  opts: { year?: boolean; timeZone?: string } = {},
): string {
  if (!s) return "";
  const d = new Date(s);
  if (isNaN(d.getTime())) return s;
  return d.toLocaleString(dateLocale(lang), {
    day: "2-digit",
    month: "short",
    ...(opts.year === false ? {} : { year: "numeric" }),
    hour: "2-digit",
    minute: "2-digit",
    ...(opts.timeZone ? { timeZone: opts.timeZone } : {}),
  });
}

/** When a PO was acknowledged. English keeps the server's label
 *  ("20 Apr 2026, 04:00 PM IST"); Marathi formats the same instant in IST. */
export function fmtAckTime(s: PoAckStatus, lang?: DateLang): string {
  if (lang === "mr" && s.acknowledged_at) {
    return `${fmtDateTime(s.acknowledged_at, "mr", { timeZone: "Asia/Kolkata" })} IST`;
  }
  if (s.acknowledged_at_label) return s.acknowledged_at_label;
  return s.acknowledged_at ? new Date(s.acknowledged_at).toLocaleString() : "";
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

/** A quantity with its unit ("12 NOS"), "—" when unknown. */
export function fmtQtyUom(n?: number | null, uom?: string | null): string {
  if (n === null || n === undefined) return "—";
  return `${Number(n).toLocaleString()}${uom ? ` ${uom}` : ""}`;
}

"use client";

import { CheckCircle2, Clock, Layers, ShieldAlert, Truck, Warehouse } from "lucide-react";
import type { AsnSummary } from "@/lib/types";

export function StatCard({
  label,
  sub,
  value,
  icon: Icon,
  tint,
  strong,
}: {
  label: string;
  sub?: string;
  value: number | string;
  icon: typeof Layers;
  tint: string;
  strong?: boolean;
}) {
  return (
    <div className="card p-4">
      <div className="flex items-start justify-between">
        <div>
          <div className="text-[10px] uppercase tracking-wider text-brand-muted font-semibold">{label}</div>
          <div className={"kpi-num mt-1 " + (strong ? "text-signal-red" : "")}>{value}</div>
          {sub && <div className="mt-0.5 text-xs text-brand-muted">{sub}</div>}
        </div>
        <div className={"icon-tile " + tint}>
          <Icon size={16} />
        </div>
      </div>
    </div>
  );
}

/** The four shipment-tracking cards (Active / At Customs / Urgent / Finalized). */
export function AsnCards({ s }: { s: AsnSummary | null }) {
  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
      <StatCard label="Active" sub="In transit" value={s?.active ?? 0} icon={Truck} tint="bg-indigo-50 text-indigo-600" />
      <StatCard label="Pending" sub="At customs / hub" value={s?.pending ?? 0} icon={Warehouse} tint="bg-amber-50 text-amber-600" />
      <StatCard label="Urgent" sub="Delayed / alert" value={s?.urgent ?? 0} icon={ShieldAlert} tint="bg-red-50 text-signal-red" strong />
      <StatCard label="Finalized" sub="Delivered (30d)" value={s?.finalized ?? 0} icon={CheckCircle2} tint="bg-emerald-50 text-emerald-600" />
    </div>
  );
}

export const PortalIcons = { Layers, Clock, CheckCircle2, ShieldAlert };

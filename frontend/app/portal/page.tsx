"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { CheckCircle2, FileSpreadsheet, Layers, ShieldAlert, Clock, Truck } from "lucide-react";

import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { PortalPo, PortalSummary } from "@/lib/types";
import { AsnCards, StatCard } from "@/components/portal/PortalCards";
import CriticalPos from "@/components/portal/CriticalPos";

export default function PortalDashboard() {
  const { user } = useAuth();
  const [summary, setSummary] = useState<PortalSummary | null>(null);
  const [pos, setPos] = useState<PortalPo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [s, p] = await Promise.all([api.portalSummary(), api.portalPos()]);
        if (!cancelled) {
          setSummary(s);
          setPos(p.items);
        }
      } catch (e) {
        if (!cancelled) setError((e as Error).message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const name = summary?.supplier_name || user?.supplier_name || "Supplier";

  return (
    <div className="page-stack">
      <div className="page-header">
        <div>
          <h1 className="page-title">Welcome, {name}</h1>
          <p className="page-subtitle">Your purchase orders and shipment notices at a glance.</p>
        </div>
        <Link href="/portal/asn" className="btn-primary">
          <Truck size={14} /> Go to ASN Portal
        </Link>
      </div>

      {error && <div className="rounded-md bg-red-50 px-3 py-2 text-xs text-signal-red">{error}</div>}

      {/* Critical Black POs with a live red overdue countdown */}
      {!loading && <CriticalPos pos={pos} />}

      {/* PO summary */}
      <div>
        <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-brand-muted">
          Purchase Orders
        </div>
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <StatCard
            label="Total POs"
            value={loading ? "—" : summary?.total_pos ?? 0}
            icon={Layers}
            tint="bg-blue-50 text-blue-600"
          />
          <StatCard
            label="Pending POs"
            sub="Awaiting delivery"
            value={loading ? "—" : summary?.pending_pos ?? 0}
            icon={Clock}
            tint="bg-amber-50 text-amber-600"
          />
          <StatCard
            label="Completed POs"
            sub="Delivered via ASN"
            value={loading ? "—" : summary?.completed_pos ?? 0}
            icon={CheckCircle2}
            tint="bg-emerald-50 text-emerald-600"
          />
          <StatCard
            label="Blocked / Black"
            sub="Critical attention"
            value={loading ? "—" : summary?.blocked_count ?? 0}
            icon={ShieldAlert}
            tint="bg-gray-100 text-gray-900"
            strong
          />
        </div>
      </div>

      {/* ASN summary */}
      <div>
        <div className="mb-2 flex items-center justify-between">
          <div className="text-[11px] font-semibold uppercase tracking-wider text-brand-muted">
            Shipments (ASN)
          </div>
          <Link href="/portal/asn" className="text-xs font-medium text-signal-red hover:underline">
            View all →
          </Link>
        </div>
        <AsnCards s={summary?.asn ?? null} />
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Link href="/portal/pos" className="card p-5 hover:border-signal-red">
          <div className="flex items-center gap-3">
            <div className="icon-tile bg-red-50 text-signal-red">
              <FileSpreadsheet size={16} />
            </div>
            <div>
              <div className="font-semibold text-brand-dark">My Purchase Orders</div>
              <div className="text-xs text-brand-muted">Review PO-wise material status and progress.</div>
            </div>
          </div>
        </Link>
        <Link href="/portal/asn" className="card p-5 hover:border-signal-red">
          <div className="flex items-center gap-3">
            <div className="icon-tile bg-red-50 text-signal-red">
              <Truck size={16} />
            </div>
            <div>
              <div className="font-semibold text-brand-dark">ASN Portal</div>
              <div className="text-xs text-brand-muted">Create and track Advance Shipping Notices.</div>
            </div>
          </div>
        </Link>
      </div>
    </div>
  );
}

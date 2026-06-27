"use client";
import { useStore } from "@/lib/store";
import { ArrowUpRight, Mail } from "lucide-react";
import Link from "next/link";

export default function EmailMasterCard() {
  const suppliers = useStore((s) => s.suppliers);
  const total = suppliers.length;
  const active = suppliers.filter((s) => s.is_active).length;
  return (
    <div className="card flex min-h-40 flex-col p-4">
      <div className="flex items-center gap-2">
        <div className="h-8 w-8 rounded-md bg-violet-50 grid place-content-center">
          <Mail size={16} className="text-violet-600" />
        </div>
        <div className="text-sm font-medium">Email Master</div>
      </div>
      <div className="mt-3 space-y-1">
        <Row label="Total Mappings" value={String(total)} />
        <Row label="Active" value={String(active)} />
      </div>
      <Link href="/emails" className="mt-auto inline-flex items-center gap-1 pt-4 text-xs font-semibold text-violet-700 hover:text-violet-800">
        Manage emails <ArrowUpRight size={13} />
      </Link>
    </div>
  );
}
function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between text-sm">
      <span className="text-brand-muted">{label}</span>
      <span className="font-medium">{value}</span>
    </div>
  );
}

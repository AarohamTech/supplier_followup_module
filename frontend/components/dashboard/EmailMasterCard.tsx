"use client";
import { useStore } from "@/lib/store";
import { Mail } from "lucide-react";
import Link from "next/link";

export default function EmailMasterCard() {
  const suppliers = useStore((s) => s.suppliers);
  const total = suppliers.length;
  const active = suppliers.filter((s) => s.is_active).length;
  return (
    <div className="card p-4">
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
      <Link href="/emails" className="mt-3 block w-full text-center bg-violet-50 text-violet-600 text-sm font-medium py-2 rounded-md hover:bg-violet-100">
        Manage Emails
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

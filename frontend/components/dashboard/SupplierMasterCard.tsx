"use client";
import { useStore } from "@/lib/store";
import { Users } from "lucide-react";
import Link from "next/link";

export default function SupplierMasterCard() {
  const suppliers = useStore((s) => s.supplierMasters);
  const total = suppliers.length;
  const mappedSuppliers = suppliers.filter((supplier) => supplier.email_mapped).length;

  return (
    <div className="card p-4">
      <div className="flex items-center gap-2">
        <div className="h-8 w-8 rounded-md bg-blue-50 grid place-content-center">
          <Users size={16} className="text-blue-600" />
        </div>
        <div className="text-sm font-medium">Supplier Master</div>
      </div>
      <div className="mt-3 space-y-1">
        <Row label="Suppliers" value={String(total)} />
        <Row label="Email Mapped" value={`${mappedSuppliers}`} />
      </div>
      <Link href="/suppliers" className="mt-3 block w-full text-center bg-blue-50 text-blue-600 text-sm font-medium py-2 rounded-md hover:bg-blue-100">
        View Suppliers
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

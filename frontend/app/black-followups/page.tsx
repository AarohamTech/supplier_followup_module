"use client";

// Admin route entry. The full panel lives in a shared component so the employee
// portal (/eportal/followups) can render the exact same UI with a scoped adapter.
import { BlackFollowupsPanel } from "@/components/black-followups/BlackFollowupsPanel";

export default function BlackFollowupsPage() {
  return <BlackFollowupsPanel />;
}

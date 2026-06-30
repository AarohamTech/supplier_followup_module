import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";

type Tone = "red" | "dark" | "emerald" | "amber" | "blue";

const toneClass: Record<Tone, string> = {
  red: "bg-red-50 text-signal-red",
  dark: "bg-ink text-white",
  emerald: "bg-emerald-50 text-emerald-700",
  amber: "bg-amber-50 text-amber-700",
  blue: "bg-blue-50 text-blue-700",
};

type PageHeaderProps = {
  title: string;
  description?: ReactNode;
  icon?: LucideIcon;
  tone?: Tone;
  actions?: ReactNode;
  className?: string;
};

export default function PageHeader({
  title,
  description,
  icon: Icon,
  tone = "red",
  actions,
  className,
}: PageHeaderProps) {
  return (
    <div className={cn("page-header", className)}>
      <div className="flex min-w-0 items-center gap-3">
        {Icon && (
          <span className={cn("icon-tile", toneClass[tone])}>
            <Icon size={17} />
          </span>
        )}
        <div className="min-w-0">
          <h1 className="page-title truncate">{title}</h1>
          {description && <p className="page-subtitle">{description}</p>}
        </div>
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </div>
  );
}

import { LogoLoader } from "@/components/brand/Logo";

export default function Loading() {
  return (
    <div
      className="flex min-h-[60vh] items-center justify-center"
      aria-busy="true"
      aria-live="polite"
    >
      <LogoLoader size={72} label="Loading…" />
    </div>
  );
}

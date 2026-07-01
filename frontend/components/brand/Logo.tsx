"use client";

import { useState } from "react";

// Harmony brand mark (geometric monogram from the Harmony logo kit), recoloured
// to the portal theme. Stroke is `currentColor`, so colour it with text-* classes.

const MARK_PATH =
  "M135 134 L135 394 M378 134 L378 394 M135 394 L256 108 M378 394 L256 108 M135 134 L378 394 M378 134 L135 394";

export function Logo({
  size = 28,
  className = "",
  animated = false,
  title = "Harmony",
}: {
  size?: number;
  className?: string;
  animated?: boolean;
  title?: string;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 512 512"
      fill="none"
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      role="img"
      aria-label={title}
      className={`${animated ? "logo-anim " : ""}${className}`}
    >
      <rect x={64} y={64} width={384} height={384} rx={92} strokeWidth={32} pathLength={1} />
      <path d={MARK_PATH} strokeWidth={26} pathLength={1} />
    </svg>
  );
}

// Centred animated mark + optional caption — for page loaders and "AI is working" states.
export function LogoLoader({
  size = 64,
  label,
  className = "",
}: {
  size?: number;
  label?: string;
  className?: string;
}) {
  return (
    <div
      className={`flex flex-col items-center justify-center gap-3 ${className}`}
      role="status"
      aria-live="polite"
    >
      <Logo size={size} animated className="text-signal-red" />
      {label ? <span className="text-xs font-medium tracking-wide text-brand-muted">{label}</span> : null}
    </div>
  );
}

// Zanvar Group (client) logo — hosted raster at /zanvar-logo.png, sized to match
// the Harmony mark. Hides itself (and its trailing "×") if the asset is missing so
// brand headers never show a broken image. Pair with <Logo/> for "Zanvar × Harmony".
export function ZanvarMark({
  size = 30,
  withSeparator = false,
  className = "",
}: {
  size?: number;
  withSeparator?: boolean;
  className?: string;
}) {
  const [ok, setOk] = useState(true);
  if (!ok) return null;
  return (
    <span className={`flex shrink-0 items-center gap-2 sm:gap-3 ${className}`}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src="/zanvar-logo.png"
        alt="Zanvar Group"
        style={{ height: size, width: "auto" }}
        className="shrink-0 object-contain"
        onError={() => setOk(false)}
      />
      {withSeparator ? (
        <span aria-hidden className="text-lg font-semibold text-brand-muted">
          ×
        </span>
      ) : null}
    </span>
  );
}

// Co-brand lockup: Zanvar Group (client) × Harmony (ours) — mark + "Harmony"
// wordmark. Degrades to the Harmony mark alone when the Zanvar asset is absent.
export function LogoLockup({
  animated = false,
  size = 34,
  subtitle,
  className = "",
}: {
  animated?: boolean;
  size?: number;
  subtitle?: string;
  className?: string;
}) {
  return (
    <div className={`flex items-center gap-2.5 ${className}`}>
      <ZanvarMark size={size} withSeparator />
      <Logo size={size} animated={animated} className="text-signal-red" />
      <div className="leading-tight">
        <div className="font-bold tracking-tight text-brand-dark">Harmony</div>
        {subtitle ? <div className="text-[11px] text-brand-muted">{subtitle}</div> : null}
      </div>
    </div>
  );
}

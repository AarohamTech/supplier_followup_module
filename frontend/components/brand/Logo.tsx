"use client";

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

// Mark + "Harmony × Hariom" wordmark lockup — for the top bar and login screen.
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
      <Logo size={size} animated={animated} className="text-signal-red" />
      <div className="leading-tight">
        <div className="font-bold tracking-tight text-brand-dark">
          Harmony <span className="font-semibold text-brand-muted">×</span> Hariom
        </div>
        {subtitle ? <div className="text-[11px] text-brand-muted">{subtitle}</div> : null}
      </div>
    </div>
  );
}

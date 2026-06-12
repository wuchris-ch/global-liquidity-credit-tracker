import { cn } from "@/lib/utils";
import type { Regime } from "@/lib/api";

const REGIME_CLASSES: Record<Regime, string> = {
  loose: "regime-wash-loose regime-text-loose",
  neutral: "regime-wash-neutral regime-text-neutral",
  tight: "regime-wash-tight regime-text-tight",
};

const REGIME_LABELS: Record<Regime, string> = {
  loose: "Loose",
  neutral: "Neutral",
  tight: "Tight",
};

interface RegimeStampProps {
  regime: Regime;
  /** Extra context rendered after the label, e.g. "14th week". */
  detail?: string;
  size?: "sm" | "lg";
  className?: string;
}

export function RegimeStamp({ regime, detail, size = "sm", className }: RegimeStampProps) {
  return (
    <span
      className={cn(
        "inline-flex items-baseline gap-1.5 rounded-sm font-mono font-medium uppercase tracking-wider",
        size === "lg" ? "px-2.5 py-1 text-sm" : "px-2 py-0.5 text-xs",
        REGIME_CLASSES[regime],
        className
      )}
    >
      {REGIME_LABELS[regime]}
      {detail && <span className="font-normal normal-case tracking-normal opacity-80">{detail}</span>}
    </span>
  );
}

export function regimeLabel(regime: Regime): string {
  return REGIME_LABELS[regime];
}

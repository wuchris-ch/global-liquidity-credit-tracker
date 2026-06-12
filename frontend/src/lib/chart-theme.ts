/**
 * Shared Recharts styling for the ink-on-paper chart language.
 * Every chart on the site uses these so the data ink stays consistent.
 */

export const AXIS_TICK = {
  fontSize: 11,
  fontFamily: "var(--font-geist-mono), monospace",
  fill: "var(--muted-foreground)",
} as const;

export const AXIS_LINE = { stroke: "var(--border)" } as const;

export const GRID_PROPS = {
  stroke: "var(--border)",
  strokeDasharray: "0",
  vertical: false,
  strokeOpacity: 0.6,
} as const;

export const TOOLTIP_STYLE: React.CSSProperties = {
  backgroundColor: "var(--popover)",
  border: "1px solid var(--border)",
  borderRadius: "var(--radius)",
  boxShadow: "0 2px 8px oklch(0.24 0.012 60 / 0.08)",
  fontSize: 12,
  fontFamily: "var(--font-geist-mono), monospace",
  color: "var(--foreground)",
  padding: "8px 10px",
};

export const TOOLTIP_LABEL_STYLE: React.CSSProperties = {
  color: "var(--muted-foreground)",
  fontSize: 11,
  marginBottom: 4,
};

/** Regime band fills for ReferenceArea overlays (washes, not blocks). */
export const REGIME_FILL: Record<string, string> = {
  loose: "color-mix(in oklch, var(--regime-loose) 13%, transparent)",
  neutral: "color-mix(in oklch, var(--regime-neutral) 7%, transparent)",
  tight: "color-mix(in oklch, var(--regime-tight) 13%, transparent)",
};

export const PILLAR_COLOR: Record<string, string> = {
  liquidity: "var(--pillar-liquidity)",
  credit: "var(--pillar-credit)",
  stress: "var(--pillar-stress)",
};

export function formatTickDate(date: string): string {
  const d = new Date(date);
  if (Number.isNaN(d.getTime())) return date;
  return d.toLocaleDateString("en-US", { month: "short", year: "2-digit" });
}

export function formatTooltipDate(date: string): string {
  const d = new Date(date);
  if (Number.isNaN(d.getTime())) return date;
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

"use client";

import { cn, type TimeRange } from "@/lib/utils";

const RANGES: { value: TimeRange; label: string }[] = [
  { value: "3m", label: "3M" },
  { value: "1y", label: "1Y" },
  { value: "2y", label: "2Y" },
  { value: "5y", label: "5Y" },
  { value: "10y", label: "10Y" },
  { value: "all", label: "All" },
];

interface RangeTabsProps {
  value: TimeRange;
  onChange: (range: TimeRange) => void;
  /** Restrict to a subset (in display order) when a page doesn't support every range. */
  ranges?: TimeRange[];
  className?: string;
}

export function RangeTabs({ value, onChange, ranges, className }: RangeTabsProps) {
  const items = ranges
    ? RANGES.filter((r) => ranges.includes(r.value))
    : RANGES;

  return (
    <div
      role="group"
      aria-label="Time range"
      className={cn("flex items-center gap-1 font-mono text-xs", className)}
    >
      {items.map((r) => (
        <button
          key={r.value}
          type="button"
          aria-pressed={value === r.value}
          onClick={() => onChange(r.value)}
          className={cn(
            "rounded-sm px-2 py-1 transition-colors",
            value === r.value
              ? "bg-foreground text-background"
              : "text-muted-foreground hover:bg-muted hover:text-foreground"
          )}
        >
          {r.label}
        </button>
      ))}
    </div>
  );
}

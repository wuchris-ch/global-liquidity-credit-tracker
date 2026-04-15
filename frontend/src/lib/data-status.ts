import { DataPoint } from "@/lib/api";

export type FreshnessTone = "current" | "recent" | "stale" | "old" | "missing";

export interface FreshnessStatus {
  label: string;
  tone: FreshnessTone;
  latestDate: string | null;
}

type LatestDateInput = DataPoint[] | string | null | undefined;

function normalizeDate(value: string | null | undefined): string | null {
  if (!value) return null;
  const [datePart] = value.split("T");
  if (!datePart) return null;
  return /^\d{4}-\d{2}-\d{2}$/.test(datePart) ? datePart : null;
}

function dayDiff(latestDate: string): number {
  const latest = new Date(`${latestDate}T00:00:00Z`);
  const now = new Date();
  const today = new Date(
    Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate())
  );
  return Math.max(
    0,
    Math.floor((today.getTime() - latest.getTime()) / (1000 * 60 * 60 * 24))
  );
}

export function formatShortDate(date: string | null | undefined): string {
  const normalized = normalizeDate(date);
  if (!normalized) return "unknown";

  const parsed = new Date(`${normalized}T00:00:00Z`);
  const now = new Date();
  const sameYear = parsed.getUTCFullYear() === now.getUTCFullYear();

  return parsed.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    ...(sameYear ? {} : { year: "numeric" }),
    timeZone: "UTC",
  });
}

export function getLatestDate(...inputs: LatestDateInput[]): string | null {
  let latest: string | null = null;

  for (const input of inputs) {
    let candidate: string | null = null;

    if (typeof input === "string" || input == null) {
      candidate = normalizeDate(input);
    } else if (Array.isArray(input) && input.length > 0) {
      candidate = normalizeDate(input[input.length - 1]?.date);
    }

    if (candidate && (!latest || candidate > latest)) {
      latest = candidate;
    }
  }

  return latest;
}

export function getFreshnessStatus(latestDate: string | null): FreshnessStatus {
  if (!latestDate) {
    return {
      label: "No data",
      tone: "missing",
      latestDate: null,
    };
  }

  const ageDays = dayDiff(latestDate);
  const tone: FreshnessTone =
    ageDays <= 1
      ? "current"
      : ageDays <= 7
        ? "recent"
        : ageDays <= 30
          ? "stale"
          : "old";

  return {
    label: `${tone === "old" ? "Last data" : "Updated"} ${formatShortDate(latestDate)}`,
    tone,
    latestDate,
  };
}

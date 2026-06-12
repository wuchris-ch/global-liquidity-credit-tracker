/**
 * Deterministic prose generation for the morning brief.
 *
 * Every sentence on the Today page is a pure function of the published JSON:
 * same data in, same words out. No model, no randomness.
 */
import type {
  DataPoint,
  GLCIPillar,
  GLCIResponse,
  Regime,
  RegimeHistory,
  BacktestResponse,
} from "@/lib/api";

// ---------------------------------------------------------------------------
// Formatting helpers
// ---------------------------------------------------------------------------

export function ordinal(n: number): string {
  const rem10 = n % 10;
  const rem100 = n % 100;
  if (rem10 === 1 && rem100 !== 11) return `${n}st`;
  if (rem10 === 2 && rem100 !== 12) return `${n}nd`;
  if (rem10 === 3 && rem100 !== 13) return `${n}rd`;
  return `${n}th`;
}

export function signed(value: number, decimals = 2): string {
  const fixed = Math.abs(value).toFixed(decimals);
  return value >= 0 ? `+${fixed}` : `−${fixed}`;
}

/** "$5.92T", "-$48B" — compact dollars from a base-currency value. */
export function compactDollars(value: number, decimals = 2): string {
  const abs = Math.abs(value);
  const sign = value < 0 ? "−" : "";
  if (abs >= 1e12) return `${sign}$${(abs / 1e12).toFixed(decimals)}T`;
  if (abs >= 1e9) return `${sign}$${(abs / 1e9).toFixed(0)}B`;
  if (abs >= 1e6) return `${sign}$${(abs / 1e6).toFixed(0)}M`;
  return `${sign}$${abs.toFixed(0)}`;
}

// ---------------------------------------------------------------------------
// Regime standing
// ---------------------------------------------------------------------------

export interface RegimeStanding {
  regime: Regime;
  /** ISO date the current regime began. */
  since: string | null;
  /** Whole weeks the regime has been in place (>= 1). */
  weeks: number;
}

export function currentRegimeStanding(
  history: RegimeHistory | null,
  fallbackRegime: Regime,
  asOf: string
): RegimeStanding {
  const periods = history?.periods ?? [];
  const last = periods[periods.length - 1];
  if (!last) return { regime: fallbackRegime, since: null, weeks: 1 };

  const regime = (last.regime as Regime) ?? fallbackRegime;
  const start = new Date(last.start).getTime();
  const end = new Date(asOf).getTime();
  const weeks = Math.max(1, Math.round((end - start) / (7 * 24 * 3600 * 1000)) + 1);
  return { regime, since: last.start, weeks };
}

// ---------------------------------------------------------------------------
// Verdict headline
// ---------------------------------------------------------------------------

export type Momentum = "building" | "fading" | "steady";

/** Momentum is the 4-week change in the index (mean 100, sd 10). */
export function momentumDirection(momentum: number): Momentum {
  if (momentum > 0.5) return "building";
  if (momentum < -0.5) return "fading";
  return "steady";
}

const HEADLINES: Record<Regime, Record<Momentum, string>> = {
  loose: {
    building: "Liquidity is loose and still building.",
    steady: "Liquidity is loose and holding.",
    fading: "Liquidity is loose, but the tide is slowing.",
  },
  neutral: {
    building: "Conditions are neutral and improving.",
    steady: "Conditions are neutral and holding.",
    fading: "Conditions are neutral and softening.",
  },
  tight: {
    building: "Conditions are tight, but easing at the margin.",
    steady: "Liquidity is tight and holding.",
    fading: "Liquidity is tight and getting tighter.",
  },
};

export function verdictHeadline(regime: Regime, momentum: number): string {
  return HEADLINES[regime][momentumDirection(momentum)];
}

/**
 * "The index stands at 84.0, 0.2σ above its two-year trend, in the neutral
 * band for a 7th week."
 */
export function standingSentence(
  glci: Pick<GLCIResponse, "value" | "zscore" | "regime">,
  standing: RegimeStanding
): string {
  const sigma = Math.abs(glci.zscore).toFixed(1);
  const side = glci.zscore >= 0 ? "above" : "below";
  const band =
    glci.regime === "neutral" ? "the neutral band" : `${glci.regime} territory`;
  const tenure =
    standing.weeks === 1 ? "its first week" : `a ${ordinal(standing.weeks)} week`;
  return `The index stands at ${glci.value.toFixed(1)}, ${sigma}σ ${side} its two-year trend, in ${band} for ${tenure}.`;
}

// ---------------------------------------------------------------------------
// Pillar attribution
// ---------------------------------------------------------------------------

interface PillarPhrases {
  positive: string;
  negative: string;
}

/** Plain-language phrasing per pillar. Values are post-sign: stress is already inverted. */
const PILLAR_PHRASES: Record<string, PillarPhrases> = {
  liquidity: {
    positive: "central-bank liquidity is doing the lifting",
    negative: "central-bank liquidity is the main drag",
  },
  credit: {
    positive: "credit growth is adding",
    negative: "credit growth is subtracting",
  },
  stress: {
    positive: "calm funding markets are adding",
    negative: "funding stress is subtracting",
  },
};

/**
 * One sentence ranking pillar contributions, largest absolute first:
 * "Central-bank liquidity is the main drag (−1.34); credit growth is adding
 * +0.18 and funding stress is subtracting 0.70."
 */
export function attributionSentence(pillars: GLCIPillar[]): string {
  if (!pillars.length) return "";
  const ranked = [...pillars].sort(
    (a, b) => Math.abs(b.contribution) - Math.abs(a.contribution)
  );

  const phrase = (p: GLCIPillar, lead: boolean): string => {
    const phrases = PILLAR_PHRASES[p.name] ?? {
      positive: `${p.name} is adding`,
      negative: `${p.name} is subtracting`,
    };
    const base = p.contribution >= 0 ? phrases.positive : phrases.negative;
    const amount =
      p.contribution >= 0
        ? `(${signed(p.contribution)})`
        : `(${signed(p.contribution)})`;
    const text = `${base} ${amount}`;
    return lead ? text.charAt(0).toUpperCase() + text.slice(1) : text;
  };

  const [first, ...rest] = ranked;
  if (!rest.length) return `${phrase(first, true)}.`;
  const tail = rest.map((p) => phrase(p, false)).join(" and ");
  return `${phrase(first, true)}; ${tail}.`;
}

// ---------------------------------------------------------------------------
// What changed
// ---------------------------------------------------------------------------

export type ChangeDirection = "supportive" | "restrictive" | "flat";

export interface ChangeItem {
  label: string;
  text: string;
  direction: ChangeDirection;
  /** Absolute salience used for ordering. */
  salience: number;
}

export interface ChangeSpec {
  label: string;
  data: DataPoint[];
  /** Multiply raw values by this to get base units (e.g. 1e6 for millions). */
  scale?: number;
  unit: "usd" | "pct" | "bps" | "index";
  /** Whether an increase is supportive of liquidity ("up") or restrictive ("down"). */
  goodWhen: "up" | "down";
  /** Calendar days to look back for the comparison point. */
  lookbackDays?: number;
  /** Moves smaller than this (in display units) read as "little changed". */
  flatBelow?: number;
}

function valueAt(data: DataPoint[], beforeOrOn: string): DataPoint | null {
  for (let i = data.length - 1; i >= 0; i--) {
    if (data[i].date <= beforeOrOn) return data[i];
  }
  return null;
}

function shiftDays(iso: string, days: number): string {
  const d = new Date(iso);
  d.setDate(d.getDate() - days);
  return d.toISOString().slice(0, 10);
}

function formatLevel(value: number, unit: ChangeSpec["unit"]): string {
  switch (unit) {
    case "usd":
      return compactDollars(value);
    case "pct":
      return `${value.toFixed(2)}%`;
    case "bps":
      return `${Math.round(value)}bp`;
    case "index": {
      const fixed = Math.abs(value).toFixed(1);
      return value < 0 ? `−${fixed}` : fixed;
    }
  }
}

function formatDelta(delta: number, unit: ChangeSpec["unit"]): string {
  switch (unit) {
    case "usd":
      return compactDollars(Math.abs(delta));
    case "pct":
      return `${Math.abs(delta).toFixed(2)}pp`;
    case "bps":
      return `${Math.abs(Math.round(delta))}bp`;
    case "index":
      return Math.abs(delta).toFixed(1);
  }
}

const VERBS: Record<ChangeSpec["unit"], { up: string; down: string }> = {
  usd: { up: "rose", down: "fell" },
  pct: { up: "rose", down: "eased" },
  bps: { up: "widened", down: "tightened" },
  index: { up: "rose", down: "fell" },
};

/** "Net liquidity rose $48B over the week to $5.92T." */
export function buildChangeItem(spec: ChangeSpec): ChangeItem | null {
  const scale = spec.scale ?? 1;
  const lookback = spec.lookbackDays ?? 7;
  const data = spec.data;
  if (data.length < 2) return null;

  const latest = data[data.length - 1];
  const prior = valueAt(data, shiftDays(latest.date, lookback));
  if (!prior || prior.date === latest.date) return null;

  const now = latest.value * scale;
  const then = prior.value * scale;
  const delta = now - then;
  const relative = then !== 0 ? Math.abs(delta / then) : Math.abs(delta);

  const flatBelow = spec.flatBelow ?? 0;
  if (Math.abs(delta) < flatBelow) {
    return {
      label: spec.label,
      text: `${spec.label} little changed at ${formatLevel(now, spec.unit)}.`,
      direction: "flat",
      salience: relative,
    };
  }

  const verb = delta >= 0 ? VERBS[spec.unit].up : VERBS[spec.unit].down;
  const supportive = (delta >= 0) === (spec.goodWhen === "up");
  const window = lookback <= 9 ? "over the week" : `over ${Math.round(lookback / 7)} weeks`;

  return {
    label: spec.label,
    text: `${spec.label} ${verb} ${formatDelta(delta, spec.unit)} ${window} to ${formatLevel(now, spec.unit)}.`,
    direction: supportive ? "supportive" : "restrictive",
    salience: relative,
  };
}

export function buildChangeItems(specs: ChangeSpec[]): ChangeItem[] {
  return specs
    .map(buildChangeItem)
    .filter((item): item is ChangeItem => item !== null)
    .sort((a, b) => {
      // Real moves first (by salience), "little changed" entries last.
      if ((a.direction === "flat") !== (b.direction === "flat")) {
        return a.direction === "flat" ? 1 : -1;
      }
      return b.salience - a.salience;
    });
}

// ---------------------------------------------------------------------------
// Historical playbook line
// ---------------------------------------------------------------------------

export interface PlaybookLine {
  text: string;
  hitRate: number;
  median: number;
  n: number;
  edge: number | null;
}

/**
 * "In past neutral regimes, the S&P 500 was higher 13 weeks later 71% of the
 * time (median +2.9%, n = 112) — 4 points above its unconditional base rate."
 */
export function playbookSentence(
  backtest: BacktestResponse | null,
  regime: Regime,
  assetId = "sp500_price",
  assetLabel = "the S&P 500",
  horizon: "4" | "13" | "26" = "13"
): PlaybookLine | null {
  const asset = backtest?.assets.find((a) => a.id === assetId);
  const stats = asset?.results?.glci?.[regime]?.[horizon];
  if (!asset || !stats || stats.hit_rate == null || stats.median == null) return null;

  const hitPct = Math.round(stats.hit_rate * 100);
  const medianPct = signed(stats.median * 100, 1);
  const weeks = Number(horizon);

  let edgeClause = "";
  if (stats.edge != null) {
    const pts = Math.round(Math.abs(stats.edge) * 100);
    edgeClause =
      pts < 1
        ? ", in line with its unconditional base rate"
        : stats.edge > 0
          ? `, ${pts} ${pts === 1 ? "point" : "points"} above its unconditional base rate`
          : `, ${pts} ${pts === 1 ? "point" : "points"} below its unconditional base rate`;
  }

  return {
    text: `In past ${regime} regimes, ${assetLabel} was higher ${weeks} weeks later ${hitPct}% of the time (median ${medianPct}%, n = ${stats.n})${edgeClause}.`,
    hitRate: stats.hit_rate,
    median: stats.median,
    n: stats.n,
    edge: stats.edge,
  };
}

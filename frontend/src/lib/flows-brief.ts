/**
 * Deterministic prose for the Flows page: same data in, same words out.
 *
 * The leadership score compares an asset's trailing 13-week return with its own
 * three-year history, so the words rank destinations by how unusual the
 * bid is for each asset, not by raw return.
 */
import type { FlowDestination, FlowsPair } from "@/lib/api";

// ---------------------------------------------------------------------------
// Formatting
// ---------------------------------------------------------------------------

/** "+57.4%" / "−10.4%" — signed percents with a true minus sign. */
export function signedPct(value: number | null | undefined, decimals = 1): string {
  if (value == null) return "–";
  const fixed = Math.abs(value * 100).toFixed(decimals);
  return value >= 0 ? `+${fixed}%` : `−${fixed}%`;
}

/** "+2.8σ" / "−0.8σ" — price-leadership scores. */
export function signedSigma(value: number | null | undefined): string {
  if (value == null) return "–";
  const fixed = Math.abs(value).toFixed(1);
  return value >= 0 ? `+${fixed}σ` : `−${fixed}σ`;
}

/** "−0.51" — plain figure with a true minus sign. */
export function signedNum(value: number | null | undefined, decimals = 2): string {
  if (value == null) return "–";
  const fixed = Math.abs(value).toFixed(decimals);
  return value < 0 ? `−${fixed}` : fixed;
}

// ---------------------------------------------------------------------------
// Selection helpers
// ---------------------------------------------------------------------------

function byId(destinations: FlowDestination[], id: string): FlowDestination | null {
  return destinations.find((d) => d.id === id) ?? null;
}

/** Mid-sentence names: lowercase common nouns, intact tickers and acronyms. */
const PROSE_NAMES: Record<string, string> = {
  ai_semis: "semiconductors (SMH)",
  megacap_tech: "the Nasdaq 100",
  bitcoin: "bitcoin",
  ethereum: "ether",
  zcash: "zcash",
  sp500: "the S&P 500",
  small_caps: "small caps (IWM)",
  gold: "gold",
  long_bonds: "long Treasuries (TLT)",
};

function proseName(dest: FlowDestination): string {
  return PROSE_NAMES[dest.id] ?? dest.name;
}

/** Destinations with a leadership score, strongest relative bid first. */
export function rankedByFlow(destinations: FlowDestination[]): FlowDestination[] {
  return destinations
    .filter((d) => d.flow_z != null)
    .sort((a, b) => (b.flow_z ?? 0) - (a.flow_z ?? 0));
}

/** The AI-trade and crypto representatives used for the headline contrast. */
function headlinePair(destinations: FlowDestination[]): {
  ai: FlowDestination | null;
  crypto: FlowDestination | null;
} {
  return {
    ai: byId(destinations, "ai_semis") ?? byId(destinations, "megacap_tech"),
    crypto: byId(destinations, "bitcoin") ?? byId(destinations, "ethereum"),
  };
}

// ---------------------------------------------------------------------------
// Headline
// ---------------------------------------------------------------------------

/** Serif headline contrasting the AI trade with crypto. */
export function flowsHeadline(destinations: FlowDestination[]): string {
  const { ai, crypto } = headlinePair(destinations);
  const aiZ = ai?.flow_z ?? null;
  const cryptoZ = crypto?.flow_z ?? null;

  if (aiZ != null && cryptoZ != null) {
    const gap = aiZ - cryptoZ;
    if (gap >= 0.75 && aiZ > 0) return "The AI trade has stronger price leadership than crypto.";
    if (gap <= -0.75 && cryptoZ > 0) return "Crypto has stronger price leadership than the AI trade.";
    if (aiZ >= 0.75 && cryptoZ >= 0.75) return "AI and crypto are both trading well above their own norms.";
    if (aiZ <= -0.75 && cryptoZ <= -0.75) return "Risk-sensitive prices are weak across AI and crypto.";
  }
  return "No destination has decisive price leadership right now.";
}

// ---------------------------------------------------------------------------
// Lead sentence
// ---------------------------------------------------------------------------

/**
 * "Over the past 13 weeks the strongest bid landed in semiconductors, +57.4%
 * and a +2.8σ stretch of their own three-year norm; the weakest is gold,
 * −16.2% (−2.7σ)."
 */
export function flowsLeadSentence(
  destinations: FlowDestination[],
  windowWeeks: number
): string | null {
  const ranked = rankedByFlow(destinations);
  if (ranked.length < 2) return null;
  const top = ranked[0];
  const bottom = ranked[ranked.length - 1];

  return (
    `Over the past ${windowWeeks} weeks the strongest bid landed in ` +
    `${proseName(top)}, ${signedPct(top.ret_13w)} and a ${signedSigma(top.flow_z)} ` +
    `stretch of its own three-year norm; the weakest is ${proseName(bottom)}, ` +
    `${signedPct(bottom.ret_13w)} (${signedSigma(bottom.flow_z)}).`
  );
}

/** Short teaser for the Today page: top destination vs bottom destination. */
export function flowsTeaserSentence(destinations: FlowDestination[]): string | null {
  const ranked = rankedByFlow(destinations);
  if (ranked.length < 2) return null;
  const top = ranked[0];
  const bottom = ranked[ranked.length - 1];
  return (
    `The strongest bid is in ${proseName(top)} (${signedPct(top.ret_13w)}, ` +
    `${signedSigma(top.flow_z)} vs its own norm); the weakest is ` +
    `${proseName(bottom)} (${signedPct(bottom.ret_13w)}, ${signedSigma(bottom.flow_z)}).`
  );
}

// ---------------------------------------------------------------------------
// Ratio chart reading
// ---------------------------------------------------------------------------

/**
 * "One bitcoin buys 51% less of the semiconductor trade than three years
 * ago; a falling line means the AI trade is outperforming bitcoin."
 */
export function ratioReading(pair: FlowsPair): string | null {
  if (!pair.ratio.length) return null;
  const first = pair.ratio[0].value;
  const last = pair.ratio[pair.ratio.length - 1].value;
  if (!first) return null;
  const change = last / first - 1;
  const pct = Math.abs(Math.round(change * 100));

  const years = Math.max(1, Math.round(pair.ratio.length / 52));
  const spelled = ["a", "two", "three", "four", "five"][years - 1] ?? String(years);
  const span = years === 1 ? "a year" : `${spelled} years`;

  if (pct < 3) {
    return `The ratio is roughly where it was ${span} ago; neither side has sustained price leadership.`;
  }
  return change < 0
    ? `One bitcoin buys ${pct}% less of the semiconductor trade than ${span} ago; a falling line means the AI trade is outperforming bitcoin.`
    : `One bitcoin buys ${pct}% more of the semiconductor trade than ${span} ago; a rising line means bitcoin is outperforming the AI trade.`;
}

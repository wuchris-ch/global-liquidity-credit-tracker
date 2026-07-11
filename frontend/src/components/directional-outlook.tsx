import {
  COMBINED_READ_LABELS,
  PRICE_DIRECTION_LABELS,
  type AssetOutlook,
  type DirectionalOutlook,
} from "@/lib/outlook";
import { signed } from "@/lib/brief";
import { signedPct, signedSigma } from "@/lib/flows-brief";

function listNames(assets: AssetOutlook[]): string {
  const names = assets.map((asset) => asset.name);
  if (names.length <= 1) return names[0] ?? "none";
  if (names.length === 2) return `${names[0]} and ${names[1]}`;
  return `${names.slice(0, -1).join(", ")}, and ${names[names.length - 1]}`;
}

function evidenceNote(asset: AssetOutlook): string {
  switch (asset.edgeEvidence) {
    case "positive":
      return "The paired 95% edge CI is above zero.";
    case "negative":
      return "The paired 95% edge CI is below zero.";
    case "unclear":
      return "The paired 95% edge CI includes zero.";
    case "unavailable":
      return "The paired 95% edge CI is unavailable for this sample.";
    case "descriptive":
      return "Descriptive only; this payload does not include paired edge inference.";
  }
}

function historicalLine(asset: AssetOutlook, regime: string, horizon: string): string {
  const stats = asset.stats;
  const hit = stats.hit_rate == null ? "–" : `${Math.round(stats.hit_rate * 100)}%`;
  const median = stats.median == null ? "–" : `${signed(stats.median * 100, 1)}%`;
  const edge = stats.edge == null ? "edge unavailable" : `edge ${signed(stats.edge * 100, 1)}pp vs base rate`;
  return `After past ${regime} signals, it was higher ${hit} of the time over ${horizon} weeks; median ${median}; ${edge}; n = ${stats.n}.`;
}

function priceLine(asset: AssetOutlook): string | null {
  if (!asset.flow) return null;
  return `Current price leadership: ${signedSigma(asset.flow.flow_z)} vs its own three-year norm; 13-week ${signedPct(asset.flow.ret_13w)}, 4-week ${signedPct(asset.flow.ret_4w)}. It is ${PRICE_DIRECTION_LABELS[asset.priceDirection]}.`;
}

function DirectionalRow({
  asset,
  regime,
  horizon,
}: {
  asset: AssetOutlook;
  regime: string;
  horizon: string;
}) {
  const price = priceLine(asset);
  return (
    <li className="border-t border-border py-4 first:border-t-0 first:pt-0">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <span className="text-sm font-semibold">{asset.name}</span>
        <span className="font-mono text-[0.6875rem] uppercase tracking-[0.1em] text-muted-foreground">
          {COMBINED_READ_LABELS[asset.combinedRead]}
        </span>
      </div>
      <p className="mt-1.5 font-serif text-[1.0125rem] leading-relaxed">
        {historicalLine(asset, regime, horizon)}
      </p>
      <p className="mt-1 font-serif text-sm leading-relaxed text-muted-foreground">
        {evidenceNote(asset)}
        {price ? ` ${price}` : " Current price confirmation is unavailable."}
      </p>
    </li>
  );
}

export function DirectionalOutlookView({
  outlook,
  compact = false,
}: {
  outlook: DirectionalOutlook;
  compact?: boolean;
}) {
  if (!outlook.horizon || outlook.assets.length === 0) {
    return (
      <p className="font-serif text-[0.9375rem] italic text-muted-foreground">
        No forward-return horizon has enough observations for the current regime yet.
      </p>
    );
  }

  const leaders = outlook.positive.slice(0, compact ? 2 : 3);
  const laggards = outlook.negative.slice(0, compact ? 2 : 3);
  const featured = outlook.featured.slice(0, compact ? 2 : 4);
  const horizon = outlook.horizon;
  const preferredUnavailable = horizon !== "13" && outlook.preferredHorizonN != null;

  return (
    <div>
      <p className="font-serif text-[1.0625rem] leading-relaxed">
        {leaders.length > 0
          ? `Using past ${outlook.regime} signal dates as a guide, ${horizon}-week outcomes lean positive for ${listNames(leaders)}`
          : `Past ${outlook.regime} signal dates do not show a clear positive ${horizon}-week lean for any asset`}
        {laggards.length > 0
          ? `; ${listNames(laggards)} had the weakest follow-through.`
          : "."}
      </p>

      <p className="mt-2 font-serif text-sm leading-relaxed text-muted-foreground">
        {outlook.hasPositiveSupportedTilt && outlook.hasNegativeSupportedTilt
          ? "Paired 95% CIs establish positive regime edges for some assets and negative edges for others. Current price leadership is shown separately."
          : outlook.hasPositiveSupportedTilt
            ? "At least one asset has a positive historical regime edge with a paired 95% CI above zero. Current price leadership is shown separately."
            : outlook.hasNegativeSupportedTilt
              ? "At least one asset has a negative historical regime edge with a paired 95% CI below zero. Positive returns and regime support are kept separate."
              : "No statistically supported asset tilt is available, so these are directional watchpoints, not a forecast."}
        {outlook.regimeAgreement === false
          ? " The published regime and the backtest payload disagree, so no combined tilt is shown."
          : outlook.regimeAgreement == null
            ? " The backtest regime is unavailable, so no combined tilt is shown."
            : ""}
        {!outlook.signalFresh
          ? " The signal is more than one week old, so current price confirmation is withheld."
          : !outlook.datesAligned
            ? " Backtest and price-leadership dates are not aligned, so the two signals are kept separate."
            : ""}
        {preferredUnavailable
          ? ` The 13-week sample has at most n = ${outlook.preferredHorizonN}, below the ${outlook.minObservations}-observation reporting minimum, so the page uses ${horizon} weeks.`
          : ""}
      </p>

      {featured.length > 0 && (
        <ol className="mt-5">
          {featured.map((asset) => (
            <DirectionalRow
              key={asset.id}
              asset={asset}
              regime={outlook.regime}
              horizon={horizon}
            />
          ))}
        </ol>
      )}

      {!compact && (
        <p className="mt-3 font-mono text-[0.6875rem] leading-relaxed text-muted-foreground/80">
          A positive historical direction requires a positive median forward return and at least a 55% hit rate. A negative direction requires a negative median and a hit rate of 45% or less. Price leadership is trailing and confirms current strength or weakness; it does not prove continuation.
          {outlook.pairedInference
            ? " Paired CIs apply to one asset and horizon at a time and are not adjusted for multiple testing."
            : ""}
        </p>
      )}
    </div>
  );
}

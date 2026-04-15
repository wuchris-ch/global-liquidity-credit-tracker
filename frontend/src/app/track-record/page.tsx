"use client";

import { useMemo } from "react";
import { Header } from "@/components/header";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";
import { AlertCircle, Loader2 } from "lucide-react";
import { RegimeTimeline } from "@/components/regime-timeline";
import { BacktestTable } from "@/components/backtest-table";
import { useBacktestData } from "@/hooks/use-backtest-data";
import { getFreshnessStatus, getLatestDate } from "@/lib/data-status";
import type {
  BacktestAssetResult,
  BacktestClassifierMeta,
  BacktestHorizon,
  BacktestStats,
  BacktestTimelineEntry,
  Regime,
  RegimePeriod,
} from "@/lib/api";

function timelineToPeriods(timeline: BacktestTimelineEntry[]): RegimePeriod[] {
  if (timeline.length === 0) return [];

  const periods: RegimePeriod[] = [];
  let currentRegime = timeline[0].regime;
  let periodStart = timeline[0].date;

  for (let i = 1; i < timeline.length; i++) {
    const entry = timeline[i];
    if (entry.regime !== currentRegime) {
      periods.push({
        regime: currentRegime,
        start: periodStart,
        end: entry.date,
      });
      currentRegime = entry.regime;
      periodStart = entry.date;
    }
  }

  periods.push({
    regime: currentRegime,
    start: periodStart,
    end: timeline[timeline.length - 1].date,
  });
  return periods;
}

interface BestEdge {
  assetName: string;
  regime: Regime;
  horizon: string;
  edge: number;
  hitRate: number;
  n: number;
}

function findExtremeEdges(
  assets: BacktestAssetResult[],
  classifier: string,
): { best: BestEdge | null; worst: BestEdge | null } {
  let best: BestEdge | null = null;
  let worst: BestEdge | null = null;

  for (const asset of assets) {
    const byRegime = asset.results[classifier];
    if (!byRegime) continue;
    for (const regime of ["tight", "neutral", "loose"] as Regime[]) {
      const byHorizon = byRegime[regime];
      if (!byHorizon) continue;
      for (const horizon of Object.keys(byHorizon) as BacktestHorizon[]) {
        const stats: BacktestStats = byHorizon[horizon];
        if (
          stats === undefined ||
          stats.edge === null ||
          stats.hit_rate === null ||
          stats.n < 20
        ) {
          continue;
        }
        const candidate: BestEdge = {
          assetName: asset.name,
          regime,
          horizon,
          edge: stats.edge,
          hitRate: stats.hit_rate,
          n: stats.n,
        };
        if (!best || candidate.edge > best.edge) best = candidate;
        if (!worst || candidate.edge < worst.edge) worst = candidate;
      }
    }
  }

  return { best, worst };
}

function ClassifierSummary({ meta }: { meta: BacktestClassifierMeta }) {
  const total = Object.values(meta.n_per_regime).reduce(
    (sum: number, v) => sum + (v ?? 0),
    0,
  );
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
      <span className="font-semibold uppercase tracking-wider">{meta.name}</span>
      <span>current:</span>
      <Badge variant="outline" className="capitalize">
        {meta.current_regime ?? "—"}
      </Badge>
      <span>·</span>
      {(["tight", "neutral", "loose"] as Regime[]).map((r) => (
        <span key={r} className="capitalize">
          {r}: {meta.n_per_regime[r] ?? 0}
        </span>
      ))}
      <span>·</span>
      <span>n={total}</span>
    </div>
  );
}

function EdgeCard({
  edge,
  description,
}: {
  edge: BestEdge | null;
  description: string;
}) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardDescription className="text-xs">{description}</CardDescription>
      </CardHeader>
      <CardContent>
        {edge ? (
          <>
            <div className="flex items-baseline gap-2">
              <span
                className={`font-mono text-2xl font-bold ${
                  edge.edge >= 0 ? "text-positive" : "text-negative"
                }`}
              >
                {edge.edge >= 0 ? "+" : ""}
                {(edge.edge * 100).toFixed(1)}pp
              </span>
              <span className="text-xs text-muted-foreground">vs base</span>
            </div>
            <p className="mt-2 text-sm font-medium">{edge.assetName}</p>
            <p className="text-xs capitalize text-muted-foreground">
              {edge.regime} regime · {edge.horizon}w · hit rate{" "}
              {(edge.hitRate * 100).toFixed(0)}% (n={edge.n})
            </p>
          </>
        ) : (
          <p className="text-sm text-muted-foreground">
            No qualifying cells yet. Need n &ge; 20 observations per regime.
          </p>
        )}
      </CardContent>
    </Card>
  );
}

export default function TrackRecordPage() {
  const { data, isLoading, error, refetch } = useBacktestData();

  const pageStatus = getFreshnessStatus(
    getLatestDate(data?.computed_at ?? null),
  );

  const glciPeriods = useMemo(
    () =>
      data?.classifiers?.glci
        ? timelineToPeriods(data.classifiers.glci.timeline)
        : [],
    [data],
  );

  const { best: glciBest, worst: glciWorst } = useMemo(
    () =>
      data
        ? findExtremeEdges(data.assets, "glci")
        : { best: null, worst: null },
    [data],
  );

  const classifierKeys = Object.keys(data?.classifiers ?? {});
  const showNfci = classifierKeys.includes("nfci");

  if (error) {
    return (
      <div className="flex h-screen flex-col bg-background">
        <Header
          title="Track Record"
          description="Backtest of GLCI regime vs forward asset returns"
          status={pageStatus}
        />
        <div className="flex flex-1 items-center justify-center">
          <Card className="max-w-md">
            <CardContent className="flex flex-col items-center gap-4 p-6">
              <AlertCircle className="h-12 w-12 text-destructive" />
              <h2 className="text-lg font-semibold">
                Track record not available
              </h2>
              <p className="text-center text-sm text-muted-foreground">
                The backtest pipeline hasn&apos;t run yet. Run:
              </p>
              <code className="rounded bg-muted px-3 py-2 text-xs">
                python cli.py backtest --save
              </code>
              <p className="text-center text-xs text-muted-foreground">
                Then re-export the JSON and reload.
              </p>
            </CardContent>
          </Card>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-screen flex-col bg-background">
      <Header
        title="Track Record"
        description="Expanding-window backtest of GLCI regime vs forward asset returns"
        onRefresh={refetch}
        isRefreshing={isLoading}
        status={pageStatus}
      />

      <ScrollArea className="flex-1 w-full">
        <div className="bg-dots min-h-full w-full overflow-x-hidden">
          <div className="mx-auto w-full max-w-[1800px] space-y-4 p-3 sm:space-y-6 sm:p-6">
            {/* Summary row */}
            <div className="space-y-2">
              <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
                <span>
                  Window: {data?.date_range?.start ?? "—"} to{" "}
                  {data?.date_range?.end ?? "—"}
                </span>
                {data?.horizons && <span>Horizons: {data.horizons.join("w / ")}w</span>}
              </div>
              {data?.classifiers?.glci && (
                <ClassifierSummary meta={data.classifiers.glci} />
              )}
              {data?.classifiers?.nfci && (
                <ClassifierSummary meta={data.classifiers.nfci} />
              )}
            </div>

            <details
              open
              className="group rounded-lg border border-primary/20 bg-primary/5 p-4 text-xs"
            >
              <summary className="cursor-pointer select-none text-sm font-semibold text-foreground">
                How to read this page
              </summary>
              <div className="mt-4 space-y-4 text-muted-foreground">
                <div className="space-y-1">
                  <p className="font-semibold text-foreground">
                    What this page answers
                  </p>
                  <p>
                    If GLCI says &quot;loose&quot; or &quot;tight&quot; right
                    now, does history show that certain assets usually move a
                    certain way over the next few months? And is that pattern
                    strong enough to actually bet on? That is the whole point
                    of this page.
                  </p>
                </div>

                <div className="space-y-1">
                  <p className="font-semibold text-foreground">
                    1. The three cards below
                  </p>
                  <ul className="ml-4 list-disc space-y-1.5">
                    <li>
                      <strong className="text-foreground">
                        Strongest positive edge:
                      </strong>{" "}
                      the one asset + regime + horizon combo where the GLCI
                      signal helped the most historically. &quot;+5pp&quot;
                      means: when GLCI was in that regime, buying that asset
                      for that many weeks had a hit rate 5 percentage points
                      higher than the base rate (just buying on any random
                      week). Bigger edge = stronger signal.
                    </li>
                    <li>
                      <strong className="text-foreground">
                        Largest negative edge:
                      </strong>{" "}
                      the mirror image. Being in that regime hurt returns.
                      Useful as a &quot;when GLCI says X, don&apos;t touch
                      Y&quot; marker.
                    </li>
                    <li>
                      <strong className="text-foreground">
                        Current GLCI regime:
                      </strong>{" "}
                      what the signal is flashing today, with the NFCI
                      baseline alongside for comparison.
                    </li>
                  </ul>
                </div>

                <div className="space-y-1">
                  <p className="font-semibold text-foreground">
                    2. The Regime History bar
                  </p>
                  <p>
                    Each thin vertical stripe is one historical week, colored
                    by the regime GLCI was in that week.
                  </p>
                  <ul className="ml-4 list-disc space-y-1">
                    <li>
                      <span className="text-positive">Green</span> = loose
                      (liquidity easing, historically risk-on friendly)
                    </li>
                    <li>Yellow = neutral (nothing extreme either way)</li>
                    <li>
                      <span className="text-negative">Red</span> = tight
                      (liquidity contracting, historically risk-off)
                    </li>
                  </ul>
                  <p>
                    The three big boxes under the bar show what share of
                    history sat in each regime.
                  </p>
                </div>

                <div className="space-y-1">
                  <p className="font-semibold text-foreground">
                    3. The Forward Returns table (the main tool)
                  </p>
                  <p>
                    One row per asset (S&amp;P 500, Gold, Bitcoin, etc.). Each
                    row has 9 cells grouped by regime (Tight / Neutral /
                    Loose) and horizon (4, 13, 26 weeks forward).
                  </p>
                  <p className="mt-2">Inside each cell:</p>
                  <ul className="ml-4 list-disc space-y-1">
                    <li>
                      <strong className="text-foreground">Big number:</strong>{" "}
                      median return over that horizon, starting from a week
                      that was in that regime. Green = positive, red =
                      negative.
                    </li>
                    <li>
                      <strong className="text-foreground">Small line:</strong>{" "}
                      hit rate (fraction of windows that ended positive) and
                      the edge in percentage points versus that asset&apos;s
                      unconditional base rate. Positive edge = the regime
                      label genuinely helped.
                    </li>
                    <li>
                      <strong className="text-foreground">Hover a cell:</strong>{" "}
                      reveals the IQR (middle 50% of returns) and the 95%
                      bootstrap confidence intervals on the median and hit
                      rate.
                    </li>
                    <li>
                      <strong className="text-foreground">
                        Empty cell with just &quot;n=X&quot;:
                      </strong>{" "}
                      fewer than 20 observations in that bucket. Too thin to
                      trust, so nothing is shown.
                    </li>
                  </ul>
                </div>

                <div className="space-y-1">
                  <p className="font-semibold text-foreground">
                    4. How to actually use this for positioning
                  </p>
                  <ul className="ml-4 list-disc space-y-1.5">
                    <li>
                      Scan the <strong className="text-foreground">Loose</strong>{" "}
                      columns for strong green numbers. Those are the assets
                      and horizons that historically tended to work when
                      liquidity was easing.
                    </li>
                    <li>
                      Scan the <strong className="text-foreground">Tight</strong>{" "}
                      columns for deep red. Those are your &quot;when GLCI is
                      tight, this asset has suffered&quot; warnings.
                    </li>
                    <li>
                      Switch to the{" "}
                      <strong className="text-foreground">NFCI tab</strong>{" "}
                      and compare. NFCI is a simpler, well-known stress index.
                      If GLCI&apos;s edges don&apos;t beat NFCI&apos;s, the
                      composite isn&apos;t adding information, and you could
                      just use NFCI alone.
                    </li>
                    <li>
                      This is a{" "}
                      <strong className="text-foreground">backtest</strong>.
                      Past regimes may not repeat. The point is to calibrate
                      your expectations, not to guarantee outcomes.
                    </li>
                  </ul>
                </div>
              </div>
            </details>

            {isLoading && !data && (
              <div className="flex items-center justify-center py-24">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              </div>
            )}

            {data && (
              <>
                <div className="grid gap-3 sm:gap-4 md:grid-cols-2 lg:grid-cols-3">
                  <EdgeCard
                    description="Strongest positive hit-rate edge (GLCI)"
                    edge={glciBest}
                  />
                  <EdgeCard
                    description="Largest negative hit-rate edge (GLCI)"
                    edge={glciWorst}
                  />
                  <Card>
                    <CardHeader className="pb-2">
                      <CardDescription className="text-xs">
                        Current GLCI regime
                      </CardDescription>
                    </CardHeader>
                    <CardContent>
                      <Badge
                        variant="outline"
                        className="text-sm capitalize"
                      >
                        {data.classifiers?.glci?.current_regime ?? "—"}
                      </Badge>
                      <p className="mt-3 text-xs text-muted-foreground">
                        NFCI baseline currently:{" "}
                        <span className="capitalize font-medium text-foreground">
                          {data.classifiers?.nfci?.current_regime ?? "—"}
                        </span>
                      </p>
                    </CardContent>
                  </Card>
                </div>

                {glciPeriods.length > 0 && (
                  <RegimeTimeline
                    periods={glciPeriods}
                    currentRegime={
                      data.classifiers?.glci?.current_regime ?? undefined
                    }
                  />
                )}

                {showNfci ? (
                  <Tabs defaultValue="glci" className="space-y-4">
                    <TabsList>
                      <TabsTrigger value="glci">
                        GLCI classifier
                      </TabsTrigger>
                      <TabsTrigger value="nfci">NFCI baseline</TabsTrigger>
                    </TabsList>
                    <TabsContent value="glci">
                      <BacktestTable
                        title="Forward returns by GLCI regime"
                        description="Median forward return and hit rate by asset, regime, and horizon (weeks). Expanding-window classifier with no look-ahead."
                        classifier="glci"
                        assets={data.assets}
                        horizons={data.horizons}
                      />
                    </TabsContent>
                    <TabsContent value="nfci">
                      <BacktestTable
                        title="Forward returns by NFCI regime"
                        description="Same structure as GLCI table but using Chicago Fed NFCI (sign-flipped so high z = loose) as the regime classifier. If GLCI doesn't outperform NFCI, the composite isn't adding information."
                        classifier="nfci"
                        assets={data.assets}
                        horizons={data.horizons}
                      />
                    </TabsContent>
                  </Tabs>
                ) : (
                  <BacktestTable
                    title="Forward returns by GLCI regime"
                    description="Median forward return and hit rate by asset, regime, and horizon (weeks). Expanding-window classifier with no look-ahead."
                    classifier="glci"
                    assets={data.assets}
                    horizons={data.horizons}
                  />
                )}

                <Card>
                  <CardHeader>
                    <CardTitle className="text-sm font-semibold">
                      Methodology
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3 text-xs text-muted-foreground">
                    <p>
                      <strong className="text-foreground">
                        Expanding-window z-score.
                      </strong>{" "}
                      At each weekly observation <em>t</em>, the z-score uses
                      the mean and standard deviation of the composite from the
                      start of the series up to <em>t</em>. A one-year burn-in
                      (52 observations) is required before any classification
                      is emitted, so the first year of history contributes to
                      the calibration but is not itself labelled.
                    </p>
                    <p>
                      <strong className="text-foreground">Regimes.</strong>{" "}
                      Tight: z &lt; -1. Neutral: -1 &le; z &le; +1. Loose: z
                      &gt; +1. The same thresholds are applied to both the GLCI
                      and NFCI classifiers for an apples-to-apples comparison.
                    </p>
                    <p>
                      <strong className="text-foreground">
                        Forward returns.
                      </strong>{" "}
                      For each date <em>t</em> and horizon{" "}
                      <em>h &isin; &#123;4, 13, 26&#125;</em> weeks, we compute{" "}
                      <em>r(t, h) = price(t+h) / price(t) - 1</em>. Assets are
                      resampled to weekly-Friday closes before the calculation.
                    </p>
                    <p>
                      <strong className="text-foreground">
                        Hit rate edge.
                      </strong>{" "}
                      Hit rate is the fraction of forward returns that are
                      positive. The &quot;edge&quot; (pp) is the regime hit
                      rate minus the unconditional hit rate across all classified
                      dates; positive means the regime label genuinely helps.
                    </p>
                    <p>
                      <strong className="text-foreground">
                        Confidence intervals.
                      </strong>{" "}
                      95% CIs via moving block bootstrap (block length =
                      horizon, 5000 resamples). Blocks respect the overlap
                      between consecutive forward returns, which standard
                      errors would ignore.
                    </p>
                    <p>
                      <strong className="text-foreground">
                        Minimum observations.
                      </strong>{" "}
                      Cells with fewer than 20 observations are left blank; CIs
                      on small cells are unreliable regardless of the
                      statistical machinery.
                    </p>
                    <p>
                      <strong className="text-foreground">
                        This is a backtest.
                      </strong>{" "}
                      It shows how a no-look-ahead regime signal would have
                      related to forward returns in the historical sample. Past
                      regimes may not repeat, and the asset set is limited to
                      the seven series on the Risk page.
                    </p>
                  </CardContent>
                </Card>
              </>
            )}
          </div>
        </div>
      </ScrollArea>
    </div>
  );
}

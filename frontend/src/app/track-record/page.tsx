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

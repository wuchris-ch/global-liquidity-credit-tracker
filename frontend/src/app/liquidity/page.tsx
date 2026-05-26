"use client";

import { useState, useCallback, useMemo } from "react";
import { Header, TimeRange } from "@/components/header";
import { MetricCard } from "@/components/metric-card";
import { LiquidityChart } from "@/components/liquidity-chart";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { InfoTooltip } from "@/components/info-tooltip";
import {
  Activity,
  ArrowDownRight,
  ArrowUpRight,
  Building2,
  Landmark,
  LineChart,
  TrendingUp,
  Wallet,
  AlertCircle,
  Loader2,
} from "lucide-react";
import { useSeriesData, useIndexData } from "@/hooks/use-series-data";
import { NetLiquidityRiskChart } from "@/components/net-liquidity-risk-chart";
import { formatCurrency, getDateRange, UNIT_SCALES } from "@/lib/utils";
import {
  correlationInterpretation,
  getLiquidityAnalyticsRange,
  mergeNetLiquidityWithEquity,
  netLiquidityFlowSeries,
  periodChange,
  rollingWeeklyChangeCorrelation,
  scaleNetLiquidity,
} from "@/lib/liquidity-analytics";
import { metricDefinitions, chartDefinitions } from "@/lib/indicator-definitions";
import {
  formatShortDate,
  getFreshnessStatus,
  getLatestDate,
} from "@/lib/data-status";

export default function LiquidityPage() {
  const [timeRange, setTimeRange] = useState<TimeRange>("1y");
  const dateRange = useMemo(() => getDateRange(timeRange), [timeRange]);
  const analyticsRange = useMemo(
    () => getLiquidityAnalyticsRange(timeRange),
    [timeRange]
  );

  const fedAssets = useSeriesData("fed_total_assets", { ...dateRange });
  const tga = useSeriesData("fed_treasury_general_account", { ...dateRange });
  const rrp = useSeriesData("fed_reverse_repo", { ...dateRange });
  const netLiquidity = useIndexData("fed_net_liquidity", { ...analyticsRange });
  const sp500 = useSeriesData("sp500_price", { ...analyticsRange });

  const isCoreLoading =
    fedAssets.isLoading ||
    tga.isLoading ||
    rrp.isLoading ||
    netLiquidity.isLoading;
  const isLoading = isCoreLoading || sp500.isLoading;
  const hasError =
    fedAssets.error || tga.error || rrp.error || netLiquidity.error;
  const sp500Unavailable =
    Boolean(sp500.error) || (!sp500.isLoading && sp500.data.length === 0);

  const handleRefresh = useCallback(async () => {
    await Promise.all([
      fedAssets.refetch(),
      tga.refetch(),
      rrp.refetch(),
      netLiquidity.refetch(),
      sp500.refetch(),
    ]);
  }, [fedAssets, tga, rrp, netLiquidity, sp500]);

  const handleTimeRangeChange = useCallback((range: TimeRange) => setTimeRange(range), []);

  // Scale raw values to base dollars using their unit multipliers
  const scaleMillions = UNIT_SCALES.millions_usd;
  const scaleBillions = UNIT_SCALES.billions_usd;

  const getLatestValue = (data: { date: string; value: number }[]) =>
    data.length > 0 ? data[data.length - 1]?.value ?? null : null;

  const latestFedRaw = getLatestValue(fedAssets.data);
  const latestTgaRaw = getLatestValue(tga.data);
  const latestRrpRaw = getLatestValue(rrp.data);
  const latestNetRaw = getLatestValue(netLiquidity.data);

  const latestFed = latestFedRaw !== null ? latestFedRaw * scaleMillions : null;
  const latestTga = latestTgaRaw !== null ? latestTgaRaw * scaleMillions : null;
  const latestRrp = latestRrpRaw !== null ? latestRrpRaw * scaleBillions : null;
  const latestNet = latestNetRaw !== null ? latestNetRaw * scaleMillions : null;

  const calcChange = (data: { date: string; value: number }[]) => {
    if (data.length < 8) return undefined;
    const latest = data[data.length - 1]?.value ?? 0;
    const prev = data[data.length - 8]?.value ?? latest;
    return prev !== 0 ? ((latest - prev) / prev) * 100 : undefined;
  };

  const scaledNetLiqFull = useMemo(
    () => scaleNetLiquidity(netLiquidity.data, scaleMillions),
    [netLiquidity.data, scaleMillions]
  );

  const scaledNetLiqDisplay = useMemo(() => {
    const startMs = new Date(dateRange.start).getTime();
    return scaledNetLiqFull.filter(
      (d) => new Date(d.date).getTime() >= startMs
    );
  }, [scaledNetLiqFull, dateRange.start]);

  const change4w = useMemo(
    () => periodChange(netLiquidity.data, 4, scaleMillions),
    [netLiquidity.data, scaleMillions]
  );

  const change13w = useMemo(
    () => periodChange(netLiquidity.data, 13, scaleMillions),
    [netLiquidity.data, scaleMillions]
  );

  const mergedForAnalytics = useMemo(
    () => mergeNetLiquidityWithEquity(netLiquidity.data, sp500.data, scaleMillions),
    [netLiquidity.data, sp500.data, scaleMillions]
  );

  const mergedDisplay = useMemo(() => {
    const startMs = new Date(dateRange.start).getTime();
    return mergedForAnalytics.filter(
      (d) => new Date(d.date).getTime() >= startMs
    );
  }, [mergedForAnalytics, dateRange.start]);

  const correlation52w = useMemo(
    () => rollingWeeklyChangeCorrelation(mergedForAnalytics, 52),
    [mergedForAnalytics]
  );

  const flow4wSeries = useMemo(() => {
    const startMs = new Date(dateRange.start).getTime();
    return netLiquidityFlowSeries(scaledNetLiqFull, 4).filter(
      (d) => new Date(d.date).getTime() >= startMs
    );
  }, [scaledNetLiqFull, dateRange.start]);

  const pageStatus = getFreshnessStatus(
    getLatestDate(
      fedAssets.latestDate,
      tga.latestDate,
      rrp.latestDate,
      netLiquidity.latestDate,
      sp500.latestDate
    )
  );

  if (hasError) {
    return (
      <div className="flex h-screen flex-col bg-background">
        <Header title="Liquidity Monitor" description="Federal Reserve balance sheet and net liquidity tracking" timeRange={timeRange} onTimeRangeChange={handleTimeRangeChange} onRefresh={handleRefresh} isRefreshing={isLoading} status={pageStatus} />
        <div className="flex flex-1 items-center justify-center">
          <Card className="max-w-md">
            <CardContent className="flex flex-col items-center gap-4 p-6">
              <AlertCircle className="h-12 w-12 text-destructive" />
              <h2 className="text-lg font-semibold">Failed to Load Data</h2>
              <p className="text-center text-sm text-muted-foreground">
                Could not load required Fed liquidity series. If this is production, check that the data
                workflow published to GitHub Pages; locally, start the API with:
              </p>
              <code className="rounded bg-muted px-3 py-2 text-sm">uvicorn src.api:app --reload</code>
            </CardContent>
          </Card>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-screen flex-col bg-background">
      <Header title="Liquidity Monitor" description="Federal Reserve balance sheet and net liquidity tracking" timeRange={timeRange} onTimeRangeChange={handleTimeRangeChange} onRefresh={handleRefresh} isRefreshing={isLoading} status={pageStatus} />
      <ScrollArea className="flex-1 w-full">
        <div className="bg-grid min-h-full w-full overflow-x-hidden">
          <div className="mx-auto w-full max-w-[1600px] space-y-3 p-2 min-[360px]:p-3 sm:space-y-6 sm:p-6 overflow-hidden">
            <Card className="border-primary/20 bg-gradient-to-r from-primary/5 via-card to-card">
              <CardContent className="p-3 sm:p-6">
                <div className="flex flex-col gap-3 sm:gap-6 lg:flex-row lg:items-center lg:justify-between">
                  <div>
                    <Badge className="mb-2 sm:mb-3 bg-primary/20 text-primary hover:bg-primary/30 text-[10px] sm:text-xs">Key Formula</Badge>
                    <h2 className="inline-flex items-center gap-2 text-base sm:text-xl font-bold tracking-tight">
                      Fed Net Liquidity
                      <InfoTooltip {...metricDefinitions.net_liquidity} size="sm" />
                    </h2>
                    <p className="mt-1 text-xs sm:text-sm text-muted-foreground">Actual liquidity available in the financial system</p>
                  </div>
                  <div className="flex flex-wrap items-center gap-1.5 sm:gap-3 font-mono text-[10px] sm:text-sm lg:gap-4 lg:text-base">
                    <div className="flex items-center gap-1.5 sm:gap-2 rounded-lg bg-muted/50 px-2 py-1.5 sm:px-4 sm:py-2">
                      <Building2 className="h-3 w-3 sm:h-4 sm:w-4 text-chart-1" />
                      <span className="hidden xs:inline">Fed</span><span>Assets</span>
                    </div>
                    <span className="text-muted-foreground">−</span>
                    <div className="flex items-center gap-1.5 sm:gap-2 rounded-lg bg-muted/50 px-2 py-1.5 sm:px-4 sm:py-2">
                      <Landmark className="h-3 w-3 sm:h-4 sm:w-4 text-chart-3" />
                      <span>TGA</span>
                    </div>
                    <span className="text-muted-foreground">−</span>
                    <div className="flex items-center gap-1.5 sm:gap-2 rounded-lg bg-muted/50 px-2 py-1.5 sm:px-4 sm:py-2">
                      <Wallet className="h-3 w-3 sm:h-4 sm:w-4 text-chart-4" />
                      <span>RRP</span>
                    </div>
                    <span className="text-muted-foreground">=</span>
                    <div className="flex items-center gap-1.5 sm:gap-2 rounded-lg border-2 border-primary/30 bg-primary/10 px-2 py-1.5 sm:px-4 sm:py-2"><Activity className="h-3 w-3 sm:h-4 sm:w-4 text-primary" /><span className="font-semibold text-primary">Net Liq</span></div>
                  </div>
                </div>
              </CardContent>
            </Card>

            <div className="grid grid-cols-1 gap-2 min-[360px]:grid-cols-2 sm:gap-4 lg:grid-cols-4">
              <MetricCard
                title="Net Liquidity (Stock)"
                value={isCoreLoading ? "Loading..." : latestNet !== null ? formatCurrency(latestNet) : "No data"}
                change={calcChange(netLiquidity.data)}
                trend={(calcChange(netLiquidity.data) ?? 0) >= 0 ? "up" : "down"}
                icon={<Activity className="h-5 w-5" />}
                variant="highlight"
                info={metricDefinitions.net_liquidity}
              />
              <MetricCard
                title="4W Flow"
                value={
                  isCoreLoading
                    ? "Loading..."
                    : change4w !== null
                      ? `${change4w.deltaAbs >= 0 ? "+" : ""}${formatCurrency(change4w.deltaAbs)}`
                      : "No data"
                }
                change={change4w?.deltaPct}
                trend={(change4w?.deltaAbs ?? 0) >= 0 ? "up" : "down"}
                icon={<TrendingUp className="h-5 w-5" />}
                variant="highlight"
                info={metricDefinitions.net_liquidity_4w_change}
              />
              <MetricCard
                title="13W Change"
                value={
                  isCoreLoading
                    ? "Loading..."
                    : change13w !== null
                      ? `${change13w.deltaPct >= 0 ? "+" : ""}${change13w.deltaPct.toFixed(2)}%`
                      : "No data"
                }
                change={change13w?.deltaPct}
                trend={(change13w?.deltaPct ?? 0) >= 0 ? "up" : "down"}
                icon={<LineChart className="h-5 w-5" />}
                info={metricDefinitions.net_liquidity_13w_change}
              />
              <MetricCard
                title="52W Δ Corr (SPX)"
                value={
                  isCoreLoading || sp500.isLoading
                    ? "Loading..."
                    : sp500Unavailable
                      ? "N/A"
                      : correlation52w !== null
                        ? `${correlation52w >= 0 ? "+" : ""}${correlation52w.toFixed(2)}`
                        : "N/A"
                }
                trend={
                  correlation52w === null
                    ? "neutral"
                    : correlation52w >= 0
                      ? "up"
                      : "down"
                }
                icon={<TrendingUp className="h-5 w-5" />}
                info={metricDefinitions.net_liquidity_sp500_corr}
              />
            </div>

            {!isCoreLoading && !sp500Unavailable && correlation52w !== null && (
              <p className="text-xs text-muted-foreground px-1">
                {correlationInterpretation(correlation52w)}
              </p>
            )}

            {sp500Unavailable && !isCoreLoading && (
              <Card className="border-amber-500/30 bg-amber-500/5">
                <CardContent className="flex items-start gap-3 p-4 text-sm text-muted-foreground">
                  <AlertCircle className="h-5 w-5 shrink-0 text-amber-500" />
                  <p>
                    S&amp;P 500 overlay is temporarily unavailable (series not in static export yet).
                    Fed liquidity levels and flows below are still live. Re-run the data workflow after
                    deploy to populate <code className="text-xs">sp500_price</code>.
                  </p>
                </CardContent>
              </Card>
            )}

            {isCoreLoading ? (
              <Card className="flex h-[420px] items-center justify-center">
                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
              </Card>
            ) : sp500Unavailable ? (
              <LiquidityChart
                title="Fed Net Liquidity"
                description="Total Assets minus TGA and Reverse Repo"
                data={scaledNetLiqDisplay}
                color="var(--chart-1)"
                height={420}
                valueFormatter={(v) => formatCurrency(v)}
                info={chartDefinitions.net_liquidity_chart}
              />
            ) : (
              <NetLiquidityRiskChart
                title="Net Liquidity vs S&P 500"
                description="Stock of Fed liquidity (left) vs risk assets (right)—see if flows are supporting equities"
                data={mergedDisplay}
                correlation52w={correlation52w}
                height={420}
                info={chartDefinitions.net_liquidity_vs_sp500_chart}
              />
            )}

            <div className="grid gap-3 sm:gap-6 lg:grid-cols-2">
              {isCoreLoading ? (
                <>
                  <Card className="flex h-[320px] items-center justify-center">
                    <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                  </Card>
                  <Card className="flex h-[320px] items-center justify-center">
                    <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                  </Card>
                </>
              ) : (
                <>
                  <LiquidityChart
                    title="Fed Net Liquidity"
                    description="Total Assets minus TGA and Reverse Repo"
                    data={scaledNetLiqDisplay}
                    color="var(--chart-1)"
                    height={320}
                    valueFormatter={(v) => formatCurrency(v)}
                    info={chartDefinitions.net_liquidity_chart}
                  />
                  <LiquidityChart
                    title="4-Week Net Liquidity Flow"
                    description="Weekly injection (+) or drain (−) vs four weeks ago"
                    data={flow4wSeries}
                    chartType="line"
                    color="var(--chart-2)"
                    height={320}
                    valueFormatter={(v) => formatCurrency(v)}
                    referenceLine={0}
                    referenceLabel="0"
                    info={chartDefinitions.net_liquidity_flow_chart}
                  />
                </>
              )}
            </div>

            <div className="grid grid-cols-1 gap-2 min-[360px]:grid-cols-2 sm:gap-4 lg:grid-cols-3">
              <MetricCard title="Fed Total Assets" value={isLoading ? "Loading..." : latestFed !== null ? formatCurrency(latestFed) : "No data"} change={calcChange(fedAssets.data)} trend={(calcChange(fedAssets.data) ?? 0) >= 0 ? "up" : "down"} icon={<Building2 className="h-5 w-5" />} info={metricDefinitions.fed_balance_sheet} />
              <MetricCard title="Treasury General Account" value={isLoading ? "Loading..." : latestTga !== null ? formatCurrency(latestTga) : "No data"} change={calcChange(tga.data)} trend={(calcChange(tga.data) ?? 0) >= 0 ? "up" : "down"} icon={<Landmark className="h-5 w-5" />} info={metricDefinitions.tga} />
              <MetricCard title="Reverse Repo Facility" value={isLoading ? "Loading..." : latestRrp !== null ? formatCurrency(latestRrp) : "No data"} change={calcChange(rrp.data)} trend={(calcChange(rrp.data) ?? 0) >= 0 ? "up" : "down"} icon={<Wallet className="h-5 w-5" />} info={metricDefinitions.rrp} />
            </div>

            <div className="grid gap-3 sm:gap-6 lg:grid-cols-3">
              {isLoading ? (
                <><Card className="flex h-[280px] items-center justify-center"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></Card><Card className="flex h-[280px] items-center justify-center"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></Card><Card className="flex h-[280px] items-center justify-center"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></Card></>
              ) : (
                <>
                  <LiquidityChart title="Fed Balance Sheet" description="Total assets held" data={fedAssets.data.map(d => ({ ...d, value: d.value * scaleMillions }))} color="var(--chart-1)" height={280} valueFormatter={(v) => formatCurrency(v)} info={chartDefinitions.fed_balance_sheet_chart} />
                  <LiquidityChart title="Treasury General Account" description="US Treasury cash balance at Fed" data={tga.data.map(d => ({ ...d, value: d.value * scaleMillions }))} color="var(--chart-3)" height={280} valueFormatter={(v) => formatCurrency(v)} info={metricDefinitions.tga} />
                  <LiquidityChart title="Overnight Reverse Repo" description="RRP facility usage" data={rrp.data.map(d => ({ ...d, value: d.value * scaleBillions }))} color="var(--chart-4)" height={280} valueFormatter={(v) => formatCurrency(v)} info={metricDefinitions.rrp} />
                </>
              )}
            </div>

            <div className="grid gap-3 sm:gap-6 lg:grid-cols-2">
              <Card>
                <CardHeader><CardTitle className="text-sm font-semibold">Liquidity Drivers</CardTitle></CardHeader>
                <CardContent className="space-y-4">
                  <div className="space-y-3">
                    <div className="flex items-center justify-between rounded-lg bg-positive/5 p-4">
                      <div className="flex items-center gap-3"><ArrowUpRight className="h-5 w-5 text-positive" /><div><p className="font-medium">RRP Decline</p><p className="text-xs text-muted-foreground">Money market funds reducing RRP usage</p></div></div>
                      <span className="font-mono text-sm font-semibold text-positive">+Liquidity</span>
                    </div>
                    <div className="flex items-center justify-between rounded-lg bg-negative/5 p-4">
                      <div className="flex items-center gap-3"><ArrowDownRight className="h-5 w-5 text-negative" /><div><p className="font-medium">QT Runoff</p><p className="text-xs text-muted-foreground">Balance sheet reduction continues</p></div></div>
                      <span className="font-mono text-sm font-semibold text-negative">-Liquidity</span>
                    </div>
                    <div className="flex items-center justify-between rounded-lg bg-muted/30 p-4">
                      <div className="flex items-center gap-3"><Landmark className="h-5 w-5 text-muted-foreground" /><div><p className="font-medium">TGA Changes</p><p className="text-xs text-muted-foreground">Treasury cash management</p></div></div>
                      <span className="font-mono text-sm font-semibold text-muted-foreground">Variable</span>
                    </div>
                  </div>
                </CardContent>
              </Card>
              <Card>
                <CardHeader><CardTitle className="text-sm font-semibold">Key Levels</CardTitle></CardHeader>
                <CardContent className="space-y-4">
                  <div className="space-y-3">
                    <div className="flex items-center justify-between border-b border-border pb-3">
                      <div><p className="text-xs text-muted-foreground">Current Net Liquidity</p><p className="font-mono text-xl font-bold">{isLoading ? "..." : latestNet !== null ? formatCurrency(latestNet) : "No data"}</p></div>
                      <Badge variant="outline" className="border-border text-muted-foreground">
                        {pageStatus.latestDate ? `As of ${formatShortDate(pageStatus.latestDate)}` : "No data"}
                      </Badge>
                    </div>
                      <div className="grid grid-cols-2 gap-4">
                      <div className="rounded-lg bg-muted/30 p-3"><p className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">Period High</p><p className="mt-1 font-mono text-lg font-semibold">{isLoading || netLiquidity.data.length === 0 ? "..." : formatCurrency(Math.max(...netLiquidity.data.map((d) => d.value)) * scaleMillions)}</p></div>
                      <div className="rounded-lg bg-muted/30 p-3"><p className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">Period Low</p><p className="mt-1 font-mono text-lg font-semibold">{isLoading || netLiquidity.data.length === 0 ? "..." : formatCurrency(Math.min(...netLiquidity.data.map((d) => d.value)) * scaleMillions)}</p></div>
                    </div>
                    <div className="rounded-lg border border-primary/20 bg-primary/5 p-3"><p className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">Latest Observation</p><p className="mt-1 font-mono text-lg font-semibold text-primary">{pageStatus.latestDate ? formatShortDate(pageStatus.latestDate) : "Unavailable"}</p><p className="mt-1 text-xs text-muted-foreground">Use the page header freshness badge to judge whether the selected window is current.</p></div>
                  </div>
                </CardContent>
              </Card>
            </div>
          </div>
        </div>
      </ScrollArea>
    </div>
  );
}

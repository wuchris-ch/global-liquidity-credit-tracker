"use client";

import { useState, useCallback, useMemo } from "react";
import { Header, TimeRange } from "@/components/header";
import { MetricCard } from "@/components/metric-card";
import { LiquidityChart } from "@/components/liquidity-chart";
import { MultiLineChart } from "@/components/multi-line-chart";
import { InfoTooltip } from "@/components/info-tooltip";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import {
  AlertTriangle,
  CheckCircle2,
  TrendingDown,
  TrendingUp,
  Activity,
  AlertCircle,
  Loader2,
} from "lucide-react";
import { useSeriesData, useIndexData } from "@/hooks/use-series-data";
import { metricDefinitions, chartDefinitions, spreadDefinitions } from "@/lib/indicator-definitions";

function getDateRange(range: TimeRange): { start: string; end: string } {
  const end = new Date();
  const start = new Date();
  
  switch (range) {
    case "1m": start.setMonth(end.getMonth() - 1); break;
    case "3m": start.setMonth(end.getMonth() - 3); break;
    case "6m": start.setMonth(end.getMonth() - 6); break;
    case "1y": start.setFullYear(end.getFullYear() - 1); break;
    case "2y": start.setFullYear(end.getFullYear() - 2); break;
    case "5y": start.setFullYear(end.getFullYear() - 5); break;
    case "10y": start.setFullYear(end.getFullYear() - 10); break;
    case "15y": start.setFullYear(end.getFullYear() - 15); break;
    case "all": start.setFullYear(2000); break;
  }
  
  return {
    start: start.toISOString().split("T")[0],
    end: end.toISOString().split("T")[0],
  };
}

export default function SpreadsPage() {
  const [timeRange, setTimeRange] = useState<TimeRange>("1y");

  const dateRange = useMemo(() => getDateRange(timeRange), [timeRange]);

  // Fetch real data
  const hySpread = useSeriesData("ice_bofa_us_high_yield_spread", { ...dateRange });
  const igSpread = useSeriesData("ice_bofa_us_ig_spread", { ...dateRange });
  const sofr = useSeriesData("sofr", { ...dateRange });
  const fedFunds = useSeriesData("fed_funds_rate", { ...dateRange });
  const stressIndex = useIndexData("usd_funding_stress", { ...dateRange });

  const isLoading = hySpread.isLoading || igSpread.isLoading || sofr.isLoading;
  const hasError = hySpread.error || igSpread.error || sofr.error;

  const handleRefresh = useCallback(async () => {
    await Promise.all([
      hySpread.refetch(),
      igSpread.refetch(),
      sofr.refetch(),
      fedFunds.refetch(),
      stressIndex.refetch(),
    ]);
  }, [hySpread, igSpread, sofr, fedFunds, stressIndex]);

  const handleTimeRangeChange = useCallback((range: TimeRange) => {
    setTimeRange(range);
  }, []);

  // Convert spread data from percent to basis points (multiply by 100)
  const hyBps = useMemo(() => 
    hySpread.data.map(d => ({ ...d, value: d.value * 100 })), 
    [hySpread.data]
  );
  const igBps = useMemo(() => 
    igSpread.data.map(d => ({ ...d, value: d.value * 100 })), 
    [igSpread.data]
  );

  // Combine for multi-line chart
  const creditSpreadsData = useMemo(() => {
    if (hyBps.length === 0) return [];
    return hyBps.map((d, i) => ({
      date: d.date,
      highYield: d.value,
      investmentGrade: igBps[i]?.value ?? 0,
    }));
  }, [hyBps, igBps]);

  const fundingRatesData = useMemo(() => {
    if (sofr.data.length === 0) return [];
    return sofr.data.map((d, i) => ({
      date: d.date,
      sofr: d.value,
      effr: fedFunds.data[i]?.value ?? d.value,
    }));
  }, [sofr.data, fedFunds.data]);

  const latestHY = hyBps[hyBps.length - 1]?.value ?? 0;
  const latestIG = igBps[igBps.length - 1]?.value ?? 0;
  const latestStress = stressIndex.data[stressIndex.data.length - 1]?.value ?? 0;
  const avgHY = hyBps.length > 0 
    ? hyBps.reduce((a, b) => a + b.value, 0) / hyBps.length 
    : 0;

  const getStressLevel = (value: number) => {
    if (value < -0.5) return { label: "Low Stress", color: "positive", icon: CheckCircle2 };
    if (value < 0.5) return { label: "Normal", color: "muted-foreground", icon: Activity };
    if (value < 1) return { label: "Elevated", color: "chart-3", icon: TrendingUp };
    return { label: "High Stress", color: "negative", icon: AlertTriangle };
  };

  const stressLevel = getStressLevel(latestStress);

  if (hasError) {
    return (
      <div className="flex h-screen flex-col bg-background">
        <Header
          title="Credit Spreads"
          description="Credit market stress indicators and spread analysis"
          timeRange={timeRange}
          onTimeRangeChange={handleTimeRangeChange}
          onRefresh={handleRefresh}
          isRefreshing={isLoading}
        />
        <div className="flex flex-1 items-center justify-center">
          <Card className="max-w-md">
            <CardContent className="flex flex-col items-center gap-4 p-6">
              <AlertCircle className="h-12 w-12 text-destructive" />
              <h2 className="text-lg font-semibold">Failed to Load Data</h2>
              <p className="text-center text-sm text-muted-foreground">
                Could not connect to the data API. Make sure the Python backend is running:
              </p>
              <code className="rounded bg-muted px-3 py-2 text-sm">
                uvicorn src.api:app --reload
              </code>
            </CardContent>
          </Card>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-screen flex-col bg-background">
      <Header
        title="Credit Spreads"
        description="Credit market stress indicators and spread analysis"
        timeRange={timeRange}
        onTimeRangeChange={handleTimeRangeChange}
        onRefresh={handleRefresh}
        isRefreshing={isLoading}
      />

      <ScrollArea className="flex-1 w-full">
        <div className="bg-dots min-h-full w-full overflow-x-hidden">
          <div className="mx-auto w-full max-w-[1600px] space-y-4 p-3 sm:space-y-6 sm:p-6 overflow-hidden">
            {/* Stress Indicator Hero */}
            <Card className="overflow-hidden">
              <div className="grid lg:grid-cols-3">
                <div className="border-b border-border p-6 lg:border-b-0 lg:border-r">
                  <div className="flex items-center gap-2">
                    <stressLevel.icon className={`h-5 w-5 text-${stressLevel.color}`} />
                    <Badge
                      variant="outline"
                      className={`border-${stressLevel.color}/30 bg-${stressLevel.color}/10 text-${stressLevel.color}`}
                    >
                      {stressLevel.label}
                    </Badge>
                  </div>
                  <p className="mt-4 inline-flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
                    Funding Stress Index
                    <InfoTooltip {...chartDefinitions.stress_index_chart} size="xs" />
                  </p>
                  <p className="mt-2 font-mono text-4xl font-bold tracking-tight">
                    {isLoading ? "..." : latestStress.toFixed(2)}
                  </p>
                  <p className="mt-2 text-xs text-muted-foreground">
                    Z-score composite of credit spreads and funding rates
                  </p>
                  <div className="mt-4">
                    <div className="flex justify-between text-[10px] text-muted-foreground">
                      <span>-2 (Low)</span>
                      <span>0 (Normal)</span>
                      <span>+2 (High)</span>
                    </div>
                    <div className="mt-1 h-2 w-full overflow-hidden rounded-full bg-muted">
                      <div
                        className="h-full rounded-full bg-gradient-to-r from-positive via-chart-3 to-negative transition-all duration-500"
                        style={{
                          width: `${((latestStress + 2) / 4) * 100}%`,
                        }}
                      />
                    </div>
                  </div>
                </div>
                <div className="col-span-2 p-6">
                  {isLoading ? (
                    <div className="flex h-[200px] items-center justify-center">
                      <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                    </div>
                  ) : (
                    <LiquidityChart
                      title="Stress Index History"
                      data={stressIndex.data}
                      chartType="area"
                      color="var(--chart-1)"
                      height={200}
                      showYAxis={true}
                      valueFormatter={(v) => v.toFixed(2)}
                      referenceLine={0}
                      referenceLabel="Normal"
                    />
                  )}
                </div>
              </div>
            </Card>

            {/* Spread Metrics */}
            <div className="grid grid-cols-2 gap-2 sm:gap-4 lg:grid-cols-4">
              <MetricCard
                title="High Yield OAS"
                value={isLoading ? "Loading..." : `${Math.round(latestHY)} bps`}
                change={avgHY !== 0 ? ((latestHY - avgHY) / avgHY) * 100 : 0}
                trend={latestHY > avgHY ? "down" : "up"}
                icon={<TrendingUp className="h-5 w-5" />}
                variant="highlight"
                info={metricDefinitions.hy_spread}
              />
              <MetricCard
                title="Investment Grade OAS"
                value={isLoading ? "Loading..." : `${Math.round(latestIG)} bps`}
                change={-2.1}
                trend="up"
                icon={<TrendingDown className="h-5 w-5" />}
                info={metricDefinitions.ig_spread}
              />
              <MetricCard
                title="HY/IG Ratio"
                value={isLoading ? "..." : `${latestIG > 0 ? (latestHY / latestIG).toFixed(2) : "0"}x`}
                change={0.8}
                trend="neutral"
                icon={<Activity className="h-5 w-5" />}
                info={spreadDefinitions.hy_ig_ratio}
              />
              <MetricCard
                title="vs Period Average"
                value={isLoading ? "..." : `${latestHY > avgHY ? "+" : ""}${Math.round(latestHY - avgHY)} bps`}
                trend={latestHY > avgHY ? "down" : "up"}
                icon={<Activity className="h-5 w-5" />}
              />
            </div>

            {/* Main Charts */}
            <div className="grid gap-3 sm:gap-6 lg:grid-cols-2">
              {isLoading ? (
                <>
                  <Card className="flex h-[350px] items-center justify-center">
                    <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                  </Card>
                  <Card className="flex h-[350px] items-center justify-center">
                    <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                  </Card>
                </>
              ) : (
                <>
                  <MultiLineChart
                    title="Credit Spreads"
                    description="Option-adjusted spreads over Treasuries"
                    data={creditSpreadsData}
                    series={[
                      { key: "highYield", label: "High Yield", color: "var(--chart-5)" },
                      { key: "investmentGrade", label: "Investment Grade", color: "var(--chart-1)" },
                    ]}
                    height={350}
                    valueFormatter={(v) => `${Math.round(v)} bps`}
                    info={chartDefinitions.credit_spreads_chart}
                  />
                  <MultiLineChart
                    title="Funding Rates"
                    description="Key overnight secured rates"
                    data={fundingRatesData}
                    series={[
                      { key: "sofr", label: "SOFR", color: "var(--chart-1)" },
                      { key: "effr", label: "EFFR", color: "var(--chart-2)" },
                    ]}
                    height={350}
                    valueFormatter={(v) => `${v.toFixed(2)}%`}
                    info={chartDefinitions.funding_rates_chart}
                  />
                </>
              )}
            </div>

            {/* Analysis Section */}
            <div className="grid gap-3 sm:gap-6 lg:grid-cols-3">
              <Card className="lg:col-span-2">
                <CardHeader>
                  <CardTitle className="inline-flex items-center gap-2 text-sm font-semibold">
                    Spread Decomposition
                    <InfoTooltip {...spreadDefinitions.spread_decomposition} size="sm" />
                  </CardTitle>
                  <CardDescription className="text-xs">
                    Components of credit risk premium (estimated)
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="space-y-4">
                    {[
                      { name: "Default Risk Premium", value: Math.round(latestHY * 0.45), total: latestHY, color: "var(--chart-1)" },
                      { name: "Liquidity Premium", value: Math.round(latestHY * 0.25), total: latestHY, color: "var(--chart-2)" },
                      { name: "Risk Aversion", value: Math.round(latestHY * 0.18), total: latestHY, color: "var(--chart-3)" },
                      { name: "Other Factors", value: Math.round(latestHY * 0.12), total: latestHY, color: "var(--chart-4)" },
                    ].map((item) => (
                      <div key={item.name} className="space-y-2">
                        <div className="flex items-center justify-between text-sm">
                          <div className="flex items-center gap-2">
                            <div
                              className="h-2 w-2 rounded-full"
                              style={{ backgroundColor: item.color }}
                            />
                            <span>{item.name}</span>
                          </div>
                          <span className="font-mono font-medium">{item.value} bps</span>
                        </div>
                        <Progress
                          value={item.total > 0 ? (item.value / item.total) * 100 : 0}
                          className="h-2"
                          style={{
                            // @ts-expect-error CSS custom property
                            "--progress-background": item.color,
                          }}
                        />
                      </div>
                    ))}
                  </div>
                  <div className="border-t border-border pt-4">
                    <div className="flex items-center justify-between">
                      <span className="font-medium">Total HY Spread</span>
                      <span className="font-mono text-lg font-bold">
                        {isLoading ? "..." : `${Math.round(latestHY)} bps`}
                      </span>
                    </div>
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className="text-sm font-semibold">Historical Context</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="space-y-3">
                    <div className="rounded-lg bg-muted/30 p-3">
                      <p className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                        Period Statistics
                      </p>
                      <p className="mt-1 font-mono text-2xl font-bold">
                        {isLoading ? "..." : `${Math.round(avgHY)} bps`}
                      </p>
                      <p className="text-xs text-muted-foreground">Average HY spread</p>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <div className="rounded-lg bg-positive/5 p-3">
                        <p className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                          Period Low
                        </p>
                        <p className="mt-1 font-mono text-lg font-semibold text-positive">
                          {isLoading || hyBps.length === 0
                            ? "..."
                            : `${Math.round(Math.min(...hyBps.map((d) => d.value)))} bps`}
                        </p>
                      </div>
                      <div className="rounded-lg bg-negative/5 p-3">
                        <p className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                          Period High
                        </p>
                        <p className="mt-1 font-mono text-lg font-semibold text-negative">
                          {isLoading || hyBps.length === 0
                            ? "..."
                            : `${Math.round(Math.max(...hyBps.map((d) => d.value)))} bps`}
                        </p>
                      </div>
                    </div>
                    <div className="rounded-lg border border-border p-3">
                      <p className="inline-flex items-center gap-1.5 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                        Recession Average
                        <InfoTooltip {...spreadDefinitions.recession_comparison} size="xs" />
                      </p>
                      <p className="mt-1 font-mono text-lg font-semibold">750 bps</p>
                      <p className="text-xs text-muted-foreground">
                        Current: {Math.round((latestHY / 750) * 100)}% of recession avg
                      </p>
                    </div>
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


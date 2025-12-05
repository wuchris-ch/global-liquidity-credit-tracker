"use client";

import { useState, useCallback, useMemo } from "react";
import { Header, TimeRange } from "@/components/header";
import { MetricCard } from "@/components/metric-card";
import { LiquidityChart } from "@/components/liquidity-chart";
import { MultiLineChart } from "@/components/multi-line-chart";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { InfoTooltip } from "@/components/info-tooltip";
import {
  Activity,
  Building2,
  CircleDollarSign,
  TrendingDown,
  TrendingUp,
  AlertCircle,
  Loader2,
} from "lucide-react";
import { useSeriesData, useIndexData } from "@/hooks/use-series-data";
import { formatCurrency, UNIT_SCALES } from "@/lib/utils";
import { metricDefinitions, chartDefinitions } from "@/lib/indicator-definitions";

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

export default function DashboardPage() {
  const [timeRange, setTimeRange] = useState<TimeRange>("3m");

  const dateRange = useMemo(() => getDateRange(timeRange), [timeRange]);

  // Fetch real data
  const fedAssets = useSeriesData("fed_total_assets", { ...dateRange });
  const netLiquidity = useIndexData("fed_net_liquidity", { ...dateRange });
  const sofr = useSeriesData("sofr", { ...dateRange });
  const fedFunds = useSeriesData("fed_funds_rate", { ...dateRange });
  const hySpread = useSeriesData("ice_bofa_us_high_yield_spread", { ...dateRange });
  const igSpread = useSeriesData("ice_bofa_us_ig_spread", { ...dateRange });
  const ecbAssets = useSeriesData("ecb_total_assets", { ...dateRange });
  const bojAssets = useSeriesData("boj_total_assets", { ...dateRange });

  const isLoading = fedAssets.isLoading || netLiquidity.isLoading || sofr.isLoading || hySpread.isLoading;
  const hasError = fedAssets.error || netLiquidity.error || sofr.error || hySpread.error;

  const handleRefresh = useCallback(async () => {
    await Promise.all([
      fedAssets.refetch(),
      netLiquidity.refetch(),
      sofr.refetch(),
      fedFunds.refetch(),
      hySpread.refetch(),
      igSpread.refetch(),
    ]);
  }, [fedAssets, netLiquidity, sofr, fedFunds, hySpread, igSpread]);

  const handleTimeRangeChange = useCallback((range: TimeRange) => {
    setTimeRange(range);
  }, []);

  // Scale factors for different unit types
  const scaleMillions = UNIT_SCALES.millions_usd;

  // Get latest values (scaled to base currency)
  const latestFed = (fedAssets.data[fedAssets.data.length - 1]?.value ?? 0) * scaleMillions;
  const latestNet = (netLiquidity.data[netLiquidity.data.length - 1]?.value ?? 0) * scaleMillions;
  const latestSofr = sofr.data[sofr.data.length - 1]?.value ?? 0;
  const latestHY = (hySpread.data[hySpread.data.length - 1]?.value ?? 0) * 100; // Convert to bps

  // Calculate changes
  const calcChange = (data: { date: string; value: number }[], periods = 7) => {
    if (data.length < periods + 1) return 0;
    const latest = data[data.length - 1]?.value ?? 0;
    const prev = data[data.length - periods - 1]?.value ?? latest;
    return prev !== 0 ? ((latest - prev) / prev) * 100 : 0;
  };

  // Prepare multi-line chart data
  const fundingRatesData = useMemo(() => {
    if (sofr.data.length === 0) return [];
    return sofr.data.map((d, i) => ({
      date: d.date,
      sofr: d.value,
      effr: fedFunds.data[i]?.value ?? d.value,
    }));
  }, [sofr.data, fedFunds.data]);

  const creditSpreadsData = useMemo(() => {
    if (hySpread.data.length === 0) return [];
    return hySpread.data.map((d, i) => ({
      date: d.date,
      highYield: d.value * 100, // Convert to bps
      investmentGrade: (igSpread.data[i]?.value ?? 0) * 100,
    }));
  }, [hySpread.data, igSpread.data]);

  // Normalize central bank data to 100
  const centralBankData = useMemo(() => {
    if (fedAssets.data.length === 0) return [];
    const fedBase = fedAssets.data[0]?.value || 1;
    const ecbBase = ecbAssets.data[0]?.value || 1;
    const bojBase = bojAssets.data[0]?.value || 1;
    
    return fedAssets.data.map((d, i) => ({
      date: d.date,
      fed: (d.value / fedBase) * 100,
      ecb: ecbAssets.data[i] ? (ecbAssets.data[i].value / ecbBase) * 100 : 100,
      boj: bojAssets.data[i] ? (bojAssets.data[i].value / bojBase) * 100 : 100,
    }));
  }, [fedAssets.data, ecbAssets.data, bojAssets.data]);

  if (hasError) {
    return (
      <div className="flex h-screen flex-col bg-background">
        <Header
          title="Dashboard"
          description="Real-time global liquidity and credit metrics"
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
        title="Dashboard"
        description="Real-time global liquidity and credit metrics"
        timeRange={timeRange}
        onTimeRangeChange={handleTimeRangeChange}
        onRefresh={handleRefresh}
        isRefreshing={isLoading}
      />

      <ScrollArea className="flex-1 w-full">
        <div className="bg-dots min-h-full w-full overflow-x-hidden">
          <div className="mx-auto w-full max-w-[1600px] space-y-4 p-3 sm:space-y-6 sm:p-6 overflow-hidden">
            {/* Hero Metrics */}
            <div className="grid grid-cols-2 gap-2 sm:gap-4 lg:grid-cols-4">
              <MetricCard
                title="Fed Balance Sheet"
                value={isLoading ? "Loading..." : formatCurrency(latestFed)}
                change={calcChange(fedAssets.data)}
                trend={calcChange(fedAssets.data) >= 0 ? "up" : "down"}
                icon={<Building2 className="h-5 w-5" />}
                variant="highlight"
                info={metricDefinitions.fed_balance_sheet}
              />
              <MetricCard
                title="SOFR Rate"
                value={isLoading ? "Loading..." : `${latestSofr.toFixed(2)}%`}
                change={sofr.data.length > 7 ? (sofr.data[sofr.data.length - 1]?.value ?? 0) - (sofr.data[sofr.data.length - 8]?.value ?? 0) : 0}
                changeLabel="vs last week"
                trend="neutral"
                icon={<CircleDollarSign className="h-5 w-5" />}
                info={metricDefinitions.sofr_rate}
              />
              <MetricCard
                title="HY Spread"
                value={isLoading ? "Loading..." : `${Math.round(latestHY)} bps`}
                change={calcChange(hySpread.data)}
                changeLabel="bps"
                trend={calcChange(hySpread.data) <= 0 ? "up" : "down"}
                icon={<TrendingUp className="h-5 w-5" />}
                info={metricDefinitions.hy_spread}
              />
              <MetricCard
                title="Net Liquidity"
                value={isLoading ? "Loading..." : formatCurrency(latestNet)}
                change={calcChange(netLiquidity.data)}
                trend={calcChange(netLiquidity.data) >= 0 ? "up" : "down"}
                icon={<Activity className="h-5 w-5" />}
                info={metricDefinitions.net_liquidity}
              />
            </div>

            {/* Main Charts */}
            <div className="grid gap-3 sm:gap-6 lg:grid-cols-2">
              {isLoading ? (
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
                    title="Federal Reserve Balance Sheet"
                    description="Total assets held by the Federal Reserve"
                    data={fedAssets.data.map(d => ({ ...d, value: d.value * scaleMillions }))}
                    color="var(--chart-1)"
                    height={320}
                    valueFormatter={(v) => formatCurrency(v)}
                    info={chartDefinitions.fed_balance_sheet_chart}
                  />
                  <LiquidityChart
                    title="Fed Net Liquidity"
                    description="Total Assets - TGA - Reverse Repo"
                    data={netLiquidity.data.map(d => ({ ...d, value: d.value * scaleMillions }))}
                    color="var(--chart-2)"
                    height={320}
                    valueFormatter={(v) => formatCurrency(v)}
                    info={chartDefinitions.net_liquidity_chart}
                  />
                </>
              )}
            </div>

            {/* Tabbed Section */}
            <Tabs defaultValue="rates" className="space-y-3 sm:space-y-4">
              <TabsList className="grid w-full max-w-full grid-cols-3 gap-1 h-auto p-1 sm:max-w-md">
                <TabsTrigger value="rates" className="text-xs">
                  Funding Rates
                </TabsTrigger>
                <TabsTrigger value="spreads" className="text-xs">
                  Credit Spreads
                </TabsTrigger>
                <TabsTrigger value="central-banks" className="text-xs">
                  Central Banks
                </TabsTrigger>
              </TabsList>

              <TabsContent value="rates" className="space-y-3 sm:space-y-4">
                <div className="grid gap-3 sm:gap-6 lg:grid-cols-3">
                  <div className="lg:col-span-2">
                    {isLoading ? (
                      <Card className="flex h-[350px] items-center justify-center">
                        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                      </Card>
                    ) : (
                      <MultiLineChart
                        title="Funding Rates"
                        description="Key overnight secured rates comparison"
                        data={fundingRatesData}
                        series={[
                          { key: "sofr", label: "SOFR", color: "var(--chart-1)" },
                          { key: "effr", label: "EFFR", color: "var(--chart-2)" },
                        ]}
                        height={350}
                        info={chartDefinitions.funding_rates_chart}
                      />
                    )}
                  </div>
                  <Card>
                    <CardHeader className="pb-3">
                      <CardTitle className="text-sm font-semibold">Rate Summary</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      <div className="space-y-3">
                        <div className="flex items-center justify-between rounded-lg bg-muted/30 p-3">
                          <div>
                            <p className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
                              SOFR
                              <InfoTooltip {...metricDefinitions.sofr_rate} size="xs" />
                            </p>
                            <p className="font-mono text-lg font-bold">
                              {isLoading ? "..." : `${latestSofr.toFixed(2)}%`}
                            </p>
                          </div>
                          <div className="flex items-center gap-1 text-muted-foreground">
                            <span className="font-mono text-xs">Live</span>
                          </div>
                        </div>
                        <div className="flex items-center justify-between rounded-lg bg-muted/30 p-3">
                          <div>
                            <p className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
                              EFFR
                              <InfoTooltip {...metricDefinitions.effr} size="xs" />
                            </p>
                            <p className="font-mono text-lg font-bold">
                              {isLoading ? "..." : `${(fedFunds.data[fedFunds.data.length - 1]?.value ?? 0).toFixed(2)}%`}
                            </p>
                          </div>
                          <div className="flex items-center gap-1 text-muted-foreground">
                            <span className="font-mono text-xs">Live</span>
                          </div>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                </div>
              </TabsContent>

              <TabsContent value="spreads" className="space-y-3 sm:space-y-4">
                <div className="grid gap-3 sm:gap-6 lg:grid-cols-3">
                  <div className="lg:col-span-2">
                    {isLoading ? (
                      <Card className="flex h-[350px] items-center justify-center">
                        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                      </Card>
                    ) : (
                      <MultiLineChart
                        title="Credit Spreads"
                        description="Option-adjusted spreads vs Treasuries"
                        data={creditSpreadsData}
                        series={[
                          { key: "highYield", label: "High Yield", color: "var(--chart-5)" },
                          { key: "investmentGrade", label: "Investment Grade", color: "var(--chart-1)" },
                        ]}
                        height={350}
                        valueFormatter={(v) => `${Math.round(v)} bps`}
                        info={chartDefinitions.credit_spreads_chart}
                      />
                    )}
                  </div>
                  <Card>
                    <CardHeader className="pb-3">
                      <CardTitle className="text-sm font-semibold">Spread Analysis</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      <div className="space-y-3">
                        <div className="rounded-lg border border-negative/20 bg-negative/5 p-3">
                          <p className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
                            High Yield OAS
                            <InfoTooltip {...metricDefinitions.hy_spread} size="xs" />
                          </p>
                          <div className="flex items-baseline gap-2">
                            <p className="font-mono text-2xl font-bold text-negative">
                              {isLoading ? "..." : Math.round(latestHY)}
                            </p>
                            <span className="text-xs text-muted-foreground">bps</span>
                          </div>
                        </div>
                        <div className="rounded-lg border border-positive/20 bg-positive/5 p-3">
                          <p className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
                            Investment Grade OAS
                            <InfoTooltip {...metricDefinitions.ig_spread} size="xs" />
                          </p>
                          <div className="flex items-baseline gap-2">
                            <p className="font-mono text-2xl font-bold text-positive">
                              {isLoading ? "..." : Math.round((igSpread.data[igSpread.data.length - 1]?.value ?? 0) * 100)}
                            </p>
                            <span className="text-xs text-muted-foreground">bps</span>
                          </div>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                </div>
              </TabsContent>

              <TabsContent value="central-banks" className="space-y-3 sm:space-y-4">
                <div className="grid gap-3 sm:gap-6 lg:grid-cols-3">
                  <div className="lg:col-span-2">
                    {isLoading ? (
                      <Card className="flex h-[350px] items-center justify-center">
                        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                      </Card>
                    ) : (
                      <MultiLineChart
                        title="Central Bank Balance Sheets"
                        description="Indexed to 100 at start of period"
                        data={centralBankData}
                        series={[
                          { key: "fed", label: "Federal Reserve", color: "var(--chart-1)" },
                          { key: "ecb", label: "ECB", color: "var(--chart-3)" },
                          { key: "boj", label: "Bank of Japan", color: "var(--chart-4)" },
                        ]}
                        height={350}
                        normalized
                        info={chartDefinitions.central_banks_chart}
                      />
                    )}
                  </div>
                  <Card>
                    <CardHeader className="pb-3">
                      <CardTitle className="text-sm font-semibold">Balance Sheet Changes</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      <div className="space-y-3">
                        <div className="flex items-center justify-between rounded-lg bg-muted/30 p-3">
                          <div className="flex items-center gap-3">
                            <div className="h-2 w-2 rounded-full" style={{ backgroundColor: "var(--chart-1)" }} />
                            <div>
                              <p className="text-xs font-medium">Federal Reserve</p>
                              <p className="font-mono text-sm font-bold">
                                {isLoading ? "..." : formatCurrency(latestFed)}
                              </p>
                            </div>
                          </div>
                          <span className={`font-mono text-xs ${calcChange(fedAssets.data) >= 0 ? "text-positive" : "text-negative"}`}>
                            {calcChange(fedAssets.data) >= 0 ? "+" : ""}{calcChange(fedAssets.data).toFixed(1)}%
                          </span>
                        </div>
                        <div className="flex items-center justify-between rounded-lg bg-muted/30 p-3">
                          <div className="flex items-center gap-3">
                            <div className="h-2 w-2 rounded-full" style={{ backgroundColor: "var(--chart-3)" }} />
                            <div>
                              <p className="text-xs font-medium">ECB</p>
                              <p className="font-mono text-sm font-bold">
                                {isLoading || ecbAssets.data.length === 0 ? "..." : formatCurrency((ecbAssets.data[ecbAssets.data.length - 1]?.value ?? 0) * scaleMillions, 2, "€")}
                              </p>
                            </div>
                          </div>
                          <span className={`font-mono text-xs ${calcChange(ecbAssets.data) >= 0 ? "text-positive" : "text-negative"}`}>
                            {calcChange(ecbAssets.data) >= 0 ? "+" : ""}{calcChange(ecbAssets.data).toFixed(1)}%
                          </span>
                        </div>
                        <div className="flex items-center justify-between rounded-lg bg-muted/30 p-3">
                          <div className="flex items-center gap-3">
                            <div className="h-2 w-2 rounded-full" style={{ backgroundColor: "var(--chart-4)" }} />
                            <div>
                              <p className="text-xs font-medium">Bank of Japan</p>
                              <p className="font-mono text-sm font-bold">
                                {isLoading || bojAssets.data.length === 0 ? "..." : formatCurrency((bojAssets.data[bojAssets.data.length - 1]?.value ?? 0) * scaleMillions, 0, "¥")}
                              </p>
                            </div>
                          </div>
                          <span className={`font-mono text-xs ${calcChange(bojAssets.data) >= 0 ? "text-positive" : "text-negative"}`}>
                            {calcChange(bojAssets.data) >= 0 ? "+" : ""}{calcChange(bojAssets.data).toFixed(1)}%
                          </span>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                </div>
              </TabsContent>
            </Tabs>

            {/* Bottom Charts */}
            <div className="grid gap-3 sm:gap-6 lg:grid-cols-2">
              {isLoading ? (
                <>
                  <Card className="flex h-[250px] items-center justify-center">
                    <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                  </Card>
                  <Card className="flex h-[250px] items-center justify-center">
                    <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                  </Card>
                </>
              ) : (
                <>
                  <LiquidityChart
                    title="SOFR Rate"
                    description="Secured Overnight Financing Rate"
                    data={sofr.data}
                    chartType="line"
                    color="var(--chart-2)"
                    height={250}
                    valueFormatter={(v) => `${v.toFixed(2)}%`}
                    info={chartDefinitions.sofr_rate_chart}
                  />
                  <LiquidityChart
                    title="High Yield Spread"
                    description="ICE BofA US High Yield Index OAS"
                    data={hySpread.data.map(d => ({ ...d, value: d.value * 100 }))}
                    color="var(--chart-5)"
                    height={250}
                    valueFormatter={(v) => `${Math.round(v)} bps`}
                    info={chartDefinitions.hy_spread_chart}
                  />
                </>
              )}
            </div>
          </div>
        </div>
      </ScrollArea>
    </div>
  );
}

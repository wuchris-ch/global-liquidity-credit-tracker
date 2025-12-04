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
  Wallet,
  AlertCircle,
  Loader2,
} from "lucide-react";
import { useSeriesData, useIndexData } from "@/hooks/use-series-data";
import { formatCurrency, UNIT_SCALES } from "@/lib/utils";
import { metricDefinitions, chartDefinitions } from "@/lib/indicator-definitions";

// Define unit types for the series we're displaying
// Values from FRED come in these units, we need to scale to base dollars for display
const SERIES_UNITS = {
  fed_total_assets: "millions_usd",
  fed_treasury_general_account: "millions_usd",
  fed_reverse_repo: "billions_usd",
  fed_net_liquidity: "millions_usd", // Computed index is in millions
} as const;

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
  return { start: start.toISOString().split("T")[0], end: end.toISOString().split("T")[0] };
}

export default function LiquidityPage() {
  const [timeRange, setTimeRange] = useState<TimeRange>("1y");
  const dateRange = useMemo(() => getDateRange(timeRange), [timeRange]);

  const fedAssets = useSeriesData("fed_total_assets", { ...dateRange });
  const tga = useSeriesData("fed_treasury_general_account", { ...dateRange });
  const rrp = useSeriesData("fed_reverse_repo", { ...dateRange });
  const netLiquidity = useIndexData("fed_net_liquidity", { ...dateRange });

  const isLoading = fedAssets.isLoading || tga.isLoading || rrp.isLoading || netLiquidity.isLoading;
  const hasError = fedAssets.error || tga.error || rrp.error || netLiquidity.error;

  const handleRefresh = useCallback(async () => {
    await Promise.all([fedAssets.refetch(), tga.refetch(), rrp.refetch(), netLiquidity.refetch()]);
  }, [fedAssets, tga, rrp, netLiquidity]);

  const handleTimeRangeChange = useCallback((range: TimeRange) => setTimeRange(range), []);

  // Scale raw values to base dollars using their unit multipliers
  const scaleMillions = UNIT_SCALES.millions_usd;
  const scaleBillions = UNIT_SCALES.billions_usd;

  const latestFed = (fedAssets.data[fedAssets.data.length - 1]?.value ?? 0) * scaleMillions;
  const latestTga = (tga.data[tga.data.length - 1]?.value ?? 0) * scaleMillions;
  const latestRrp = (rrp.data[rrp.data.length - 1]?.value ?? 0) * scaleBillions;
  const latestNet = (netLiquidity.data[netLiquidity.data.length - 1]?.value ?? 0) * scaleMillions;

  const calcChange = (data: { date: string; value: number }[]) => {
    if (data.length < 8) return 0;
    const latest = data[data.length - 1]?.value ?? 0;
    const prev = data[data.length - 8]?.value ?? latest;
    return prev !== 0 ? ((latest - prev) / prev) * 100 : 0;
  };

  if (hasError) {
    return (
      <div className="flex h-screen flex-col bg-background">
        <Header title="Liquidity Monitor" description="Federal Reserve balance sheet and net liquidity tracking" timeRange={timeRange} onTimeRangeChange={handleTimeRangeChange} onRefresh={handleRefresh} isRefreshing={isLoading} />
        <div className="flex flex-1 items-center justify-center">
          <Card className="max-w-md">
            <CardContent className="flex flex-col items-center gap-4 p-6">
              <AlertCircle className="h-12 w-12 text-destructive" />
              <h2 className="text-lg font-semibold">Failed to Load Data</h2>
              <p className="text-center text-sm text-muted-foreground">Could not connect to the data API. Make sure the Python backend is running:</p>
              <code className="rounded bg-muted px-3 py-2 text-sm">uvicorn src.api:app --reload</code>
            </CardContent>
          </Card>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-screen flex-col bg-background">
      <Header title="Liquidity Monitor" description="Federal Reserve balance sheet and net liquidity tracking" timeRange={timeRange} onTimeRangeChange={handleTimeRangeChange} onRefresh={handleRefresh} isRefreshing={isLoading} />
      <ScrollArea className="flex-1">
        <div className="bg-grid min-h-full">
          <div className="mx-auto w-full max-w-[1600px] space-y-6 p-6">
            <Card className="border-primary/20 bg-gradient-to-r from-primary/5 via-card to-card">
              <CardContent className="p-6">
                <div className="flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
                  <div>
                    <Badge className="mb-3 bg-primary/20 text-primary hover:bg-primary/30">Key Formula</Badge>
                    <h2 className="inline-flex items-center gap-2 text-xl font-bold tracking-tight">
                      Fed Net Liquidity
                      <InfoTooltip {...metricDefinitions.net_liquidity} size="sm" />
                    </h2>
                    <p className="mt-1 text-sm text-muted-foreground">A measure of actual liquidity available in the financial system</p>
                  </div>
                  <div className="flex flex-wrap items-center gap-3 font-mono text-sm lg:gap-4 lg:text-base">
                    <div className="flex items-center gap-2 rounded-lg bg-muted/50 px-4 py-2">
                      <Building2 className="h-4 w-4 text-chart-1" />
                      <span>Fed Assets</span>
                      <InfoTooltip {...metricDefinitions.fed_balance_sheet} size="xs" />
                    </div>
                    <span className="text-muted-foreground">−</span>
                    <div className="flex items-center gap-2 rounded-lg bg-muted/50 px-4 py-2">
                      <Landmark className="h-4 w-4 text-chart-3" />
                      <span>TGA</span>
                      <InfoTooltip {...metricDefinitions.tga} size="xs" />
                    </div>
                    <span className="text-muted-foreground">−</span>
                    <div className="flex items-center gap-2 rounded-lg bg-muted/50 px-4 py-2">
                      <Wallet className="h-4 w-4 text-chart-4" />
                      <span>RRP</span>
                      <InfoTooltip {...metricDefinitions.rrp} size="xs" />
                    </div>
                    <span className="text-muted-foreground">=</span>
                    <div className="flex items-center gap-2 rounded-lg border-2 border-primary/30 bg-primary/10 px-4 py-2"><Activity className="h-4 w-4 text-primary" /><span className="font-semibold text-primary">Net Liquidity</span></div>
                  </div>
                </div>
              </CardContent>
            </Card>

            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
              <MetricCard title="Fed Total Assets" value={isLoading ? "Loading..." : formatCurrency(latestFed)} change={calcChange(fedAssets.data)} trend={calcChange(fedAssets.data) >= 0 ? "up" : "down"} icon={<Building2 className="h-5 w-5" />} variant="highlight" info={metricDefinitions.fed_balance_sheet} />
              <MetricCard title="Treasury General Account" value={isLoading ? "Loading..." : formatCurrency(latestTga)} change={calcChange(tga.data)} trend={calcChange(tga.data) >= 0 ? "up" : "down"} icon={<Landmark className="h-5 w-5" />} info={metricDefinitions.tga} />
              <MetricCard title="Reverse Repo Facility" value={isLoading ? "Loading..." : formatCurrency(latestRrp)} change={calcChange(rrp.data)} trend={calcChange(rrp.data) >= 0 ? "up" : "down"} icon={<Wallet className="h-5 w-5" />} info={metricDefinitions.rrp} />
              <MetricCard title="Net Liquidity" value={isLoading ? "Loading..." : formatCurrency(latestNet)} change={calcChange(netLiquidity.data)} trend={calcChange(netLiquidity.data) >= 0 ? "up" : "down"} icon={<Activity className="h-5 w-5" />} variant="highlight" info={metricDefinitions.net_liquidity} />
            </div>

            {isLoading ? (
              <Card className="flex h-[400px] items-center justify-center"><Loader2 className="h-8 w-8 animate-spin text-muted-foreground" /></Card>
            ) : (
              <LiquidityChart title="Fed Net Liquidity" description="Total Assets minus TGA and Reverse Repo" data={netLiquidity.data.map(d => ({ ...d, value: d.value * scaleMillions }))} color="var(--chart-1)" height={400} valueFormatter={(v) => formatCurrency(v)} info={chartDefinitions.net_liquidity_chart} />
            )}

            <div className="grid gap-6 lg:grid-cols-3">
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

            <div className="grid gap-6 lg:grid-cols-2">
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
                      <div><p className="text-xs text-muted-foreground">Current Net Liquidity</p><p className="font-mono text-xl font-bold">{isLoading ? "..." : formatCurrency(latestNet)}</p></div>
                      <Badge variant="outline" className="border-positive/30 text-positive">Live Data</Badge>
                    </div>
                      <div className="grid grid-cols-2 gap-4">
                      <div className="rounded-lg bg-muted/30 p-3"><p className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">Period High</p><p className="mt-1 font-mono text-lg font-semibold">{isLoading || netLiquidity.data.length === 0 ? "..." : formatCurrency(Math.max(...netLiquidity.data.map((d) => d.value)) * scaleMillions)}</p></div>
                      <div className="rounded-lg bg-muted/30 p-3"><p className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">Period Low</p><p className="mt-1 font-mono text-lg font-semibold">{isLoading || netLiquidity.data.length === 0 ? "..." : formatCurrency(Math.min(...netLiquidity.data.map((d) => d.value)) * scaleMillions)}</p></div>
                    </div>
                    <div className="rounded-lg border border-primary/20 bg-primary/5 p-3"><p className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">Critical Support Level</p><p className="mt-1 font-mono text-lg font-semibold text-primary">$5.5T</p><p className="mt-1 text-xs text-muted-foreground">Historically correlates with market stress</p></div>
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


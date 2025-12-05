"use client";

import { useState, useCallback, useMemo, useEffect } from "react";
import { Header, TimeRange } from "@/components/header";
import { MetricCard } from "@/components/metric-card";
import { LiquidityChart } from "@/components/liquidity-chart";
import { MultiLineChart } from "@/components/multi-line-chart";
import { WaterfallChart, ContributionBreakdown } from "@/components/waterfall-chart";
import { RegimeTimeline, RegimeBadge } from "@/components/regime-timeline";
import { DataFreshness, FreshnessSummary } from "@/components/data-freshness";
import { PredictivePanel } from "@/components/predictive-panel";
import { InfoTooltip } from "@/components/info-tooltip";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Activity,
  AlertCircle,
  ArrowDown,
  ArrowUp,
  Gauge,
  Loader2,
  TrendingDown,
  TrendingUp,
  Waves,
  CreditCard,
  AlertTriangle,
  BarChart3,
  Clock,
} from "lucide-react";
import { useGLCIData } from "@/hooks/use-series-data";
import api, { DataFreshnessItem, RegimeHistory } from "@/lib/api";
import { glciDefinitions, chartDefinitions } from "@/lib/indicator-definitions";

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

const regimeConfig = {
  tight: {
    color: "text-regime-tight",
    bgColor: "bg-regime-tight/10",
    borderColor: "border-regime-tight/30",
    label: "Tight",
    description: "Restrictive liquidity conditions",
    icon: TrendingDown,
  },
  neutral: {
    color: "text-regime-neutral",
    bgColor: "bg-regime-neutral/10",
    borderColor: "border-regime-neutral/30",
    label: "Neutral",
    description: "Balanced liquidity conditions",
    icon: Activity,
  },
  loose: {
    color: "text-emerald-500",
    bgColor: "bg-emerald-500/10",
    borderColor: "border-emerald-500/30",
    label: "Loose",
    description: "Expansionary liquidity conditions",
    icon: TrendingUp,
  },
};

const pillarConfig = {
  liquidity: {
    label: "Liquidity",
    description: "Central bank balance sheets & monetary aggregates",
    icon: Waves,
    color: "var(--pillar-liquidity)",
    info: glciDefinitions.pillar_liquidity,
  },
  credit: {
    label: "Credit",
    description: "Private sector credit growth & credit/GDP",
    icon: CreditCard,
    color: "var(--pillar-credit)",
    info: glciDefinitions.pillar_credit,
  },
  stress: {
    label: "Funding Stress",
    description: "Credit spreads & funding rates (inverted)",
    icon: AlertTriangle,
    color: "var(--pillar-stress)",
    info: glciDefinitions.pillar_stress,
  },
};

export default function GLCIPage() {
  const [timeRange, setTimeRange] = useState<TimeRange>("5y");
  const [activeTab, setActiveTab] = useState<string>("overview");
  const [freshnessData, setFreshnessData] = useState<DataFreshnessItem[]>([]);
  const [regimeHistory, setRegimeHistory] = useState<RegimeHistory | null>(null);
  
  const dateRange = useMemo(() => getDateRange(timeRange), [timeRange]);
  const { data: glciData, isLoading, error, refetch } = useGLCIData({ ...dateRange });

  // Fetch additional data
  useEffect(() => {
    api.getGLCIFreshness().then(setFreshnessData).catch(console.error);
    api.getRegimeHistory(dateRange.start, dateRange.end).then(setRegimeHistory).catch(console.error);
  }, [dateRange]);

  const handleRefresh = useCallback(async () => {
    await refetch();
    api.getGLCIFreshness().then(setFreshnessData).catch(console.error);
  }, [refetch]);

  const handleTimeRangeChange = useCallback((range: TimeRange) => setTimeRange(range), []);

  // Calculate change from period
  const calcChange = (data: { date: string; value: number }[] | undefined, periods: number = 8) => {
    if (!data || data.length < periods) return 0;
    const latest = data[data.length - 1]?.value ?? 0;
    const prev = data[data.length - periods]?.value ?? latest;
    return latest - prev;
  };

  const regime = glciData?.regime || "neutral";
  const regimeInfo = regimeConfig[regime as keyof typeof regimeConfig] || regimeConfig.neutral;
  const RegimeIcon = regimeInfo.icon;

  // Prepare pillar chart data
  const pillarChartData = useMemo(() => {
    if (!glciData?.pillar_data) return [];
    const liquidity = glciData.pillar_data.liquidity || [];
    const credit = glciData.pillar_data.credit || [];
    const stress = glciData.pillar_data.stress || [];
    
    return liquidity.map((d, i) => ({
      date: d.date,
      liquidity: d.value,
      credit: credit[i]?.value ?? 0,
      stress: stress[i]?.value ?? 0,
    }));
  }, [glciData]);

  // Previous week's GLCI value for waterfall
  const previousValue = useMemo(() => {
    if (!glciData?.data || glciData.data.length < 2) return glciData?.value ?? 100;
    return glciData.data[glciData.data.length - 2]?.value ?? glciData.value;
  }, [glciData]);

  if (error) {
    return (
      <div className="flex h-screen flex-col bg-background">
        <Header
          title="GLCI"
          description="Global Liquidity & Credit Index"
          timeRange={timeRange}
          onTimeRangeChange={handleTimeRangeChange}
          onRefresh={handleRefresh}
          isRefreshing={isLoading}
        />
        <div className="flex flex-1 items-center justify-center">
          <Card className="max-w-md">
            <CardContent className="flex flex-col items-center gap-4 p-6">
              <AlertCircle className="h-12 w-12 text-destructive" />
              <h2 className="text-lg font-semibold">Failed to Load GLCI</h2>
              <p className="text-center text-sm text-muted-foreground">
                Could not compute the Global Liquidity & Credit Index. Make sure the Python backend is running:
              </p>
              <code className="rounded bg-muted px-3 py-2 text-sm">
                uvicorn src.api.server:app --reload
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
        title="GLCI"
        description="Global Liquidity & Credit Index"
        timeRange={timeRange}
        onTimeRangeChange={handleTimeRangeChange}
        onRefresh={handleRefresh}
        isRefreshing={isLoading}
      />

      <ScrollArea className="flex-1 w-full">
        <div className="bg-dots min-h-full w-full overflow-x-hidden">
          <div className="mx-auto w-full max-w-[1800px] space-y-3 p-2 min-[360px]:p-3 sm:space-y-6 sm:p-6 overflow-hidden">
            {/* Hero Section */}
            <div className="grid gap-3 sm:gap-6 lg:grid-cols-3">
              {/* Main GLCI Value */}
              <Card className="lg:col-span-2 border-primary/20 bg-gradient-to-br from-primary/5 via-card to-card overflow-hidden">
                <CardContent className="p-4 sm:p-6">
                  <div className="flex flex-col gap-4 sm:gap-6">
                    {/* Top row: GLCI value and regime on mobile */}
                    <div className="flex items-start justify-between gap-3">
                      <div className="space-y-3 sm:space-y-4 flex-1 min-w-0">
                        <div className="flex items-center gap-2 sm:gap-3">
                          <div className="flex h-10 w-10 sm:h-12 sm:w-12 items-center justify-center rounded-xl bg-foreground shadow-lg shrink-0">
                            <Gauge className="h-5 w-5 sm:h-6 sm:w-6 text-background" />
                          </div>
                          <div className="min-w-0">
                            <p className="inline-flex items-center gap-1.5 text-xs sm:text-sm font-medium text-muted-foreground">
                              Global Liquidity & Credit Index
                              <InfoTooltip {...glciDefinitions.glci_index} size="sm" />
                            </p>
                            <p className="text-[10px] sm:text-xs text-muted-foreground/70">Tri-pillar composite indicator</p>
                          </div>
                        </div>
                        
                        <div className="flex items-baseline gap-2 sm:gap-4 flex-wrap">
                          {isLoading ? (
                            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                          ) : (
                            <>
                              <span className="font-mono text-3xl sm:text-5xl font-bold tracking-tight">
                                {glciData?.value.toFixed(1) ?? "—"}
                              </span>
                              <div className="flex items-center gap-1">
                                {calcChange(glciData?.data) >= 0 ? (
                                  <ArrowUp className="h-4 w-4 text-positive" />
                                ) : (
                                  <ArrowDown className="h-4 w-4 text-negative" />
                                )}
                                <span className={`font-mono text-sm ${calcChange(glciData?.data) >= 0 ? "text-positive" : "text-negative"}`}>
                                  {calcChange(glciData?.data) >= 0 ? "+" : ""}{calcChange(glciData?.data).toFixed(1)}
                                </span>
                                <span className="text-xs text-muted-foreground">vs last week</span>
                              </div>
                            </>
                          )}
                        </div>
                      </div>

                      {/* Regime indicator - always visible, compact on mobile */}
                      <div className="flex flex-col items-center gap-1.5 sm:gap-2 shrink-0">
                        <div className={`rounded-xl sm:rounded-2xl border-2 ${regimeInfo.borderColor} ${regimeInfo.bgColor} p-3 sm:p-6`}>
                          <RegimeIcon className={`h-6 w-6 sm:h-10 sm:w-10 ${regimeInfo.color}`} />
                        </div>
                        <Badge variant="outline" className={`${regimeInfo.borderColor} ${regimeInfo.color} text-[10px] sm:text-sm font-semibold px-1.5 sm:px-2`}>
                          {regimeInfo.label} Regime
                        </Badge>
                        <p className="text-center text-[10px] sm:text-xs text-muted-foreground max-w-[100px] sm:max-w-[150px] hidden sm:block">
                          {regimeInfo.description}
                        </p>
                      </div>
                    </div>

                    {/* Stats row */}
                    <div className="flex flex-wrap items-center gap-3 sm:gap-4">
                      <div className="flex items-center gap-1.5 sm:gap-2">
                        <span className="inline-flex items-center gap-1 text-[10px] sm:text-xs text-muted-foreground">
                          Z-Score:
                          <InfoTooltip {...glciDefinitions.glci_zscore} size="xs" />
                        </span>
                        <span className="font-mono text-xs sm:text-sm font-semibold">
                          {glciData?.zscore?.toFixed(2) ?? "—"}
                        </span>
                      </div>
                      <div className="flex items-center gap-1.5 sm:gap-2">
                        <span className="inline-flex items-center gap-1 text-[10px] sm:text-xs text-muted-foreground">
                          Momentum:
                          <InfoTooltip {...glciDefinitions.glci_momentum} size="xs" />
                        </span>
                        <span className={`font-mono text-xs sm:text-sm font-semibold ${(glciData?.momentum ?? 0) >= 0 ? "text-positive" : "text-negative"}`}>
                          {(glciData?.momentum ?? 0) >= 0 ? "+" : ""}{(glciData?.momentum ?? 0).toFixed(2)}
                        </span>
                      </div>
                    </div>

                    {/* Data freshness summary */}
                    {freshnessData.length > 0 && (
                      <FreshnessSummary items={freshnessData} />
                    )}
                  </div>
                </CardContent>
              </Card>

              {/* Pillar Breakdown */}
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm font-semibold">Pillar Contributions</CardTitle>
                  <CardDescription className="text-xs">Weighted factor scores</CardDescription>
                </CardHeader>
                <CardContent>
                  {isLoading ? (
                    <div className="flex h-[200px] items-center justify-center">
                      <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                    </div>
                  ) : glciData?.pillars ? (
                    <ContributionBreakdown pillars={glciData.pillars} />
                  ) : null}
                </CardContent>
              </Card>
            </div>

            {/* Tabs for different views */}
            <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-3 sm:space-y-4">
              <TabsList className="grid w-full grid-cols-2 gap-1 sm:gap-2 h-auto p-1 md:max-w-lg md:grid-cols-4">
                <TabsTrigger value="overview" className="gap-2 text-xs sm:text-sm">
                  <BarChart3 className="h-3.5 w-3.5" />
                  Overview
                </TabsTrigger>
                <TabsTrigger value="pillars" className="gap-2 text-xs sm:text-sm">
                  <Activity className="h-3.5 w-3.5" />
                  Pillars
                </TabsTrigger>
                <TabsTrigger value="analytics" className="gap-2 text-xs sm:text-sm">
                  <TrendingUp className="h-3.5 w-3.5" />
                  Analytics
                </TabsTrigger>
                <TabsTrigger value="data" className="gap-2 text-xs sm:text-sm">
                  <Clock className="h-3.5 w-3.5" />
                  Data
                </TabsTrigger>
              </TabsList>

              {/* Overview Tab */}
              <TabsContent value="overview" className="space-y-3 sm:space-y-6">
                {/* Main GLCI Chart */}
                {isLoading ? (
                  <Card className="flex h-[400px] items-center justify-center">
                    <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                  </Card>
                ) : (
                  <LiquidityChart
                    title="GLCI Time Series"
                    description="Global Liquidity & Credit Index (normalized to mean 100, stdev 10)"
                    data={glciData?.data || []}
                    color="var(--primary)"
                    height={400}
                    valueFormatter={(v) => v.toFixed(1)}
                    referenceLine={100}
                    referenceLabel="Mean"
                    info={glciDefinitions.glci_index}
                  />
                )}

                {/* Statistics Row */}
                <div className="grid grid-cols-1 gap-2 min-[360px]:grid-cols-2 sm:gap-4 md:grid-cols-4">
                  <MetricCard
                    title="Current Value"
                    value={isLoading ? "Loading..." : glciData?.value.toFixed(1) ?? "—"}
                    change={calcChange(glciData?.data)}
                    trend={calcChange(glciData?.data) >= 0 ? "up" : "down"}
                    icon={<Gauge className="h-5 w-5" />}
                    variant="highlight"
                    info={glciDefinitions.glci_index}
                  />
                  <MetricCard
                    title="Period High"
                    value={isLoading || !glciData?.data ? "—" : Math.max(...glciData.data.map(d => d.value)).toFixed(1)}
                    icon={<TrendingUp className="h-5 w-5" />}
                  />
                  <MetricCard
                    title="Period Low"
                    value={isLoading || !glciData?.data ? "—" : Math.min(...glciData.data.map(d => d.value)).toFixed(1)}
                    icon={<TrendingDown className="h-5 w-5" />}
                  />
                  <MetricCard
                    title="Z-Score"
                    value={isLoading ? "Loading..." : glciData?.zscore?.toFixed(2) ?? "—"}
                    trend="neutral"
                    icon={<Activity className="h-5 w-5" />}
                    info={glciDefinitions.glci_zscore}
                  />
                </div>

                {/* Interpretation Guide */}
                <Card>
                  <CardHeader>
                    <CardTitle className="text-sm font-semibold">Index Interpretation</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="grid gap-2 sm:gap-3 md:grid-cols-3">
                      <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-4">
                        <div className="flex items-center gap-2 mb-2">
                          <TrendingUp className="h-4 w-4 text-emerald-500" />
                          <span className="font-semibold text-emerald-500">Above 110</span>
                        </div>
                        <p className="text-sm text-muted-foreground">
                          Loose conditions. Ample liquidity, expanding credit, low stress. Historically favorable for risk assets.
                        </p>
                      </div>
                      
                      <div className="rounded-lg border border-regime-neutral/20 bg-regime-neutral/5 p-4">
                        <div className="flex items-center gap-2 mb-2">
                          <Activity className="h-4 w-4 text-regime-neutral" />
                          <span className="font-semibold text-regime-neutral">90 - 110</span>
                        </div>
                        <p className="text-sm text-muted-foreground">
                          Neutral conditions. Balanced liquidity environment with normal credit growth.
                        </p>
                      </div>
                      
                      <div className="rounded-lg border border-regime-tight/20 bg-regime-tight/5 p-4">
                        <div className="flex items-center gap-2 mb-2">
                          <TrendingDown className="h-4 w-4 text-regime-tight" />
                          <span className="font-semibold text-regime-tight">Below 90</span>
                        </div>
                        <p className="text-sm text-muted-foreground">
                          Tight conditions. Contracting liquidity, credit stress. Associated with market corrections.
                        </p>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </TabsContent>

              {/* Pillars Tab */}
              <TabsContent value="pillars" className="space-y-3 sm:space-y-6">
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
                        title="Pillar Factors"
                        description="Individual pillar contributions over time (standardized)"
                        data={pillarChartData}
                        series={[
                          { key: "liquidity", label: "Liquidity", color: "var(--pillar-liquidity)" },
                          { key: "credit", label: "Credit", color: "var(--pillar-credit)" },
                          { key: "stress", label: "Stress (inverted)", color: "var(--pillar-stress)" },
                        ]}
                        height={350}
                        info={{
                          title: "GLCI Pillar Factors",
                          description: "Time series of individual pillar contributions to the composite index",
                          sections: [
                            { label: "Liquidity", content: "Central bank balance sheets, reserve balances, money supply (40% weight)" },
                            { label: "Credit", content: "Bank credit, consumer credit, BIS credit data (35% weight)" },
                            { label: "Stress", content: "Credit spreads, funding rates, VIX — inverted so lower is worse (25% weight)" },
                          ],
                          interpretation: "When pillars diverge, identify which factor is driving GLCI movement.",
                        }}
                      />
                      
                      <WaterfallChart
                        title="Weekly Change Breakdown"
                        description="Contribution of each pillar to weekly change"
                        previousValue={previousValue}
                        currentValue={glciData?.value ?? 100}
                        contributions={glciData?.pillars?.map(p => ({
                          name: p.name,
                          value: p.contribution,
                        })) || []}
                        height={350}
                        info={glciDefinitions.waterfall_breakdown}
                      />
                    </>
                  )}
                </div>

                {/* Individual pillar cards */}
                <div className="grid gap-2 sm:gap-4 md:grid-cols-3">
                  {glciData?.pillars?.map((pillar) => {
                    const config = pillarConfig[pillar.name as keyof typeof pillarConfig];
                    const Icon = config?.icon || Activity;
                    
                    return (
                      <Card key={pillar.name} className={`pillar-${pillar.name}`}>
                        <CardHeader className="pb-2">
                          <div className="flex items-center gap-2">
                            <div 
                              className="flex h-8 w-8 items-center justify-center rounded-lg pillar-bg"
                              style={{ backgroundColor: `color-mix(in srgb, ${config?.color || 'gray'} 20%, transparent)` }}
                            >
                              <Icon className="h-4 w-4" style={{ color: config?.color }} />
                            </div>
                            <CardTitle className="inline-flex items-center gap-1.5 text-sm">
                              {config?.label || pillar.name}
                              {config?.info && <InfoTooltip {...config.info} size="xs" />}
                            </CardTitle>
                          </div>
                        </CardHeader>
                        <CardContent className="space-y-2">
                          <div className="flex items-baseline justify-between">
                            <span className="font-mono text-2xl font-bold">
                              {pillar.value >= 0 ? "+" : ""}{pillar.value.toFixed(2)}
                            </span>
                            <Badge variant="outline" className="text-xs">
                              {(pillar.weight * 100).toFixed(0)}% weight
                            </Badge>
                          </div>
                          <p className="text-xs text-muted-foreground">
                            {config?.description}
                          </p>
                          <Progress 
                            value={Math.min(Math.max((pillar.value + 3) / 6 * 100, 0), 100)} 
                            className="h-1.5"
                          />
                        </CardContent>
                      </Card>
                    );
                  })}
                </div>
              </TabsContent>

              {/* Analytics Tab */}
              <TabsContent value="analytics" className="space-y-3 sm:space-y-6">
                <div className="grid gap-3 sm:gap-6 lg:grid-cols-2">
                  {/* Predictive Panel */}
                  {!isLoading && glciData && (
                    <PredictivePanel
                      currentValue={glciData.value}
                      zscore={glciData.zscore}
                      momentum={glciData.momentum}
                      regime={glciData.regime}
                      probRegimeChange={glciData.prob_regime_change}
                      historicalData={glciData.data}
                    />
                  )}

                  {/* Regime Timeline */}
                  {regimeHistory && (
                    <RegimeTimeline
                      periods={regimeHistory.periods}
                      currentRegime={regimeHistory.current}
                    />
                  )}
                </div>
              </TabsContent>

              {/* Data Tab */}
              <TabsContent value="data" className="space-y-3 sm:space-y-6">
                <div className="grid gap-3 sm:gap-6 lg:grid-cols-2">
                  {/* Data Freshness */}
                  {freshnessData.length > 0 && (
                    <DataFreshness items={freshnessData} />
                  )}

                  {/* Methodology */}
                  <Card>
                    <CardHeader>
                      <CardTitle className="text-sm font-semibold">Methodology</CardTitle>
                      <CardDescription className="text-xs">How the GLCI is computed</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4 text-sm text-muted-foreground">
                      <div>
                        <h4 className="font-semibold text-foreground mb-1">Factor Extraction</h4>
                        <p>Each pillar uses PCA with shrinkage regularization to extract a single latent factor from its component series.</p>
                      </div>
                      <div>
                        <h4 className="font-semibold text-foreground mb-1">Sign Normalization</h4>
                        <p>Components with inverse relationships (e.g., RRP drains liquidity) are pre-flipped before extraction.</p>
                      </div>
                      <div>
                        <h4 className="font-semibold text-foreground mb-1">Aggregation</h4>
                        <p>Pillar factors are weighted (40% liquidity, 35% credit, 25% stress) and normalized to mean 100, stdev 10.</p>
                      </div>
                      <div>
                        <h4 className="font-semibold text-foreground mb-1">Regime Classification</h4>
                        <p>Z-score thresholds: Tight (&lt;-1), Neutral (-1 to +1), Loose (&gt;+1).</p>
                      </div>
                    </CardContent>
                  </Card>
                </div>
              </TabsContent>
            </Tabs>
          </div>
        </div>
      </ScrollArea>
    </div>
  );
}

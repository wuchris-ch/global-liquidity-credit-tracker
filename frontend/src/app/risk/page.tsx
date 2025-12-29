"use client";

import { useState, useMemo } from "react";
import { Header } from "@/components/header";
import { MetricCard } from "@/components/metric-card";
import { MultiLineChart } from "@/components/multi-line-chart";
import { InfoTooltip } from "@/components/info-tooltip";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Activity,
  AlertCircle,
  BarChart3,
  Loader2,
  TrendingDown,
  TrendingUp,
  Gauge,
  LineChart,
  Percent,
} from "lucide-react";
import { useRiskData } from "@/hooks/use-risk-data";
import { AssetRiskMetrics } from "@/lib/api";

const regimeColors = {
  tight: "text-regime-tight bg-regime-tight/10 border-regime-tight/30",
  neutral: "text-regime-neutral bg-regime-neutral/10 border-regime-neutral/30",
  loose: "text-emerald-500 bg-emerald-500/10 border-emerald-500/30",
};

const regimeLabels = {
  tight: "Tight",
  neutral: "Neutral",
  loose: "Loose",
};

function SharpeCell({ value }: { value: number | null }) {
  if (value === null) return <span className="text-muted-foreground">N/A</span>;
  const color =
    value > 1
      ? "text-positive"
      : value > 0
        ? "text-foreground"
        : "text-negative";
  return (
    <span className={`font-mono font-semibold ${color}`}>{value.toFixed(2)}</span>
  );
}

function RegimeHeatmap({
  data,
}: {
  data: {
    assets: string[];
    regimes: string[];
    sharpe_data: (number | null)[][];
  };
}) {
  const getColor = (value: number | null) => {
    if (value === null) return "bg-muted";
    if (value > 1.5) return "bg-emerald-500/70 text-white";
    if (value > 1.0) return "bg-emerald-500/50";
    if (value > 0.5) return "bg-emerald-500/30";
    if (value > 0) return "bg-yellow-500/30";
    if (value > -0.5) return "bg-orange-500/30";
    return "bg-red-500/50";
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-semibold flex items-center gap-2">
          Sharpe Ratio by Regime
          <InfoTooltip
            title="Regime-Conditional Sharpe"
            description="Shows risk-adjusted returns for each asset during different GLCI regimes."
            sections={[
              {
                label: "Loose Regime",
                content: "GLCI z-score > +1. Abundant liquidity, risk-on.",
              },
              {
                label: "Neutral Regime",
                content: "GLCI z-score between -1 and +1. Balanced conditions.",
              },
              {
                label: "Tight Regime",
                content:
                  "GLCI z-score < -1. Restrictive liquidity, risk-off.",
              },
            ]}
            interpretation="Higher Sharpe ratios indicate better risk-adjusted performance. Values above 1.0 are generally considered good."
            size="sm"
          />
        </CardTitle>
        <CardDescription className="text-xs">
          Which assets perform best in each liquidity regime?
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr>
                <th className="text-left text-xs font-medium text-muted-foreground p-2">
                  Asset
                </th>
                {data.regimes.map((regime) => (
                  <th
                    key={regime}
                    className="text-center text-xs font-medium text-muted-foreground p-2 capitalize"
                  >
                    {regimeLabels[regime as keyof typeof regimeLabels] || regime}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.assets.map((asset, i) => (
                <tr key={asset} className="border-t border-border/50">
                  <td className="text-sm font-medium p-2">{asset}</td>
                  {data.sharpe_data[i].map((value, j) => (
                    <td
                      key={j}
                      className={`text-center p-2 ${getColor(value)}`}
                    >
                      <span className="font-mono text-sm">
                        {value !== null ? value.toFixed(2) : "N/A"}
                      </span>
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}

function AssetCards({ assets }: { assets: AssetRiskMetrics[] }) {
  return (
    <div className="grid grid-cols-1 gap-3 sm:gap-4 md:grid-cols-2 lg:grid-cols-4 xl:grid-cols-7">
      {assets.map((asset) => (
        <Card key={asset.id} className="relative overflow-hidden">
          <CardContent className="p-3 sm:p-4">
            <div className="flex flex-col gap-1">
              <p className="text-xs text-muted-foreground truncate">
                {asset.name}
              </p>
              <p className="text-[10px] text-muted-foreground/70">
                {asset.category}
              </p>
              <div className="flex items-baseline gap-2 mt-1">
                <span
                  className={`font-mono text-xl font-bold ${
                    asset.current_sharpe > 0 ? "text-positive" : "text-negative"
                  }`}
                >
                  {asset.current_sharpe.toFixed(2)}
                </span>
                <span className="text-[10px] text-muted-foreground">Sharpe</span>
              </div>
              <div className="flex items-center gap-2 mt-1 text-xs">
                <span
                  className={`font-mono ${
                    asset.annualized_return > 0
                      ? "text-positive"
                      : "text-negative"
                  }`}
                >
                  {asset.annualized_return > 0 ? "+" : ""}
                  {asset.annualized_return.toFixed(1)}%
                </span>
                <span className="text-muted-foreground">return</span>
              </div>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

export default function RiskPage() {
  const [activeTab, setActiveTab] = useState<string>("overview");
  const { data, isLoading, error, refetch } = useRiskData();

  // Find best/worst performers in current regime
  const regimeInsights = useMemo(() => {
    if (!data) return null;
    const regime = data.current_regime as "tight" | "neutral" | "loose";
    const sorted = [...data.assets]
      .filter((a) => a.sharpe_by_regime[regime] !== null)
      .sort(
        (a, b) =>
          (b.sharpe_by_regime[regime] || 0) - (a.sharpe_by_regime[regime] || 0)
      );

    return {
      best: sorted[0],
      worst: sorted[sorted.length - 1],
      regime,
    };
  }, [data]);

  // Prepare rolling sharpe chart data
  const rollingSharpeData = useMemo(() => {
    if (!data?.assets) return [];

    // Find the asset with the most rolling sharpe data points
    const assetWithMostData = data.assets.reduce((prev, curr) => {
      return (curr.rolling_sharpe?.length || 0) > (prev.rolling_sharpe?.length || 0)
        ? curr
        : prev;
    });

    if (!assetWithMostData.rolling_sharpe?.length) return [];

    // Build a map of dates to values for each asset
    const dateMap = new Map<string, Record<string, string | number>>();

    for (const asset of data.assets) {
      if (!asset.rolling_sharpe) continue;
      for (const point of asset.rolling_sharpe) {
        if (!dateMap.has(point.date)) {
          dateMap.set(point.date, { date: point.date });
        }
        const entry = dateMap.get(point.date)!;
        entry[asset.id] = point.value;
      }
    }

    // Convert to array and sort by date
    return Array.from(dateMap.values()).sort(
      (a, b) => new Date(a.date as string).getTime() - new Date(b.date as string).getTime()
    );
  }, [data]);

  if (error) {
    return (
      <div className="flex h-screen flex-col bg-background">
        <Header
          title="Risk by Regime"
          description="Risk-adjusted returns by GLCI regime"
        />
        <div className="flex flex-1 items-center justify-center">
          <Card className="max-w-md">
            <CardContent className="flex flex-col items-center gap-4 p-6">
              <AlertCircle className="h-12 w-12 text-destructive" />
              <h2 className="text-lg font-semibold">Failed to Load Risk Data</h2>
              <p className="text-center text-sm text-muted-foreground">
                Risk metrics data is not available. The risk computation pipeline
                needs to run first.
              </p>
              <code className="rounded bg-muted px-3 py-2 text-sm">
                python -c &quot;from src.indicators.risk_metrics import
                compute_risk_metrics; compute_risk_metrics(save=True)&quot;
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
        title="Risk by Regime"
        description="Sharpe ratios and risk metrics conditioned on GLCI regime"
        onRefresh={refetch}
        isRefreshing={isLoading}
      />

      <ScrollArea className="flex-1 w-full">
        <div className="bg-dots min-h-full w-full overflow-x-hidden">
          <div className="mx-auto w-full max-w-[1800px] space-y-3 p-2 min-[360px]:p-3 sm:space-y-6 sm:p-6">
            {/* Hero Section */}
            <div className="grid gap-3 sm:gap-6 lg:grid-cols-3">
              {/* Current Regime Card */}
              <Card className="border-primary/20 bg-gradient-to-br from-primary/5 via-card to-card">
                <CardContent className="p-4 sm:p-6">
                  <div className="flex items-center justify-between">
                    <div className="space-y-3">
                      <p className="text-xs font-medium text-muted-foreground">
                        Current GLCI Regime
                      </p>
                      <div className="flex items-center gap-2">
                        <Badge
                          className={`capitalize text-sm px-3 py-1 ${
                            regimeColors[
                              data?.current_regime as keyof typeof regimeColors
                            ] || regimeColors.neutral
                          }`}
                        >
                          {regimeLabels[
                            data?.current_regime as keyof typeof regimeLabels
                          ] || "Loading..."}
                        </Badge>
                      </div>
                      {regimeInsights && (
                        <div className="space-y-2 pt-2">
                          <div className="flex items-center gap-2">
                            <TrendingUp className="h-3 w-3 text-positive" />
                            <p className="text-xs text-muted-foreground">
                              Best:{" "}
                              <span className="font-semibold text-foreground">
                                {regimeInsights.best?.name}
                              </span>
                            </p>
                          </div>
                          <p className="text-xs text-muted-foreground pl-5">
                            Sharpe:{" "}
                            <span className="font-mono font-semibold text-positive">
                              {regimeInsights.best?.sharpe_by_regime[
                                regimeInsights.regime
                              ]?.toFixed(2)}
                            </span>
                          </p>
                        </div>
                      )}
                    </div>
                    <Gauge className="h-12 w-12 text-muted-foreground/20" />
                  </div>
                </CardContent>
              </Card>

              {/* Summary Stats */}
              <Card className="lg:col-span-2">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-semibold flex items-center gap-2">
                    Asset Overview
                    <InfoTooltip
                      title="Current Sharpe Ratios"
                      description="Real-time risk-adjusted performance for each tracked asset class."
                      interpretation="Sharpe ratio measures excess return per unit of risk. Higher is better."
                      size="sm"
                    />
                  </CardTitle>
                  <CardDescription className="text-xs">
                    Current Sharpe ratios across asset classes
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  {isLoading ? (
                    <div className="flex h-32 items-center justify-center">
                      <Loader2 className="h-6 w-6 animate-spin" />
                    </div>
                  ) : (
                    <AssetCards assets={data?.assets || []} />
                  )}
                </CardContent>
              </Card>
            </div>

            {/* Tabs */}
            <Tabs
              value={activeTab}
              onValueChange={setActiveTab}
              className="space-y-4"
            >
              <TabsList className="grid w-full grid-cols-3 md:max-w-lg">
                <TabsTrigger value="overview" className="gap-2 text-xs sm:text-sm">
                  <BarChart3 className="h-3.5 w-3.5" />
                  Overview
                </TabsTrigger>
                <TabsTrigger value="details" className="gap-2 text-xs sm:text-sm">
                  <Activity className="h-3.5 w-3.5" />
                  Details
                </TabsTrigger>
                <TabsTrigger
                  value="methodology"
                  className="gap-2 text-xs sm:text-sm"
                >
                  <Percent className="h-3.5 w-3.5" />
                  Methodology
                </TabsTrigger>
              </TabsList>

              {/* Overview Tab */}
              <TabsContent value="overview" className="space-y-6">
                {data?.regime_matrix && (
                  <RegimeHeatmap data={data.regime_matrix} />
                )}

                {/* Rolling Sharpe Chart */}
                {rollingSharpeData.length > 0 && (
                  <MultiLineChart
                    title="Rolling Sharpe Ratios (1 Year)"
                    description="Historical risk-adjusted performance over time"
                    data={rollingSharpeData}
                    series={
                      data?.assets.map((asset) => ({
                        key: asset.id,
                        label: asset.name,
                        color: `hsl(${(data.assets.indexOf(asset) * 360) / data.assets.length}, 70%, 50%)`,
                      })) || []
                    }
                    height={350}
                    info={{
                      title: "Rolling Sharpe Ratio",
                      description:
                        "252-day rolling Sharpe ratio showing how risk-adjusted performance evolves over time.",
                      interpretation:
                        "Values above 1.0 indicate strong risk-adjusted returns. Negative values indicate losses relative to risk-free rate.",
                    }}
                  />
                )}

                {/* Metric Cards Row */}
                <div className="grid grid-cols-1 gap-3 sm:gap-4 md:grid-cols-2 lg:grid-cols-4">
                  {data?.assets.slice(0, 4).map((asset) => (
                    <MetricCard
                      key={asset.id}
                      title={asset.name}
                      value={`${asset.annualized_return >= 0 ? "+" : ""}${asset.annualized_return.toFixed(1)}%`}
                      change={asset.annualized_volatility}
                      changeLabel="volatility"
                      trend={asset.annualized_return > 0 ? "up" : "down"}
                      icon={
                        asset.annualized_return > 0 ? (
                          <TrendingUp className="h-5 w-5" />
                        ) : (
                          <TrendingDown className="h-5 w-5" />
                        )
                      }
                    />
                  ))}
                </div>
              </TabsContent>

              {/* Details Table Tab */}
              <TabsContent value="details">
                <Card>
                  <CardHeader>
                    <CardTitle className="text-sm font-semibold">
                      Detailed Risk Metrics
                    </CardTitle>
                    <CardDescription className="text-xs">
                      Comprehensive breakdown of risk and return metrics by asset
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="overflow-x-auto">
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead>Asset</TableHead>
                            <TableHead>Category</TableHead>
                            <TableHead className="text-right">Sharpe</TableHead>
                            <TableHead className="text-right">Return</TableHead>
                            <TableHead className="text-right">Volatility</TableHead>
                            <TableHead className="text-right">Max DD</TableHead>
                            <TableHead className="text-right">GLCI Corr</TableHead>
                            <TableHead className="text-right">Tight</TableHead>
                            <TableHead className="text-right">Neutral</TableHead>
                            <TableHead className="text-right">Loose</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {data?.assets.map((asset) => (
                            <TableRow key={asset.id}>
                              <TableCell className="font-medium">
                                {asset.name}
                              </TableCell>
                              <TableCell className="text-muted-foreground text-xs">
                                {asset.category}
                              </TableCell>
                              <TableCell className="text-right">
                                <SharpeCell value={asset.current_sharpe} />
                              </TableCell>
                              <TableCell
                                className={`text-right font-mono ${
                                  asset.annualized_return > 0
                                    ? "text-positive"
                                    : "text-negative"
                                }`}
                              >
                                {asset.annualized_return >= 0 ? "+" : ""}
                                {asset.annualized_return.toFixed(1)}%
                              </TableCell>
                              <TableCell className="text-right font-mono">
                                {asset.annualized_volatility.toFixed(1)}%
                              </TableCell>
                              <TableCell className="text-right font-mono text-negative">
                                {asset.max_drawdown.toFixed(1)}%
                              </TableCell>
                              <TableCell className="text-right font-mono text-muted-foreground">
                                {asset.correlation_with_glci.toFixed(2)}
                              </TableCell>
                              <TableCell className="text-right">
                                <SharpeCell value={asset.sharpe_by_regime.tight} />
                              </TableCell>
                              <TableCell className="text-right">
                                <SharpeCell value={asset.sharpe_by_regime.neutral} />
                              </TableCell>
                              <TableCell className="text-right">
                                <SharpeCell value={asset.sharpe_by_regime.loose} />
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </div>
                  </CardContent>
                </Card>
              </TabsContent>

              {/* Methodology Tab */}
              <TabsContent value="methodology">
                <div className="grid gap-6 lg:grid-cols-2">
                  <Card>
                    <CardHeader>
                      <CardTitle className="text-sm font-semibold">
                        Calculation Methodology
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-4 text-sm text-muted-foreground">
                      <div>
                        <h4 className="font-semibold text-foreground mb-1">
                          Sharpe Ratio
                        </h4>
                        <p>
                          Sharpe = (Annualized Return - Risk Free Rate) /
                          Annualized Volatility
                        </p>
                        <p className="mt-1 text-xs">
                          Risk-free rate: 3-month US Treasury (DGS3MO)
                        </p>
                      </div>
                      <div>
                        <h4 className="font-semibold text-foreground mb-1">
                          Rolling Window
                        </h4>
                        <p>
                          252 trading days (approximately 1 year) for all rolling
                          calculations.
                        </p>
                      </div>
                      <div>
                        <h4 className="font-semibold text-foreground mb-1">
                          Annualization
                        </h4>
                        <p>
                          Returns and volatility are annualized using 252 trading
                          days per year.
                        </p>
                      </div>
                      <div>
                        <h4 className="font-semibold text-foreground mb-1">
                          Maximum Drawdown
                        </h4>
                        <p>
                          Largest peak-to-trough decline in the asset price over
                          the analyzed period.
                        </p>
                      </div>
                    </CardContent>
                  </Card>

                  <Card>
                    <CardHeader>
                      <CardTitle className="text-sm font-semibold">
                        Regime Classification
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-4 text-sm text-muted-foreground">
                      <div>
                        <h4 className="font-semibold text-foreground mb-1">
                          GLCI Regimes
                        </h4>
                        <p>
                          Returns are segmented by the GLCI z-score at the time
                          of each observation:
                        </p>
                      </div>
                      <div className="space-y-2">
                        <div className="flex items-center gap-2">
                          <Badge className={regimeColors.loose}>Loose</Badge>
                          <span>z-score &gt; +1.0</span>
                        </div>
                        <div className="flex items-center gap-2">
                          <Badge className={regimeColors.neutral}>Neutral</Badge>
                          <span>-1.0 &le; z-score &le; +1.0</span>
                        </div>
                        <div className="flex items-center gap-2">
                          <Badge className={regimeColors.tight}>Tight</Badge>
                          <span>z-score &lt; -1.0</span>
                        </div>
                      </div>
                      <div>
                        <h4 className="font-semibold text-foreground mb-1">
                          Data Sources
                        </h4>
                        <ul className="list-disc list-inside space-y-1 text-xs">
                          <li>S&P 500, Gold: FRED (Federal Reserve)</li>
                          <li>Russell 2000 (IWM), TLT: Yahoo Finance</li>
                          <li>Silver (SLV): Yahoo Finance</li>
                          <li>Bitcoin (BTC-USD), Ethereum (ETH-USD): Yahoo Finance</li>
                        </ul>
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

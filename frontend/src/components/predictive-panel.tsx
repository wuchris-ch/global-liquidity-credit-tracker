"use client";

import { useMemo } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { InfoTooltip } from "@/components/info-tooltip";
import { predictiveDefinitions } from "@/lib/indicator-definitions";
import { 
  TrendingUp, 
  TrendingDown, 
  Minus,
  ArrowRight,
  AlertTriangle,
  Target,
  Gauge
} from "lucide-react";
import { cn } from "@/lib/utils";
import { DataPoint } from "@/lib/api";

interface PredictivePanelProps {
  currentValue: number;
  zscore: number;
  momentum: number;
  regime: string;
  probRegimeChange: number;
  historicalData?: DataPoint[];
  className?: string;
}

const regimeThresholds = {
  tight: -1.0,
  loose: 1.0,
};

export function PredictivePanel({
  currentValue,
  zscore,
  momentum,
  regime,
  probRegimeChange,
  historicalData = [],
  className,
}: PredictivePanelProps) {
  // Calculate distance to regime boundaries
  const distToTight = zscore - regimeThresholds.tight;
  const distToLoose = regimeThresholds.loose - zscore;
  
  // Determine nearest boundary
  const nearestBoundary = distToTight < distToLoose ? "tight" : "loose";
  const distToNearest = Math.min(Math.abs(distToTight), Math.abs(distToLoose));

  // Calculate momentum trend
  const momentumTrend = useMemo(() => {
    if (historicalData.length < 4) return { direction: "neutral", strength: 0 };
    
    const recent = historicalData.slice(-4);
    const changes = recent.slice(1).map((d, i) => d.value - recent[i].value);
    const avgChange = changes.reduce((a, b) => a + b, 0) / changes.length;
    
    if (avgChange > 0.5) return { direction: "up", strength: Math.min(avgChange / 2, 1) };
    if (avgChange < -0.5) return { direction: "down", strength: Math.min(Math.abs(avgChange) / 2, 1) };
    return { direction: "neutral", strength: 0 };
  }, [historicalData]);

  // Calculate projected value (simple linear extrapolation)
  const projectedValue = currentValue + (momentum * 4); // 4-week projection

  // Risk assessment
  const riskLevel = useMemo(() => {
    if (probRegimeChange > 0.5) return "high";
    if (probRegimeChange > 0.25) return "medium";
    return "low";
  }, [probRegimeChange]);

  const MomentumIcon = momentum > 0 ? TrendingUp : momentum < 0 ? TrendingDown : Minus;
  const momentumColor = momentum > 0 ? "text-emerald-500" : momentum < 0 ? "text-red-500" : "text-muted-foreground";

  return (
    <Card className={cn("overflow-hidden", className)}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Target className="h-4 w-4 text-primary" />
            <div>
              <CardTitle className="text-base font-semibold">Outlook</CardTitle>
              <CardDescription className="text-xs">
                Short-term regime analysis
              </CardDescription>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Badge
              variant="outline"
              className={cn(
                riskLevel === "high" && "text-red-500 border-red-500/30",
                riskLevel === "medium" && "text-amber-500 border-amber-500/30",
                riskLevel === "low" && "text-emerald-500 border-emerald-500/30"
              )}
            >
              {riskLevel} volatility
            </Badge>
            <InfoTooltip {...predictiveDefinitions.volatility_assessment} size="sm" />
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Momentum indicator */}
        <div className="flex items-center justify-between rounded-lg border p-3">
          <div className="flex items-center gap-3">
            <div className={cn(
              "flex h-10 w-10 items-center justify-center rounded-xl",
              "bg-gradient-to-br from-muted to-muted/50"
            )}>
              <MomentumIcon className={cn("h-5 w-5", momentumColor)} />
            </div>
            <div>
              <p className="inline-flex items-center gap-1.5 text-sm font-medium">
                Momentum
                <InfoTooltip {...predictiveDefinitions.momentum_indicator} size="xs" />
              </p>
              <p className="text-xs text-muted-foreground">Weekly rate of change</p>
            </div>
          </div>
          <div className="text-right">
            <p className={cn("font-mono text-lg font-bold", momentumColor)}>
              {momentum >= 0 ? "+" : ""}{momentum.toFixed(2)}
            </p>
            <p className="text-[10px] text-muted-foreground">pts/week</p>
          </div>
        </div>

        {/* Regime change probability */}
        <div className="space-y-2">
          <div className="flex items-center justify-between text-sm">
            <div className="flex items-center gap-2">
              <AlertTriangle className={cn(
                "h-4 w-4",
                probRegimeChange > 0.5 ? "text-red-500" :
                probRegimeChange > 0.25 ? "text-amber-500" :
                "text-muted-foreground"
              )} />
              <span>Regime Change Probability</span>
            </div>
            <span className="font-mono font-semibold">
              {(probRegimeChange * 100).toFixed(0)}%
            </span>
          </div>
          <Progress 
            value={probRegimeChange * 100} 
            className="h-2"
          />
        </div>

        {/* Distance to boundaries */}
        <div className="grid grid-cols-2 gap-3">
          <Tooltip>
            <TooltipTrigger asChild>
              <div className={cn(
                "rounded-lg border p-3 text-center cursor-help",
                nearestBoundary === "tight" && distToNearest < 0.5 && "border-red-500/50 bg-red-500/5"
              )}>
                <p className="text-lg font-bold text-red-500">
                  {Math.abs(distToTight).toFixed(2)}
                </p>
                <p className="text-[10px] text-muted-foreground">
                  to Tight
                </p>
              </div>
            </TooltipTrigger>
            <TooltipContent>
              Distance to tight regime boundary (z-score = -1.0)
            </TooltipContent>
          </Tooltip>
          
          <Tooltip>
            <TooltipTrigger asChild>
              <div className={cn(
                "rounded-lg border p-3 text-center cursor-help",
                nearestBoundary === "loose" && distToNearest < 0.5 && "border-emerald-500/50 bg-emerald-500/5"
              )}>
                <p className="text-lg font-bold text-emerald-500">
                  {Math.abs(distToLoose).toFixed(2)}
                </p>
                <p className="text-[10px] text-muted-foreground">
                  to Loose
                </p>
              </div>
            </TooltipTrigger>
            <TooltipContent>
              Distance to loose regime boundary (z-score = +1.0)
            </TooltipContent>
          </Tooltip>
        </div>

        {/* 4-week projection */}
        <div className="rounded-lg border border-dashed p-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Gauge className="h-4 w-4 text-muted-foreground" />
              <span className="inline-flex items-center gap-1.5 text-sm">
                4-Week Projection
                <InfoTooltip {...predictiveDefinitions.projection_4w} size="xs" />
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="font-mono text-sm text-muted-foreground">
                {currentValue.toFixed(1)}
              </span>
              <ArrowRight className="h-3 w-3 text-muted-foreground" />
              <span className={cn(
                "font-mono text-sm font-semibold",
                projectedValue > currentValue ? "text-emerald-500" : "text-red-500"
              )}>
                {projectedValue.toFixed(1)}
              </span>
            </div>
          </div>
          <p className="mt-1 text-[10px] text-muted-foreground">
            Based on current momentum. Not a forecast.
          </p>
        </div>

        {/* Key insight */}
        <div className={cn(
          "rounded-lg p-3 text-sm",
          regime === "loose" && "bg-emerald-500/10 border border-emerald-500/20",
          regime === "neutral" && "bg-amber-500/10 border border-amber-500/20",
          regime === "tight" && "bg-red-500/10 border border-red-500/20"
        )}>
          <p className="font-medium">
            {regime === "loose" && momentum > 0 && "Conditions remain supportive with positive momentum."}
            {regime === "loose" && momentum < 0 && "Watch for potential regime weakening as momentum turns negative."}
            {regime === "loose" && momentum === 0 && "Loose conditions holding steady."}
            {regime === "neutral" && momentum > 0 && "Improving conditions; possible transition to loose regime."}
            {regime === "neutral" && momentum < 0 && "Deteriorating conditions; monitor for stress signals."}
            {regime === "neutral" && momentum === 0 && "Balanced conditions with no clear directional bias."}
            {regime === "tight" && momentum > 0 && "Early signs of improvement in tight conditions."}
            {regime === "tight" && momentum < 0 && "Stress conditions intensifying; risk-off positioning warranted."}
            {regime === "tight" && momentum === 0 && "Tight conditions persisting; await catalyst for change."}
          </p>
        </div>
      </CardContent>
    </Card>
  );
}


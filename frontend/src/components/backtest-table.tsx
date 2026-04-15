"use client";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";
import type {
  BacktestAssetResult,
  BacktestHorizon,
  BacktestStats,
  Regime,
} from "@/lib/api";

interface BacktestTableProps {
  title: string;
  description?: string;
  classifier: string;
  assets: BacktestAssetResult[];
  horizons: number[];
}

const REGIMES: Regime[] = ["tight", "neutral", "loose"];

function formatPct(value: number | null, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

function formatSigned(value: number | null, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const pct = value * 100;
  return `${pct >= 0 ? "+" : ""}${pct.toFixed(digits)}%`;
}

function edgeColor(edge: number | null): string {
  if (edge === null || Number.isNaN(edge)) return "text-muted-foreground";
  if (edge > 0.1) return "text-emerald-500 font-semibold";
  if (edge > 0.03) return "text-emerald-400";
  if (edge < -0.1) return "text-red-500 font-semibold";
  if (edge < -0.03) return "text-red-400";
  return "text-muted-foreground";
}

function medianBackground(median: number | null): string {
  if (median === null || Number.isNaN(median)) return "";
  if (median > 0.05) return "bg-emerald-500/10";
  if (median > 0) return "bg-emerald-500/5";
  if (median < -0.05) return "bg-red-500/10";
  if (median < 0) return "bg-red-500/5";
  return "";
}

function StatCell({ stats }: { stats: BacktestStats | undefined }) {
  if (!stats || stats.n < 20 || stats.median === null) {
    return (
      <TableCell className="text-center text-muted-foreground">
        <span className="text-xs">n={stats?.n ?? 0}</span>
      </TableCell>
    );
  }

  const bg = medianBackground(stats.median);
  const edgeCls = edgeColor(stats.edge);

  return (
    <TableCell className={cn("text-center align-middle", bg)}>
      <Tooltip>
        <TooltipTrigger asChild>
          <div className="flex cursor-help flex-col items-center gap-0.5">
            <span className="font-mono text-sm font-semibold">
              {formatSigned(stats.median)}
            </span>
            <span className={cn("font-mono text-[10px]", edgeCls)}>
              hit {formatPct(stats.hit_rate, 0)}{" "}
              {stats.edge !== null && (
                <span>
                  ({stats.edge >= 0 ? "+" : ""}
                  {(stats.edge * 100).toFixed(1)}pp)
                </span>
              )}
            </span>
          </div>
        </TooltipTrigger>
        <TooltipContent side="top" className="max-w-xs space-y-1 text-xs">
          <div>
            <span className="font-semibold">Median:</span>{" "}
            {formatSigned(stats.median, 2)}
          </div>
          <div className="text-muted-foreground">
            IQR: {formatSigned(stats.p25, 2)} to {formatSigned(stats.p75, 2)}
          </div>
          <div>
            <span className="font-semibold">Hit rate:</span>{" "}
            {formatPct(stats.hit_rate, 0)}{" "}
            {stats.edge !== null && (
              <span className={edgeCls}>
                ({stats.edge >= 0 ? "+" : ""}
                {(stats.edge * 100).toFixed(1)}pp vs base)
              </span>
            )}
          </div>
          {stats.ci_median_low !== null && stats.ci_median_high !== null && (
            <div className="text-muted-foreground">
              Median 95% CI: {formatSigned(stats.ci_median_low, 2)} to{" "}
              {formatSigned(stats.ci_median_high, 2)}
            </div>
          )}
          {stats.ci_hit_rate_low !== null && stats.ci_hit_rate_high !== null && (
            <div className="text-muted-foreground">
              Hit rate 95% CI: {formatPct(stats.ci_hit_rate_low, 0)} to{" "}
              {formatPct(stats.ci_hit_rate_high, 0)}
            </div>
          )}
          <div className="text-muted-foreground">n = {stats.n}</div>
        </TooltipContent>
      </Tooltip>
    </TableCell>
  );
}

export function BacktestTable({
  title,
  description,
  classifier,
  assets,
  horizons,
}: BacktestTableProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-semibold capitalize">
          {title}
        </CardTitle>
        {description && (
          <CardDescription className="text-xs">{description}</CardDescription>
        )}
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-[140px]">Asset</TableHead>
                <TableHead className="text-right">Base (13w hit)</TableHead>
                {REGIMES.flatMap((regime) =>
                  horizons.map((h) => (
                    <TableHead
                      key={`${regime}-${h}`}
                      className="text-center capitalize"
                    >
                      <div className="flex flex-col items-center">
                        <span>{regime}</span>
                        <span className="text-[10px] font-normal text-muted-foreground">
                          {h}w
                        </span>
                      </div>
                    </TableHead>
                  )),
                )}
              </TableRow>
            </TableHeader>
            <TableBody>
              {assets.map((asset) => {
                const byRegime = asset.results[classifier];
                const baseHr = asset.base_rates["13"]?.hit_rate;
                return (
                  <TableRow key={asset.id}>
                    <TableCell className="font-medium">{asset.name}</TableCell>
                    <TableCell className="text-right font-mono text-xs text-muted-foreground">
                      {formatPct(baseHr ?? null, 0)}
                    </TableCell>
                    {REGIMES.flatMap((regime) =>
                      horizons.map((h) => {
                        const stats =
                          byRegime?.[regime]?.[String(h) as BacktestHorizon];
                        return (
                          <StatCell
                            key={`${asset.id}-${regime}-${h}`}
                            stats={stats}
                          />
                        );
                      }),
                    )}
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
        <p className="mt-3 text-[11px] text-muted-foreground">
          Cell: median forward return · hit rate (edge vs unconditional base
          rate, pp). Empty cells have n &lt; 20. Hover for IQR and 95% CIs
          (block bootstrap).
        </p>
      </CardContent>
    </Card>
  );
}

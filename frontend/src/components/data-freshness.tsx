"use client";

import { useState, useMemo } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { 
  CheckCircle2, 
  AlertCircle, 
  Clock, 
  Database,
  Waves,
  CreditCard,
  AlertTriangle 
} from "lucide-react";
import { cn } from "@/lib/utils";
import { DataFreshnessItem } from "@/lib/api";

interface DataFreshnessProps {
  items: DataFreshnessItem[];
  className?: string;
}

const pillarConfig = {
  liquidity: {
    icon: Waves,
    color: "var(--foreground)",
    label: "Liquidity",
  },
  credit: {
    icon: CreditCard,
    color: "var(--muted-foreground)",
    label: "Credit",
  },
  stress: {
    icon: AlertTriangle,
    color: "var(--pillar-stress)",
    label: "Stress",
  },
};

function getFreshnessStatus(daysOld: number): {
  status: "fresh" | "stale" | "old";
  icon: typeof CheckCircle2;
  color: string;
  label: string;
} {
  if (daysOld < 0) {
    return {
      status: "old",
      icon: AlertCircle,
      color: "text-red-500",
      label: "Unknown",
    };
  }
  if (daysOld <= 7) {
    return {
      status: "fresh",
      icon: CheckCircle2,
      color: "text-emerald-500",
      label: "Fresh",
    };
  }
  if (daysOld <= 30) {
    return {
      status: "stale",
      icon: Clock,
      color: "text-amber-500",
      label: "Stale",
    };
  }
  return {
    status: "old",
    icon: AlertCircle,
    color: "text-red-500",
    label: "Old",
  };
}

function formatSeriesId(id: string): string {
  return id
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

export function DataFreshness({ items, className }: DataFreshnessProps) {
  const [selectedPillar, setSelectedPillar] = useState<string>("all");

  const groupedByPillar = useMemo(() => {
    const groups: Record<string, DataFreshnessItem[]> = {};
    items.forEach((item) => {
      if (!groups[item.pillar]) {
        groups[item.pillar] = [];
      }
      groups[item.pillar].push(item);
    });
    return groups;
  }, [items]);

  const stats = useMemo(() => {
    let fresh = 0;
    let stale = 0;
    let old = 0;

    items.forEach((item) => {
      const status = getFreshnessStatus(item.days_old);
      if (status.status === "fresh") fresh++;
      else if (status.status === "stale") stale++;
      else old++;
    });

    return { fresh, stale, old, total: items.length };
  }, [items]);

  const filteredItems = useMemo(() => {
    if (selectedPillar === "all") return items;
    return items.filter((item) => item.pillar === selectedPillar);
  }, [items, selectedPillar]);

  const pillars = Object.keys(groupedByPillar);

  return (
    <Card className={cn("overflow-hidden", className)}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Database className="h-4 w-4 text-muted-foreground" />
            <div>
              <CardTitle className="text-base font-semibold">Data Freshness</CardTitle>
              <CardDescription className="text-xs">
                Last update status for {stats.total} data sources
              </CardDescription>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Tooltip>
              <TooltipTrigger>
                <Badge variant="outline" className="text-emerald-500 border-emerald-500/30">
                  {stats.fresh}
                </Badge>
              </TooltipTrigger>
              <TooltipContent>Fresh (&lt;7 days)</TooltipContent>
            </Tooltip>
            <Tooltip>
              <TooltipTrigger>
                <Badge variant="outline" className="text-amber-500 border-amber-500/30">
                  {stats.stale}
                </Badge>
              </TooltipTrigger>
              <TooltipContent>Stale (7-30 days)</TooltipContent>
            </Tooltip>
            <Tooltip>
              <TooltipTrigger>
                <Badge variant="outline" className="text-red-500 border-red-500/30">
                  {stats.old}
                </Badge>
              </TooltipTrigger>
              <TooltipContent>Old (&gt;30 days)</TooltipContent>
            </Tooltip>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* Pillar filter tabs */}
        <Tabs value={selectedPillar} onValueChange={setSelectedPillar}>
          <TabsList className="grid w-full grid-cols-4">
            <TabsTrigger value="all" className="text-xs">All</TabsTrigger>
            {pillars.map((pillar) => {
              const config = pillarConfig[pillar as keyof typeof pillarConfig];
              return (
                <TabsTrigger key={pillar} value={pillar} className="text-xs capitalize">
                  {config?.label || pillar}
                </TabsTrigger>
              );
            })}
          </TabsList>
        </Tabs>

        {/* Data list */}
        <ScrollArea className="h-[200px]">
          <div className="space-y-1.5 pr-3">
            {filteredItems.map((item) => {
              const status = getFreshnessStatus(item.days_old);
              const StatusIcon = status.icon;
              const pillar = pillarConfig[item.pillar as keyof typeof pillarConfig];

              return (
                <div
                  key={item.series_id}
                  className={cn(
                    "flex items-center justify-between rounded-md px-2 py-1.5 text-sm",
                    "hover:bg-muted/50 transition-colors"
                  )}
                >
                  <div className="flex items-center gap-2 truncate">
                    <Tooltip>
                      <TooltipTrigger>
                        <StatusIcon className={cn("h-3.5 w-3.5 shrink-0", status.color)} />
                      </TooltipTrigger>
                      <TooltipContent>{status.label}</TooltipContent>
                    </Tooltip>
                    <span className="truncate text-xs">
                      {formatSeriesId(item.series_id)}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    {pillar && (
                      <div
                        className="h-2 w-2 rounded-full"
                        style={{ backgroundColor: pillar.color }}
                      />
                    )}
                    <span className="text-[10px] text-muted-foreground tabular-nums">
                      {item.days_old >= 0 ? `${item.days_old}d` : "—"}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </ScrollArea>
      </CardContent>
    </Card>
  );
}

interface FreshnessSummaryProps {
  items: DataFreshnessItem[];
  compact?: boolean;
}

export function FreshnessSummary({ items, compact = false }: FreshnessSummaryProps) {
  const stats = useMemo(() => {
    let freshCount = 0;
    let avgAge = 0;
    let validCount = 0;

    items.forEach((item) => {
      if (item.days_old >= 0) {
        avgAge += item.days_old;
        validCount++;
        if (item.days_old <= 7) freshCount++;
      }
    });

    return {
      freshPct: items.length > 0 ? (freshCount / items.length) * 100 : 0,
      avgAge: validCount > 0 ? avgAge / validCount : -1,
    };
  }, [items]);

  if (compact) {
    return (
      <div className="flex items-center gap-2 text-xs">
        <Database className="h-3 w-3 text-muted-foreground" />
        <span className={cn(
          stats.freshPct >= 80 ? "text-emerald-500" :
          stats.freshPct >= 50 ? "text-amber-500" :
          "text-red-500"
        )}>
          {stats.freshPct.toFixed(0)}% fresh
        </span>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-4 text-sm">
      <div className="flex items-center gap-1.5">
        <Database className="h-4 w-4 text-muted-foreground" />
        <span className="text-muted-foreground">Data Status:</span>
      </div>
      <Badge
        variant="outline"
        className={cn(
          stats.freshPct >= 80
            ? "text-emerald-500 border-emerald-500/30"
            : stats.freshPct >= 50
            ? "text-amber-500 border-amber-500/30"
            : "text-red-500 border-red-500/30"
        )}
      >
        {stats.freshPct.toFixed(0)}% fresh
      </Badge>
      {stats.avgAge >= 0 && (
        <span className="text-xs text-muted-foreground">
          Avg age: {stats.avgAge.toFixed(0)} days
        </span>
      )}
    </div>
  );
}


"use client";

import { SidebarTrigger } from "@/components/ui/sidebar";
import { Separator } from "@/components/ui/separator";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { RefreshCw, Calendar } from "lucide-react";

export type TimeRange = "1m" | "3m" | "6m" | "1y" | "2y" | "5y" | "10y" | "15y" | "all";

interface HeaderProps {
  title: string;
  description?: string;
  showDateSelector?: boolean;
  onRefresh?: () => void;
  timeRange?: TimeRange;
  onTimeRangeChange?: (range: TimeRange) => void;
  isRefreshing?: boolean;
}

export function Header({
  title,
  description,
  showDateSelector = true,
  onRefresh,
  timeRange = "3m",
  onTimeRangeChange,
  isRefreshing = false,
}: HeaderProps) {
  return (
    <header className="sticky top-0 z-10 shrink-0 border-b border-border bg-background/95 backdrop-blur-xl">
      {/* Main row - always horizontal */}
      <div className="flex min-h-14 items-center gap-2 px-3 sm:min-h-16 sm:gap-4 sm:px-6">
        <SidebarTrigger className="-ml-1 sm:-ml-2" />
        <Separator orientation="vertical" className="hidden h-6 sm:flex" />
        
        {/* Title area - flexible */}
        <div className="flex flex-1 min-w-0 items-center gap-2">
          <div className="min-w-0 flex-1">
            <h1 className="text-sm font-semibold tracking-tight sm:text-lg truncate">{title}</h1>
            {description && (
              <p className="text-[10px] text-muted-foreground sm:text-xs truncate hidden xs:block">{description}</p>
            )}
          </div>
          
          <Badge
            variant="outline"
            className="shrink-0 border-positive/30 bg-positive/5 text-positive text-[10px] sm:text-xs h-5 sm:h-6 px-1.5 sm:px-2"
          >
            <span className="mr-1 h-1.5 w-1.5 rounded-full bg-positive pulse-live" />
            <span className="hidden sm:inline">Live</span>
            <span className="sm:hidden">●</span>
          </Badge>
        </div>

        {/* Controls - compact on mobile */}
        <div className="flex shrink-0 items-center gap-1.5 sm:gap-3">
          {showDateSelector && (
            <Select value={timeRange} onValueChange={(value) => onTimeRangeChange?.(value as TimeRange)}>
              <SelectTrigger className="h-8 w-[70px] text-[10px] sm:h-9 sm:w-[130px] sm:text-xs">
                <Calendar className="mr-1 h-3 w-3 sm:mr-2 sm:h-3.5 sm:w-3.5 text-muted-foreground shrink-0" />
                <SelectValue placeholder="Range" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="1m">1 Mo</SelectItem>
                <SelectItem value="3m">3 Mo</SelectItem>
                <SelectItem value="6m">6 Mo</SelectItem>
                <SelectItem value="1y">1 Yr</SelectItem>
                <SelectItem value="2y">2 Yr</SelectItem>
                <SelectItem value="5y">5 Yr</SelectItem>
                <SelectItem value="10y">10 Yr</SelectItem>
                <SelectItem value="15y">15 Yr</SelectItem>
                <SelectItem value="all">All</SelectItem>
              </SelectContent>
            </Select>
          )}
          
          <Button
            variant="outline"
            size="icon"
            className="h-8 w-8 sm:h-9 sm:w-auto sm:px-3 sm:gap-2"
            onClick={onRefresh}
            disabled={isRefreshing}
          >
            <RefreshCw className={`h-3.5 w-3.5 ${isRefreshing ? "animate-spin" : ""}`} />
            <span className="hidden sm:inline">{isRefreshing ? "..." : "Refresh"}</span>
          </Button>
        </div>
      </div>
    </header>
  );
}



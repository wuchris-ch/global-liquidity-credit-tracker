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
    <header className="sticky top-0 z-10 flex min-h-16 shrink-0 items-center gap-3 border-b border-border bg-background/80 px-4 sm:gap-4 sm:px-6 backdrop-blur-xl">
      <SidebarTrigger className="-ml-2" />
      <Separator orientation="vertical" className="hidden h-6 sm:flex" />
      
      <div className="flex flex-1 min-w-0 flex-wrap items-center gap-3 sm:gap-4">
        <div className="min-w-0">
          <h1 className="text-base font-semibold tracking-tight sm:text-lg line-clamp-1">{title}</h1>
          {description && (
            <p className="text-[11px] text-muted-foreground sm:text-xs line-clamp-2">{description}</p>
          )}
        </div>
        
        <Badge
          variant="outline"
          className="ml-0 border-positive/30 bg-positive/5 text-positive sm:ml-2"
        >
          <span className="mr-1.5 h-1.5 w-1.5 rounded-full bg-positive pulse-live" />
          <span className="hidden sm:inline">Live</span>
          <span className="sm:hidden">On</span>
        </Badge>
      </div>

      <div className="flex flex-1 flex-wrap items-center justify-end gap-2 sm:flex-none sm:gap-3">
        {showDateSelector && (
          <Select value={timeRange} onValueChange={(value) => onTimeRangeChange?.(value as TimeRange)}>
            <SelectTrigger className="h-9 w-full min-w-[0] text-xs sm:w-auto sm:min-w-[140px]">
              <Calendar className="mr-2 h-3.5 w-3.5 text-muted-foreground" />
              <SelectValue placeholder="Select range" />
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
              <SelectItem value="all">All Time</SelectItem>
            </SelectContent>
          </Select>
        )}
        
        <Button
          variant="outline"
          size="sm"
          className="h-9 w-full gap-2 sm:w-auto"
          onClick={onRefresh}
          disabled={isRefreshing}
        >
          <RefreshCw className={`h-3.5 w-3.5 ${isRefreshing ? "animate-spin" : ""}`} />
          <span className="sm:hidden">{isRefreshing ? "..." : "Refresh"}</span>
          <span className="hidden sm:inline">{isRefreshing ? "Refreshing..." : "Refresh"}</span>
        </Button>
      </div>
    </header>
  );
}



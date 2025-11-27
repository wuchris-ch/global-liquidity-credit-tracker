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
    <header className="sticky top-0 z-10 flex h-16 shrink-0 items-center gap-4 border-b border-border bg-background/80 px-6 backdrop-blur-xl">
      <SidebarTrigger className="-ml-2" />
      <Separator orientation="vertical" className="h-6" />
      
      <div className="flex flex-1 items-center gap-4">
        <div>
          <h1 className="text-lg font-semibold tracking-tight">{title}</h1>
          {description && (
            <p className="text-xs text-muted-foreground">{description}</p>
          )}
        </div>
        
        <Badge
          variant="outline"
          className="ml-2 border-positive/30 bg-positive/5 text-positive"
        >
          <span className="mr-1.5 h-1.5 w-1.5 rounded-full bg-positive pulse-live" />
          Live
        </Badge>
      </div>

      <div className="flex items-center gap-3">
        {showDateSelector && (
          <Select value={timeRange} onValueChange={(value) => onTimeRangeChange?.(value as TimeRange)}>
            <SelectTrigger className="w-auto min-w-[100px] h-9 text-xs">
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
          className="h-9 gap-2"
          onClick={onRefresh}
          disabled={isRefreshing}
        >
          <RefreshCw className={`h-3.5 w-3.5 ${isRefreshing ? "animate-spin" : ""}`} />
          <span className="hidden sm:inline">{isRefreshing ? "Refreshing..." : "Refresh"}</span>
        </Button>
      </div>
    </header>
  );
}



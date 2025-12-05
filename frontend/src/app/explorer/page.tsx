"use client";

import { useCallback, useMemo, useState } from "react";
import { Header, TimeRange } from "@/components/header";
import { MultiLineChart } from "@/components/multi-line-chart";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  AlertCircle,
  Check,
  Database,
  Download,
  Filter,
  Loader2,
  Search,
  X,
} from "lucide-react";
import { useSeriesList, useMultipleSeries } from "@/hooks/use-series-data";
import { useIsMobile } from "@/hooks/use-mobile";

const chartColors = [
  "var(--chart-1)",
  "var(--chart-2)",
  "var(--chart-3)",
  "var(--chart-4)",
  "var(--chart-5)",
];

function getDateRange(range: TimeRange): { start: string; end: string } {
  const end = new Date();
  const start = new Date();

  switch (range) {
    case "1m":
      start.setMonth(end.getMonth() - 1);
      break;
    case "3m":
      start.setMonth(end.getMonth() - 3);
      break;
    case "6m":
      start.setMonth(end.getMonth() - 6);
      break;
    case "1y":
      start.setFullYear(end.getFullYear() - 1);
      break;
    case "2y":
      start.setFullYear(end.getFullYear() - 2);
      break;
    case "5y":
      start.setFullYear(end.getFullYear() - 5);
      break;
    case "10y":
      start.setFullYear(end.getFullYear() - 10);
      break;
    case "15y":
      start.setFullYear(end.getFullYear() - 15);
      break;
    case "all":
      start.setFullYear(2000);
      break;
  }

  return {
    start: start.toISOString().split("T")[0],
    end: end.toISOString().split("T")[0],
  };
}

export default function ExplorerPage() {
  const [userSelectedSeries, setUserSelectedSeries] = useState<string[] | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [categoryFilter, setCategoryFilter] = useState<string>("all");
  const [normalize, setNormalize] = useState(true);
  const [timeRange, setTimeRange] = useState<TimeRange>("1y");
  const [seriesSheetOpen, setSeriesSheetOpen] = useState(false);

  const isMobile = useIsMobile();

  const dateRange = useMemo(() => getDateRange(timeRange), [timeRange]);

  const { series: availableSeries, isLoading: seriesLoading, error: seriesError } = useSeriesList();
  const defaultSelection = useMemo(
    () => (availableSeries.length > 0 ? availableSeries.slice(0, 2).map((s) => s.id) : []),
    [availableSeries]
  );
  const selectedSeries = userSelectedSeries ?? defaultSelection;
  const { data: seriesData, isLoading: dataLoading, refetch } = useMultipleSeries(
    selectedSeries,
    { ...dateRange, enabled: selectedSeries.length > 0 }
  );

  const handleRefresh = useCallback(async () => {
    await refetch();
  }, [refetch]);

  const handleTimeRangeChange = useCallback((range: TimeRange) => {
    setTimeRange(range);
  }, []);

  const categories = useMemo(() => {
    const cats = new Set(availableSeries.map((s) => s.category));
    return ["all", ...Array.from(cats)];
  }, [availableSeries]);

  const filteredSeries = useMemo(() => {
    return availableSeries.filter((s) => {
      const matchesSearch =
        s.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        s.id.toLowerCase().includes(searchQuery.toLowerCase());
      const matchesCategory = categoryFilter === "all" || s.category === categoryFilter;
      return matchesSearch && matchesCategory;
    });
  }, [availableSeries, searchQuery, categoryFilter]);

  const toggleSeries = (id: string) => {
    if (selectedSeries.includes(id)) {
      setUserSelectedSeries(selectedSeries.filter((s) => s !== id));
    } else if (selectedSeries.length < 5) {
      setUserSelectedSeries([...selectedSeries, id]);
    }
  };

  const chartData = useMemo(() => {
    if (selectedSeries.length === 0 || Object.keys(seriesData).length === 0) return [];

    let baseSeries = selectedSeries[0];
    let maxLength = 0;
    for (const id of selectedSeries) {
      const len = seriesData[id]?.length || 0;
      if (len > maxLength) {
        maxLength = len;
        baseSeries = id;
      }
    }

    const baseData = seriesData[baseSeries] || [];
    if (baseData.length === 0) return [];

    return baseData.map((d, i) => {
      const point: Record<string, string | number> = { date: d.date };

      selectedSeries.forEach((seriesId) => {
        const data = seriesData[seriesId] || [];
        const dataPoint = data.find((dp) => dp.date === d.date) || data[i];
        if (dataPoint) {
          if (normalize) {
            const firstValue = data[0]?.value || 1;
            point[seriesId] = (dataPoint.value / firstValue) * 100;
          } else {
            point[seriesId] = dataPoint.value;
          }
        }
      });

      return point;
    });
  }, [selectedSeries, seriesData, normalize]);

  const chartSeries = useMemo(() => {
    return selectedSeries.map((id, index) => {
      const series = availableSeries.find((s) => s.id === id);
      return {
        key: id,
        label: series?.name || id,
        color: chartColors[index % chartColors.length],
      };
    });
  }, [selectedSeries, availableSeries]);

  const renderSeriesPanel = (onClose?: () => void) => {
    return (
      <div className="flex h-full flex-col">
        <div className="border-b border-border p-4">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder="Search series..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9"
            />
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <Filter className="h-4 w-4 text-muted-foreground" />
            <Select value={categoryFilter} onValueChange={setCategoryFilter}>
              <SelectTrigger className="h-8 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {categories.map((cat) => (
                  <SelectItem key={cat} value={cat} className="text-xs">
                    {cat === "all" ? "All Categories" : cat}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        <ScrollArea className="flex-1">
          <div className="space-y-1 p-2">
            {seriesLoading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              </div>
            ) : (
              filteredSeries.map((series) => {
                const isSelected = selectedSeries.includes(series.id);
                const colorIndex = selectedSeries.indexOf(series.id);

                return (
                  <button
                    key={series.id}
                    onClick={() => {
                      toggleSeries(series.id);
                      onClose?.();
                    }}
                    className={`flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left transition-colors ${
                      isSelected ? "bg-primary/10 text-primary" : "hover:bg-muted/50"
                    }`}
                  >
                    <div
                      className={`flex h-5 w-5 shrink-0 items-center justify-center rounded border transition-colors ${
                        isSelected ? "border-primary bg-primary text-primary-foreground" : "border-border"
                      }`}
                    >
                      {isSelected && <Check className="h-3 w-3" />}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="truncate text-sm font-medium">{series.name}</span>
                        {isSelected && (
                          <div className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: chartColors[colorIndex] }} />
                        )}
                      </div>
                      <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
                        <span>{series.source}</span>
                        <span>•</span>
                        <span>{series.category}</span>
                      </div>
                    </div>
                  </button>
                );
              })
            )}
          </div>
        </ScrollArea>

        <div className="border-t border-border p-4">
          <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
            <span>{selectedSeries.length}/5 series selected</span>
            {selectedSeries.length > 0 && (
              <Button
                variant="ghost"
                size="sm"
                className="h-6 px-2 text-xs"
                onClick={() => {
                  setUserSelectedSeries([]);
                  onClose?.();
                }}
              >
                Clear all
              </Button>
            )}
          </div>
        </div>
      </div>
    );
  };

  if (seriesError) {
    return (
      <div className="flex h-screen flex-col bg-background">
        <Header
          title="Data Explorer"
          description="Compare and analyze multiple data series"
          timeRange={timeRange}
          onTimeRangeChange={handleTimeRangeChange}
          onRefresh={handleRefresh}
          isRefreshing={dataLoading}
        />
        <div className="flex flex-1 items-center justify-center">
          <Card className="max-w-md">
            <CardContent className="flex flex-col items-center gap-4 p-6">
              <AlertCircle className="h-12 w-12 text-destructive" />
              <h2 className="text-lg font-semibold">Failed to Load Series</h2>
              <p className="text-center text-sm text-muted-foreground">
                Could not connect to the data API. Make sure the Python backend is running:
              </p>
              <code className="rounded bg-muted px-3 py-2 text-sm">uvicorn src.api:app --reload</code>
            </CardContent>
          </Card>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-screen flex-col bg-background">
      <Header
        title="Data Explorer"
        description="Compare and analyze multiple data series"
        timeRange={timeRange}
        onTimeRangeChange={handleTimeRangeChange}
        onRefresh={handleRefresh}
        isRefreshing={dataLoading}
      />

      <div className="flex flex-1 flex-col overflow-hidden">
        {isMobile && (
          <div className="border-b border-border bg-card/60 px-4 py-3">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <Database className="h-5 w-5 text-muted-foreground" />
                <div>
                  <p className="text-sm font-semibold">Series Picker</p>
                  <p className="text-[11px] text-muted-foreground">{selectedSeries.length}/5 selected</p>
                </div>
              </div>
              <Sheet open={seriesSheetOpen} onOpenChange={setSeriesSheetOpen}>
                <SheetTrigger asChild>
                  <Button size="sm" variant="outline" className="gap-2">
                    <Search className="h-4 w-4" />
                    Browse
                  </Button>
                </SheetTrigger>
                <SheetContent side="left" className="w-[320px] p-0">
                  <SheetHeader className="sr-only">
                    <SheetTitle>Select data series</SheetTitle>
                  </SheetHeader>
                  {renderSeriesPanel(() => setSeriesSheetOpen(false))}
                </SheetContent>
              </Sheet>
            </div>
          </div>
        )}

        <div className="flex flex-1 flex-col overflow-hidden lg:flex-row">
          {!isMobile && (
            <div className="w-full max-w-[320px] shrink-0 border-b border-border bg-card/50 lg:w-80 lg:border-b-0 lg:border-r">
              {renderSeriesPanel()}
            </div>
          )}

          <div className="flex-1 overflow-hidden">
            <ScrollArea className="h-full w-full">
                <div className="bg-grid min-h-full p-2 min-[360px]:p-3 sm:p-6 w-full overflow-x-hidden">
                {selectedSeries.length === 0 ? (
                  <Card className="flex h-[500px] items-center justify-center">
                    <div className="text-center">
                      <Database className="mx-auto h-12 w-12 text-muted-foreground/50" />
                      <h3 className="mt-4 text-lg font-semibold">No Series Selected</h3>
                      <p className="mt-2 text-sm text-muted-foreground">Select up to 5 series from the sidebar to compare</p>
                    </div>
                  </Card>
                ) : (
                  <div className="space-y-4 sm:space-y-6">
                    <div className="flex flex-wrap items-center gap-1.5 sm:gap-2">
                      <span className="text-xs sm:text-sm text-muted-foreground">Comparing:</span>
                      {selectedSeries.map((id, index) => {
                        const series = availableSeries.find((s) => s.id === id);
                        return (
                          <Badge key={id} variant="secondary" className="gap-1 sm:gap-1.5 pr-1 text-[10px] sm:text-xs">
                            <div className="h-1.5 w-1.5 sm:h-2 sm:w-2 rounded-full" style={{ backgroundColor: chartColors[index] }} />
                            <span className="max-w-[80px] sm:max-w-none truncate">{series?.name || id}</span>
                            <button onClick={() => toggleSeries(id)} className="ml-0.5 sm:ml-1 rounded-full p-0.5 hover:bg-muted">
                              <X className="h-3 w-3" />
                            </button>
                          </Badge>
                        );
                      })}
                    </div>

                    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                      <Tabs
                        value={normalize ? "normalized" : "absolute"}
                        onValueChange={(v) => setNormalize(v === "normalized")}
                      >
                        <TabsList className="grid w-full grid-cols-2 sm:w-[240px]">
                          <TabsTrigger value="normalized" className="text-xs">
                            Normalized (100)
                          </TabsTrigger>
                          <TabsTrigger value="absolute" className="text-xs">
                            Absolute Values
                          </TabsTrigger>
                        </TabsList>
                      </Tabs>
                      <Button variant="outline" size="sm" className="w-full gap-2 sm:w-auto">
                        <Download className="h-4 w-4" />
                        Export
                      </Button>
                    </div>

                    {dataLoading ? (
                      <Card className="flex h-[450px] items-center justify-center">
                        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                      </Card>
                    ) : (
                      <MultiLineChart
                        title="Series Comparison"
                        description={
                          normalize ? "All series indexed to 100 at start of period" : "Absolute values (different scales)"
                        }
                        data={chartData}
                        series={chartSeries}
                        height={450}
                        normalized={normalize}
                      />
                    )}

                    <Card>
                      <CardHeader>
                        <CardTitle className="text-sm font-semibold">Statistics</CardTitle>
                        <CardDescription className="text-xs">Selected time period</CardDescription>
                      </CardHeader>
                      <CardContent>
                        <div className="overflow-x-auto">
                          <table className="w-full text-sm">
                            <thead>
                              <tr className="border-b border-border">
                                <th className="pb-3 text-left font-medium text-muted-foreground">Series</th>
                                <th className="pb-3 text-right font-medium text-muted-foreground">Latest</th>
                                <th className="pb-3 text-right font-medium text-muted-foreground">Min</th>
                                <th className="pb-3 text-right font-medium text-muted-foreground">Max</th>
                                <th className="pb-3 text-right font-medium text-muted-foreground">Change</th>
                              </tr>
                            </thead>
                            <tbody>
                              {selectedSeries.map((id, index) => {
                                const series = availableSeries.find((s) => s.id === id);
                                const data = seriesData[id] || [];
                                const latest = data[data.length - 1]?.value || 0;
                                const first = data[0]?.value || 1;
                                const min = data.length > 0 ? Math.min(...data.map((d) => d.value)) : 0;
                                const max = data.length > 0 ? Math.max(...data.map((d) => d.value)) : 0;
                                const change = ((latest - first) / first) * 100;

                                return (
                                  <tr key={id} className="border-b border-border/50">
                                    <td className="py-3">
                                      <div className="flex items-center gap-2">
                                        <div className="h-2 w-2 rounded-full" style={{ backgroundColor: chartColors[index] }} />
                                        <span className="font-medium">{series?.name || id}</span>
                                      </div>
                                    </td>
                                    <td className="py-3 text-right font-mono">
                                      {dataLoading
                                        ? "..."
                                        : latest.toLocaleString(undefined, {
                                            maximumFractionDigits: 2,
                                          })}
                                    </td>
                                    <td className="py-3 text-right font-mono text-muted-foreground">
                                      {dataLoading
                                        ? "..."
                                        : min.toLocaleString(undefined, {
                                            maximumFractionDigits: 2,
                                          })}
                                    </td>
                                    <td className="py-3 text-right font-mono text-muted-foreground">
                                      {dataLoading
                                        ? "..."
                                        : max.toLocaleString(undefined, {
                                            maximumFractionDigits: 2,
                                          })}
                                    </td>
                                    <td
                                      className={`py-3 text-right font-mono ${
                                        change >= 0 ? "text-positive" : "text-negative"
                                      }`}
                                    >
                                      {dataLoading ? "..." : `${change >= 0 ? "+" : ""}${change.toFixed(2)}%`}
                                    </td>
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>
                      </CardContent>
                    </Card>
                  </div>
                )}
              </div>
            </ScrollArea>
          </div>
        </div>
      </div>
    </div>
  );
}


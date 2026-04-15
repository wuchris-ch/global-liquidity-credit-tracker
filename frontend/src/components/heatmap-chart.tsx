"use client";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { InfoTooltip, InfoTooltipProps } from "@/components/info-tooltip";

export interface HeatmapChartProps {
  title: string;
  description?: string;
  rowLabels: string[];
  columnLabels: string[];
  data: (number | null)[][];
  formatValue?: (value: number) => string;
  getColor: (value: number | null) => string;
  info?: Omit<InfoTooltipProps, "size">;
}

const defaultFormat = (value: number) => value.toFixed(2);

export function HeatmapChart({
  title,
  description,
  rowLabels,
  columnLabels,
  data,
  formatValue = defaultFormat,
  getColor,
  info,
}: HeatmapChartProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-sm font-semibold">
          {title}
          {info && <InfoTooltip {...info} size="sm" />}
        </CardTitle>
        {description && (
          <CardDescription className="text-xs">{description}</CardDescription>
        )}
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr>
                <th className="p-2 text-left text-xs font-medium text-muted-foreground">
                  {/* top-left empty */}
                </th>
                {columnLabels.map((col) => (
                  <th
                    key={col}
                    className="p-2 text-center text-xs font-medium capitalize text-muted-foreground"
                  >
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rowLabels.map((row, i) => (
                <tr key={row} className="border-t border-border/50">
                  <td className="p-2 text-sm font-medium">{row}</td>
                  {data[i].map((value, j) => (
                    <td
                      key={j}
                      className={`p-2 text-center ${getColor(value)}`}
                    >
                      <span className="font-mono text-sm">
                        {value !== null && !Number.isNaN(value)
                          ? formatValue(value)
                          : "N/A"}
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

export const sharpeHeatmapColor = (value: number | null) => {
  if (value === null || Number.isNaN(value)) return "bg-muted";
  if (value > 1.5) return "bg-emerald-500/70 text-white";
  if (value > 1.0) return "bg-emerald-500/50";
  if (value > 0.5) return "bg-emerald-500/30";
  if (value > 0) return "bg-yellow-500/30";
  if (value > -0.5) return "bg-orange-500/30";
  return "bg-red-500/50";
};

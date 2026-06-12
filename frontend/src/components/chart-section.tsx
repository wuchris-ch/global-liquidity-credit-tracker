import { cn } from "@/lib/utils";

interface ChartSectionProps {
  title: string;
  /** One-line reading of the chart in plain language, set in serif. */
  reading?: string;
  /** Source / footnote line under the chart. */
  source?: string;
  /** Control rendered to the right of the title (e.g. RangeTabs). */
  control?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}

/**
 * Editorial chart frame: charts sit directly on the paper with a title,
 * an optional one-line reading, and a source line. No card chrome.
 */
export function ChartSection({
  title,
  reading,
  source,
  control,
  children,
  className,
}: ChartSectionProps) {
  return (
    <section className={cn("space-y-3", className)}>
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-2">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold tracking-tight">{title}</h3>
          {reading && (
            <p className="mt-0.5 max-w-[70ch] font-serif text-[0.9375rem] italic leading-snug text-muted-foreground">
              {reading}
            </p>
          )}
        </div>
        {control && <div className="shrink-0">{control}</div>}
      </div>
      {children}
      {source && (
        <p className="font-mono text-[0.6875rem] text-muted-foreground/80">{source}</p>
      )}
    </section>
  );
}

"use client";

import { useMemo, useState } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
} from "recharts";
import { useGLCIData } from "@/hooks/use-series-data";
import { useRegimeHistory } from "@/hooks/use-regime-history";
import { GlciChart } from "@/components/glci-chart";
import { ChartSection } from "@/components/chart-section";
import { RangeTabs } from "@/components/range-tabs";
import { RegimeStamp } from "@/components/regime-stamp";
import { DataLoadError } from "@/components/data-load-error";
import { getDateRange, type TimeRange } from "@/lib/utils";
import { formatShortDate } from "@/lib/data-status";
import {
  attributionSentence,
  currentRegimeStanding,
  ordinal,
  signed,
  standingSentence,
} from "@/lib/brief";
import {
  AXIS_TICK,
  AXIS_LINE,
  GRID_PROPS,
  TOOLTIP_STYLE,
  TOOLTIP_LABEL_STYLE,
  PILLAR_COLOR,
  formatTickDate,
  formatTooltipDate,
} from "@/lib/chart-theme";
import type { RegimePeriod } from "@/lib/api";

// ---------------------------------------------------------------------------
// Pillar labels and ordering
// ---------------------------------------------------------------------------

const PILLAR_ORDER = ["liquidity", "credit", "stress"] as const;
type PillarName = (typeof PILLAR_ORDER)[number];

const PILLAR_LABELS: Record<PillarName, string> = {
  liquidity: "Liquidity",
  credit: "Credit",
  stress: "Funding stress (inverted)",
};

function PillarDot({ name }: { name: string }) {
  return (
    <span
      aria-hidden="true"
      className="inline-block h-2 w-2 shrink-0 rounded-full"
      style={{ backgroundColor: PILLAR_COLOR[name] ?? "var(--muted-foreground)" }}
    />
  );
}

// ---------------------------------------------------------------------------
// Pillar contribution history chart
// ---------------------------------------------------------------------------

interface ContributionRow {
  date: string;
  liquidity?: number;
  credit?: number;
  stress?: number;
}

function formatSignedTick(v: number): string {
  const fixed = Math.abs(v).toFixed(1);
  return v < 0 ? `−${fixed}` : fixed;
}

function PillarContributionChart({ rows, height = 280 }: { rows: ContributionRow[]; height?: number }) {
  return (
    <div style={{ height }} className="w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid {...GRID_PROPS} />
          <XAxis
            dataKey="date"
            tick={AXIS_TICK}
            tickLine={false}
            axisLine={AXIS_LINE}
            tickFormatter={formatTickDate}
            minTickGap={48}
          />
          <YAxis
            tick={AXIS_TICK}
            tickLine={false}
            axisLine={false}
            width={44}
            domain={["auto", "auto"]}
            tickFormatter={formatSignedTick}
          />
          <Tooltip
            contentStyle={TOOLTIP_STYLE}
            labelStyle={TOOLTIP_LABEL_STYLE}
            labelFormatter={(label) => formatTooltipDate(String(label))}
            formatter={(value, name) => [signed(Number(value)), String(name)]}
          />
          <ReferenceLine y={0} stroke="var(--border)" />
          {PILLAR_ORDER.map((name) => (
            <Line
              key={name}
              type="monotone"
              dataKey={name}
              name={PILLAR_LABELS[name]}
              stroke={PILLAR_COLOR[name]}
              strokeWidth={1.25}
              dot={false}
              activeDot={{ r: 3, strokeWidth: 0, fill: PILLAR_COLOR[name] }}
              isAnimationActive={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Regime timeline strip
// ---------------------------------------------------------------------------

const TIMELINE_FILL: Record<string, string> = {
  loose: "color-mix(in oklch, var(--regime-loose) 35%, transparent)",
  neutral: "color-mix(in oklch, var(--regime-neutral) 35%, transparent)",
  tight: "color-mix(in oklch, var(--regime-tight) 35%, transparent)",
};

function RegimeTimelineStrip({ periods }: { periods: RegimePeriod[] }) {
  const spans = useMemo(() => {
    if (!periods.length) return [];
    const t0 = new Date(periods[0].start).getTime();
    const t1 = new Date(periods[periods.length - 1].end).getTime();
    const total = Math.max(t1 - t0, 1);
    return periods.map((p) => {
      const span = Math.max(new Date(p.end).getTime() - new Date(p.start).getTime(), 0);
      return { ...p, widthPct: (span / total) * 100 };
    });
  }, [periods]);

  if (!spans.length) return null;

  return (
    <div
      className="flex h-7 w-full overflow-hidden rounded-sm"
      role="img"
      aria-label="Timeline of liquidity regimes, loose, neutral and tight, with each period's width proportional to its duration"
    >
      {spans.map((p, i) => (
        <div
          key={`${p.start}-${i}`}
          className="h-full"
          style={{
            width: `${p.widthPct}%`,
            backgroundColor: TIMELINE_FILL[p.regime] ?? "transparent",
          }}
          title={`${p.regime}: ${formatShortDate(p.start)} to ${formatShortDate(p.end)}`}
        />
      ))}
    </div>
  );
}

/** Years of regime history shown in the strip; the full history is too
 * flip-heavy in the early decades to read as anything but noise. */
const TIMELINE_YEARS = 15;

function clipPeriods(periods: RegimePeriod[], years: number): RegimePeriod[] {
  if (!periods.length) return [];
  const end = periods[periods.length - 1].end;
  const cut = new Date(end);
  cut.setFullYear(cut.getFullYear() - years);
  const cutoff = cut.toISOString().slice(0, 10);
  return periods
    .filter((p) => p.end > cutoff)
    .map((p) => (p.start < cutoff ? { ...p, start: cutoff } : p));
}

function regimeWeeksCaption(periods: RegimePeriod[]): string {
  const weeks: Record<string, number> = {};
  for (const p of periods) {
    const w = Math.round(
      (new Date(p.end).getTime() - new Date(p.start).getTime()) / (7 * 864e5)
    );
    weeks[p.regime] = (weeks[p.regime] ?? 0) + w;
  }
  const fmt = (k: string) => (weeks[k] ?? 0).toLocaleString("en-US");
  return `Past ${TIMELINE_YEARS} years: loose ${fmt("loose")} weeks · neutral ${fmt("neutral")} · tight ${fmt("tight")}`;
}

// ---------------------------------------------------------------------------
// Loading skeleton
// ---------------------------------------------------------------------------

function IndexSkeleton() {
  return (
    <div className="animate-pulse space-y-6 pt-10 sm:pt-14" aria-label="Loading the index">
      <div className="h-4 w-28 rounded bg-muted" />
      <div className="h-10 w-3/4 max-w-2xl rounded bg-muted" />
      <div className="space-y-2">
        <div className="h-5 w-full max-w-2xl rounded bg-muted" />
        <div className="h-5 w-2/3 max-w-xl rounded bg-muted" />
      </div>
      <div className="h-72 w-full rounded bg-muted" />
      <div className="h-40 w-full max-w-2xl rounded bg-muted" />
      <div className="h-56 w-full rounded bg-muted" />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function GlciPage() {
  const [chartRange, setChartRange] = useState<TimeRange>("5y");
  const chartDates = useMemo(() => getDateRange(chartRange), [chartRange]);

  const glci = useGLCIData({ start: chartDates.start, end: chartDates.end });
  const history = useRegimeHistory();

  const standing = useMemo(
    () =>
      glci.data
        ? currentRegimeStanding(history.data, glci.data.regime, glci.data.date)
        : null,
    [history.data, glci.data]
  );

  const contributionRows = useMemo<ContributionRow[]>(() => {
    if (!glci.data) return [];
    const pillarData = glci.data.pillar_data ?? {};
    const weights = new Map(glci.data.pillars.map((p) => [p.name, p.weight]));
    const byDate = new Map<string, ContributionRow>();
    for (const name of PILLAR_ORDER) {
      const weight = weights.get(name);
      if (weight == null) continue;
      for (const point of pillarData[name] ?? []) {
        const row = byDate.get(point.date) ?? { date: point.date };
        row[name] = point.value * weight;
        byDate.set(point.date, row);
      }
    }
    return [...byDate.values()].sort((a, b) => a.date.localeCompare(b.date));
  }, [glci.data]);

  if (glci.error) {
    return (
      <div className="mx-auto w-full max-w-6xl px-4 py-10 sm:px-8">
        <DataLoadError title="The Index could not be loaded" onRetry={glci.refetch} />
      </div>
    );
  }

  if (glci.isLoading || !glci.data || !standing) {
    return (
      <div className="mx-auto w-full max-w-6xl px-4 pb-16 sm:px-8">
        <IndexSkeleton />
      </div>
    );
  }

  const g = glci.data;
  const orderedPillars = PILLAR_ORDER.map((name) =>
    g.pillars.find((p) => p.name === name)
  ).filter((p): p is NonNullable<typeof p> => p != null);

  return (
    <div className="mx-auto w-full max-w-6xl px-4 pb-16 sm:px-8">
      {/* Header */}
      <section className="pt-10 sm:pt-14">
        <span className="font-mono text-xs uppercase tracking-[0.18em] text-muted-foreground">
          The Index
        </span>
        <h1 className="mt-4 max-w-3xl font-serif text-3xl font-medium leading-[1.1] tracking-tight sm:text-4xl">
          One number for global liquidity and credit.
        </h1>
        <p className="mt-5 max-w-[70ch] font-serif text-lg leading-relaxed text-muted-foreground">
          The GLCI is a weekly composite of three latent factors: central-bank
          liquidity (40%), private credit growth (35%) and funding stress (25%,
          inverted so that calmer markets raise the index). The composite is
          scaled to a mean of 100 and a standard deviation of 10, then
          classified as Loose, Neutral or Tight where its two-year rolling
          z-score crosses ±1σ.
        </p>
        <div className="mt-5 flex flex-wrap items-baseline gap-x-3 gap-y-2">
          <RegimeStamp regime={g.regime} detail={`${ordinal(standing.weeks)} week`} />
          <p className="font-serif text-[1.0625rem] leading-relaxed">
            {standingSentence(g, standing)}
          </p>
        </div>
      </section>

      {/* The index chart */}
      <div className="rule mt-10" />
      <ChartSection
        className="mt-8"
        title="Global Liquidity & Credit Index"
        reading="Shaded bands mark the regime in force at the time; the index is scaled to mean 100, one band per 10 points."
        source={`Composite of liquidity (40%), credit (35%) and inverted funding-stress (25%) factors. Weekly, through ${formatShortDate(g.date)}.`}
        control={
          <RangeTabs
            value={chartRange}
            onChange={setChartRange}
            ranges={["1y", "2y", "5y", "10y", "all"]}
          />
        }
      >
        <GlciChart data={g.data} periods={history.data?.periods} height={320} />
      </ChartSection>

      {/* Pillar decomposition */}
      <div className="rule mt-10" />
      <section className="mt-8">
        <h2 className="text-sm font-semibold tracking-tight">
          What is inside the number
        </h2>

        {orderedPillars.length === 0 ? (
          <p className="mt-4 font-serif text-[0.9375rem] italic text-muted-foreground">
            The pillar breakdown is unavailable right now.
          </p>
        ) : (
          <>
            <div className="mt-4 max-w-2xl overflow-x-auto">
              <table className="w-full border-collapse text-sm">
                <thead>
                  <tr className="border-b border-border">
                    <th className="py-2 pr-4 text-left text-xs font-medium tracking-wide text-muted-foreground">
                      Pillar
                    </th>
                    <th className="py-2 pl-4 text-right text-xs font-medium tracking-wide text-muted-foreground">
                      Factor value
                    </th>
                    <th className="py-2 pl-4 text-right text-xs font-medium tracking-wide text-muted-foreground">
                      Weight
                    </th>
                    <th className="py-2 pl-4 text-right text-xs font-medium tracking-wide text-muted-foreground">
                      Contribution
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {orderedPillars.map((pillar) => (
                    <tr key={pillar.name} className="border-b border-border">
                      <td className="py-2.5 pr-4">
                        <span className="flex items-center gap-2">
                          <PillarDot name={pillar.name} />
                          {PILLAR_LABELS[pillar.name as PillarName] ?? pillar.name}
                        </span>
                      </td>
                      <td className="py-2.5 pl-4 text-right font-mono tabular-nums">
                        {signed(pillar.value)}
                      </td>
                      <td className="py-2.5 pl-4 text-right font-mono tabular-nums">
                        {Math.round(pillar.weight * 100)}%
                      </td>
                      <td className="py-2.5 pl-4 text-right font-mono tabular-nums">
                        {signed(pillar.contribution)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="mt-3 font-mono text-[0.6875rem] text-muted-foreground/80">
              As of {formatShortDate(g.date)}. Factor values are post
              sign-inversion (stress already enters inverted), so contribution
              = value × weight and the three contributions are directly
              additive; a negative contribution is a drag on the index.
            </p>
          </>
        )}

        {contributionRows.length === 0 ? (
          <p className="mt-8 font-serif text-[0.9375rem] italic text-muted-foreground">
            Pillar history is unavailable for this period.
          </p>
        ) : (
          <ChartSection
            className="mt-8"
            title="Weighted pillar contributions"
            reading="Each line is a pillar's factor value times its weight; the lines sum to the index in standardized units."
            source="Weighted latent factors, post sign-inversion. Weekly. Zero line marks no contribution."
          >
            <div className="flex flex-wrap gap-x-5 gap-y-1 font-mono text-[0.6875rem] text-muted-foreground">
              {PILLAR_ORDER.map((name) => (
                <span key={name} className="flex items-center gap-1.5">
                  <PillarDot name={name} />
                  {PILLAR_LABELS[name]}
                </span>
              ))}
            </div>
            <PillarContributionChart rows={contributionRows} height={280} />
          </ChartSection>
        )}

        {orderedPillars.length > 0 && (
          <p className="mt-6 max-w-[70ch] font-serif text-[1.0625rem] leading-relaxed">
            {attributionSentence(g.pillars)}
          </p>
        )}
      </section>

      {/* Regime history */}
      <div className="rule mt-10" />
      <section className="mt-8">
        <h2 className="text-sm font-semibold tracking-tight">Regime history</h2>
        {history.error ? (
          <p className="mt-4 font-serif text-[0.9375rem] italic text-muted-foreground">
            The regime history is unavailable right now.
          </p>
        ) : !history.data || history.data.periods.length === 0 ? (
          <div className="mt-4 h-7 w-full animate-pulse rounded-sm bg-muted" />
        ) : (
          <>
            <div className="mt-4">
              <RegimeTimelineStrip periods={clipPeriods(history.data.periods, TIMELINE_YEARS)} />
            </div>
            <div className="mt-1.5 flex justify-between font-mono text-[0.6875rem] tabular-nums text-muted-foreground/80">
              <span>
                {formatShortDate(
                  clipPeriods(history.data.periods, TIMELINE_YEARS)[0]?.start ?? null
                )}
              </span>
              <span>
                {formatShortDate(
                  history.data.periods[history.data.periods.length - 1]?.end ?? null
                )}
              </span>
            </div>
            <p className="mt-2 font-mono text-[0.6875rem] tabular-nums text-muted-foreground/80">
              {regimeWeeksCaption(clipPeriods(history.data.periods, TIMELINE_YEARS))}
            </p>
          </>
        )}
      </section>

      {/* Methodology */}
      <div className="rule mt-10" />
      <section className="mt-8">
        <h2 className="text-sm font-semibold tracking-tight">How it&apos;s built</h2>
        <div className="mt-5 max-w-[70ch] space-y-6">
          <div>
            <h3 className="text-sm font-semibold tracking-tight">The three pillars</h3>
            <p className="mt-2 font-serif leading-relaxed">
              The index blends three families of weekly data. The liquidity
              pillar (40% weight) tracks central-bank balance sheets, reserve
              balances and monetary aggregates. The credit pillar (35%) tracks
              private-sector credit growth from bank lending and BIS credit
              data. The funding-stress pillar (25%) tracks credit spreads and
              funding rates, and enters the composite inverted: higher stress
              lowers the index. Before extraction, every component series is
              resampled to weekly, transformed (a 104-week rolling z-score, a
              52-week growth rate, or both) and sign-flipped so that its
              expected factor loading is positive.
            </p>
          </div>
          <div>
            <h3 className="text-sm font-semibold tracking-tight">Factor extraction</h3>
            <p className="mt-2 font-serif leading-relaxed">
              Each pillar is summarized by a single latent factor. When the
              data panel is complete enough (at least half the rows complete,
              no more than 30% missing), the factor comes from a dynamic
              factor model estimated by EM. Otherwise the pipeline falls back
              to the first principal component, with loadings re-estimated by
              Ridge regression for stability when components are collinear.
              The factor is oriented so that its average loading is positive:
              factor up means components up. If a pillar cannot be computed at
              all (a data outage), its weight is redistributed proportionally
              across the remaining pillars rather than failing the run.
            </p>
          </div>
          <div>
            <h3 className="text-sm font-semibold tracking-tight">
              Normalization and regimes
            </h3>
            <p className="mt-2 font-serif leading-relaxed">
              The three factors are combined at fixed weights (liquidity 0.40,
              credit 0.35, stress 0.25, with stress inverted) and the
              composite is scaled to a mean of 100 and a standard deviation of
              10, so one band on the chart is one standard deviation. Regimes
              come from a rolling z-score of the composite over a 104-week
              window: below −1σ is tight, above +1σ is loose, anything in
              between is neutral. The dashboard also reports 4-week momentum
              and a heuristic probability of regime change based on the
              distance to the nearest threshold and the z-score trend.
            </p>
          </div>
          <div>
            <h3 className="text-sm font-semibold tracking-tight">What it is not</h3>
            <p className="mt-2 font-serif leading-relaxed">
              The regimes are statistical buckets, not economic declarations:
              ±1σ is a convention, and a reading of 0.9σ is not meaningfully
              different from 1.1σ. The sample, long as it is, overlaps a
              limited number of macro cycles, so regime statistics partly
              describe those specific episodes. The historical relationships
              in the playbook are conditional averages, not causal claims. The
              backtest avoids look-ahead by re-classifying regimes with an
              expanding window (with a one-year burn-in), but the live index
              itself uses a rolling window and is revised as source data
              arrives, so the most recent readings are the least settled.
            </p>
          </div>
        </div>
      </section>
    </div>
  );
}

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
          The GLCI combines three weekly latent factors: central-bank liquidity (40%), private
          credit growth (35%), and inverted funding stress (25%). Higher readings mean easier
          conditions. The index is scaled to a mean of 100 and a standard deviation of 10. A
          104-week rolling z-score sets the Loose, Neutral, and Tight regimes at ±1σ.
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
          What is driving the index
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
                      Raw contribution
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
              sign-inversion (stress already enters inverted). Raw contribution
              = value × weight; the three values add to the pre-normalization
              composite, not to index points. A negative value is a drag.
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
            reading="Each line is a pillar's factor value times its weight; together they sum to the raw composite before its final 100/10 rescaling."
            source="Weighted latent factors, post sign-inversion. Raw composite units, weekly. Zero marks no contribution."
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
              The liquidity pillar (40%) tracks central-bank balance sheets, reserve balances,
              and monetary aggregates. The credit pillar (35%) tracks bank lending and BIS
              private-credit data. The funding-stress pillar (25%) tracks credit spreads and
              funding rates, then enters inverted so higher stress lowers the index. Each component
              is resampled weekly and transformed with a 104-week rolling z-score, a 52-week growth
              rate, or both. Its economic sign is set before factor extraction.
            </p>
          </div>
          <div>
            <h3 className="text-sm font-semibold tracking-tight">Factor extraction</h3>
            <p className="mt-2 font-serif leading-relaxed">
              Each pillar becomes one latent factor. The production model initializes from the
              first principal component, then re-estimates loadings with Ridge regression. Economic
              sign constraints are enforced while factor and loadings are solved jointly: an input
              that moves persistently against its configured direction receives zero loading and is
              disclosed as excluded. Coverage and concentration gates prevent a pillar from
              collapsing onto one source. Each factor is then scaled to unit variance. All three
              pillars are required; the update fails rather than publishing a partial or reweighted
              index.
            </p>
          </div>
          <div>
            <h3 className="text-sm font-semibold tracking-tight">
              Normalization and regimes
            </h3>
            <p className="mt-2 font-serif leading-relaxed">
              Fixed weights combine liquidity (0.40), credit (0.35), and inverted stress (0.25).
              The result is scaled to mean 100 and standard deviation 10, so one chart band equals
              one standard deviation. The 104-week rolling z-score defines Tight below −1σ, Loose
              above +1σ, and Neutral between them. Four-week momentum shows direction. The
              boundary-pressure score is uncalibrated and uses distance to the nearest threshold
              plus the z-score trend.
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
              backtest uses the same rolling 104-week classifier with a 20-week minimum
              and enters on the next weekly bar. That controls classification
              and execution timing, but it does not turn the upstream index
              into a point-in-time series. Source revisions and factor
              re-estimation can rewrite the displayed history, which should be
              read as a current-vintage reconstruction rather than a simulated
              live record.
            </p>
          </div>
        </div>
      </section>
    </div>
  );
}

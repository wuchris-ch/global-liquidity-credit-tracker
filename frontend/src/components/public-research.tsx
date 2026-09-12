"use client";

import { useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import {
  ArrowDownToLine,
  ArrowRight,
  Check,
  ExternalLink,
  Fingerprint,
  Link2,
  BookOpen,
  SlidersHorizontal,
} from "lucide-react";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  CartesianGrid,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceLine,
} from "recharts";
import {
  atlas,
  compare,
  csv,
  dateLabel,
  focusValue,
  number,
  saveFile,
  type Study,
} from "@/lib/public-research";

const label =
  "text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground";
const control =
  "mt-2 w-full rounded-md border border-border bg-background px-3 py-2.5 text-sm focus-visible:outline-2 focus-visible:outline-primary";
const action =
  "inline-flex items-center justify-center gap-2 rounded-md border border-border bg-card px-3 py-2 text-xs font-medium transition-colors hover:bg-muted focus-visible:outline-2 focus-visible:outline-primary";
const notebookTabs = [
  ["analysis", "Analysis"],
  ["evidence", "Source evidence"],
  ["method", "Method"],
];
const formulas: Record<string, string> = {
  level:
    "Published annualized quarterly growth rate. No additional transformation.",
  difference:
    "Current month's payroll level minus the preceding month's level, using the same vintage for both. Units: thousands of jobs.",
  pct_change:
    "(Current month's index ÷ preceding month's index − 1) × 100, using the same vintage for both. This is monthly growth, not annualized growth.",
};

function Chart({
  study,
  before,
  after,
  mode,
  range,
}: {
  study: Study;
  before: number;
  after: number;
  mode: string;
  range: number;
}) {
  const rows = compare(
    study,
    study.snapshots[before],
    study.snapshots[after],
  ).slice(-range);
  const shortDate = (date: string) =>
    study.frequency === "quarterly"
      ? `Q${Math.floor(Number(date.slice(5, 7)) / 3) + 1} '${date.slice(2, 4)}`
      : new Date(date + "T12:00:00Z").toLocaleDateString("en-US", {
          month: "short",
          year: "2-digit",
          timeZone: "UTC",
        });
  return (
    <div
      className="h-[260px] w-full sm:h-[310px]"
      role="img"
      aria-label={`${study.name}: ${mode === "revision" ? "revisions" : "baseline and comparison"} over ${rows.length} observations. Exact values are in the data table below.`}
    >
      <ResponsiveContainer width="100%" height="100%" minWidth={0}>
        <LineChart
          data={rows}
          margin={{ top: 18, right: 16, bottom: 8, left: 0 }}
          accessibilityLayer
        >
          <CartesianGrid
            stroke="var(--border)"
            vertical={false}
            strokeDasharray="3 4"
          />
          <XAxis
            dataKey="date"
            tickFormatter={shortDate}
            tick={{ fontSize: 10, fill: "var(--muted-foreground)" }}
            axisLine={false}
            tickLine={false}
            minTickGap={30}
            dy={8}
          />
          <YAxis
            width={44}
            tick={{ fontSize: 10, fill: "var(--muted-foreground)" }}
            axisLine={false}
            tickLine={false}
            domain={["auto", "auto"]}
            tickFormatter={(v) =>
              number(
                Number(v),
                mode === "revision"
                  ? study.decimals
                  : Math.min(study.decimals, 1),
              )
            }
          />
          <Tooltip
            labelFormatter={(value) => dateLabel(String(value))}
            formatter={(value, name) => [
              `${number(Number(value), study.decimals)} ${mode === "revision" ? study.delta_unit : study.unit}`,
              name,
            ]}
            contentStyle={{
              background: "var(--card)",
              border: "1px solid var(--border)",
              borderRadius: 6,
              fontSize: 12,
            }}
          />
          {/* Direct children avoid react-is 18 fragment detection under React 19. */}
          {mode === "revision" && (
            <ReferenceLine y={0} stroke="var(--chart-3)" />
          )}
          {mode === "revision" && (
            <Line
              name="Revision"
              type="linear"
              dataKey="revision"
              stroke="var(--chart-2)"
              strokeWidth={2}
              dot={{ r: 3, fill: "var(--background)" }}
              isAnimationActive={false}
              connectNulls={false}
            />
          )}
          {mode !== "revision" && (
            <Line
              name={`Baseline · ${dateLabel(study.snapshots[before].date)}`}
              type="linear"
              dataKey="baseline"
              stroke="var(--chart-3)"
              strokeDasharray="5 4"
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
              connectNulls={false}
            />
          )}
          {mode !== "revision" && (
            <Line
              name={`Comparison · ${dateLabel(study.snapshots[after].date)}`}
              type="linear"
              dataKey="comparison"
              stroke="var(--chart-2)"
              strokeWidth={2.5}
              dot={{ r: 3, fill: "var(--background)" }}
              isAnimationActive={false}
              connectNulls={false}
            />
          )}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export function PublicResearch() {
  const search = useSearchParams();
  const study =
    atlas.cases.find((item) => item.id === search.get("study")) ??
    atlas.cases[0];
  const snapshotIndex = (key: string, fallback: number) => {
    const value = search.get(key);
    return value !== null && /^[0-2]$/.test(value) ? Number(value) : fallback;
  };
  const before = snapshotIndex("before", 0),
    after = snapshotIndex("after", 1);
  const reference = search.get("threshold");
  const threshold =
    reference !== null &&
    reference.trim() !== "" &&
    Number.isFinite(Number(reference)) &&
    Math.abs(Number(reference)) <= 10000
      ? Number(reference)
      : study.threshold;
  const [view, setView] = useState("analysis"),
    [mode, setMode] = useState("levels"),
    [longRange, setLongRange] = useState(false);
  const [notice, setNotice] = useState(""),
    [verification, setVerification] = useState<Record<string, string>>({});
  const baseline = study.snapshots[before],
    comparison = study.snapshots[after];
  const left = focusValue(study, baseline),
    right = focusValue(study, comparison);
  const delta =
    left === null || right === null
      ? null
      : Math.round((right - left) * 1e8) / 1e8;
  const changed =
    left !== null && right !== null && left > threshold !== right > threshold;
  const range =
    study.frequency === "quarterly"
      ? longRange
        ? 12
        : 6
      : longRange
        ? 36
        : 12;
  const update = (values: Record<string, string>) => {
    const params = new URLSearchParams(search.toString());
    Object.entries(values).forEach(([key, value]) => params.set(key, value));
    window.history.replaceState(null, "", `?${params}`);
    setNotice("");
  };
  const selectStudy = (next: Study) => {
    update({
      study: next.id,
      before: "0",
      after: "1",
      threshold: String(next.threshold),
    });
    setMode("levels");
  };
  const verify = async () => {
    const key = `${study.id}-${comparison.date}`;
    setVerification((current) => ({
      ...current,
      [key]: "Checking source bytes…",
    }));
    try {
      const response = await fetch(comparison.raw_url, { cache: "no-store" });
      if (!response.ok) throw new Error("Source unavailable");
      const hash = await crypto.subtle.digest(
        "SHA-256",
        await response.arrayBuffer(),
      );
      const actual = Array.from(new Uint8Array(hash), (byte) =>
        byte.toString(16).padStart(2, "0"),
      ).join("");
      setVerification((current) => ({
        ...current,
        [key]:
          actual === comparison.sha256
            ? "Verified: downloaded bytes match the published capture."
            : "Mismatch: the downloaded file does not match the published hash.",
      }));
    } catch {
      setVerification((current) => ({
        ...current,
        [key]:
          "Verification unavailable. Download the source and compare its SHA-256 hash.",
      }));
    }
  };
  const share = async () => {
    try {
      const url = new URL(window.location.href);
      Object.entries({
        study: study.id,
        before: String(before),
        after: String(after),
        threshold: String(threshold),
      }).forEach(([key, value]) => url.searchParams.set(key, value));
      await navigator.clipboard.writeText(url.toString());
      setNotice("Comparison link copied.");
    } catch {
      setNotice("Copy the current browser address to share this comparison.");
    }
  };
  const exportBundle = () =>
    saveFile(
      `${study.id}-evidence.json`,
      JSON.stringify(
        {
          schema_version: "research-atlas-export/1",
          study,
          selection: {
            baseline: baseline.date,
            comparison: comparison.date,
            threshold,
          },
          results: compare(study, baseline, comparison),
          formula: formulas[study.operation],
          date_basis:
            "Historical source vintages retrieved later; not contemporaneous platform publications.",
        },
        null,
        2,
      ),
      "application/json",
    );

  return (
    <div className="mx-auto max-w-6xl px-4 pb-16 pt-9 sm:px-8 sm:pt-12">
      <header className="flex flex-col justify-between gap-6 border-b border-foreground/20 pb-8 sm:flex-row sm:items-end">
        <div className="max-w-2xl">
          <p className={label}>
            Research atlas <span className="mx-2 text-border">/</span> US
            macroeconomic revisions
          </p>
          <h1 className="mt-4 font-serif text-[2.7rem] leading-[1.04] tracking-tight sm:text-6xl">
            The economy changes.
            <br />
            <span className="text-muted-foreground">So does its history.</span>
          </h1>
          <p className="mt-5 max-w-xl text-sm leading-6 text-muted-foreground">
            A number is only part of the story. Explore what was reported, what
            was revised, and whether the difference changes your reading.
          </p>
        </div>
        <div className="flex shrink-0 gap-7 pb-1">
          <div>
            <p className="font-mono text-3xl">03</p>
            <p className={`${label} mt-1`}>Studies</p>
          </div>
          <div>
            <p className="font-mono text-3xl">09</p>
            <p className={`${label} mt-1`}>Source vintages</p>
          </div>
        </div>
      </header>

      <Link
        href="/research/lab"
        className="mt-6 flex flex-col justify-between gap-4 rounded-lg border border-foreground/25 bg-card px-5 py-4 sm:flex-row sm:items-center"
      >
        <div>
          <p className={label}>Release laboratory</p>
          <p className="mt-2 font-serif text-xl">
            Two years of payroll revisions. A new way to explore the evidence.
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            Follow releases, build a saved comparison, and replay every result.
          </p>
        </div>
        <span className="inline-flex shrink-0 items-center gap-2 text-xs font-medium">
          Open the laboratory <ArrowRight size={14} />
        </span>
      </Link>

      <section
        aria-label="Choose a research study"
        className="grid gap-3 py-6 md:grid-cols-3"
      >
        {atlas.cases.map((item, index) => (
          <button
            key={item.id}
            onClick={() => selectStudy(item)}
            aria-pressed={study.id === item.id}
            className={`group rounded-lg border p-4 text-left transition-colors focus-visible:outline-2 focus-visible:outline-primary ${study.id === item.id ? "border-foreground/60 bg-card shadow-sm" : "border-border hover:border-foreground/30 hover:bg-card/70"}`}
          >
            <div className="flex justify-between">
              <span className={label}>
                0{index + 1} <span className="mx-1">/</span> {item.category}
              </span>
              {study.id === item.id ? (
                <span className="flex items-center gap-1 text-[10px] font-medium">
                  <Check size={12} /> Selected
                </span>
              ) : (
                <ArrowRight size={14} className="text-muted-foreground" />
              )}
            </div>
            <h2 className="mt-3 font-serif text-2xl">{item.title}</h2>
            <p className="mt-1 text-xs text-muted-foreground">
              {item.period_label} · {item.snapshots.length} releases
            </p>
            <div className="mt-4 flex items-center gap-2 font-mono text-sm tabular-nums">
              {item.snapshots.map((snapshot, i) => (
                <span key={snapshot.date} className="flex items-center gap-2">
                  {i > 0 && (
                    <ArrowRight size={12} className="text-muted-foreground" />
                  )}
                  {number(focusValue(item, snapshot), item.decimals)}
                  {i === 2 && (
                    <span className="font-sans text-[10px] text-muted-foreground">
                      {item.unit}
                    </span>
                  )}
                </span>
              ))}
            </div>
          </button>
        ))}
      </section>

      <section
        className="overflow-hidden rounded-xl border border-border bg-card"
        aria-label="Research notebook"
      >
        <div className="flex flex-col justify-between gap-4 border-b border-border px-5 py-5 sm:flex-row sm:items-center sm:px-6">
          <div>
            <p className={label}>{study.agency} · via FRED / ALFRED</p>
            <h2 className="mt-2 font-serif text-2xl sm:text-3xl">
              {study.name}{" "}
              <span className="text-muted-foreground">
                / {study.period_label}
              </span>
            </h2>
          </div>
          <div className="flex flex-wrap gap-2">
            <button className={action} onClick={share}>
              <Link2 size={14} /> Share view
            </button>
            <button className={action} onClick={exportBundle}>
              <ArrowDownToLine size={14} /> Evidence JSON
            </button>
          </div>
        </div>
        <div className="grid border-b border-border md:grid-cols-[1fr_1fr_1.2fr]">
          <label className="p-5 sm:px-6">
            <span className={label}>Baseline source date</span>
            <select
              aria-label="Baseline source date"
              className={control}
              value={before}
              onChange={(e) => update({ before: e.target.value })}
            >
              {study.snapshots.map((s, i) => (
                <option key={s.date} value={i}>
                  {dateLabel(s.date)} · {s.label}
                </option>
              ))}
            </select>
          </label>
          <label className="border-t border-border p-5 sm:px-6 md:border-l md:border-t-0">
            <span className={label}>Comparison source date</span>
            <select
              aria-label="Comparison source date"
              className={control}
              value={after}
              onChange={(e) => update({ after: e.target.value })}
            >
              {study.snapshots.map((s, i) => (
                <option key={s.date} value={i}>
                  {dateLabel(s.date)} · {s.label}
                </option>
              ))}
            </select>
          </label>
          <div className="border-t border-border bg-muted/30 p-5 sm:px-6 md:border-l md:border-t-0">
            <p className={label}>Keep the period fixed</p>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">
              {study.description}
            </p>
          </div>
        </div>
        <div
          role="tablist"
          aria-label="Notebook sections"
          className="flex gap-5 border-b border-border px-5 sm:px-6"
        >
          {notebookTabs.map(([id, title], index) => (
            <button
              key={id}
              id={`tab-${id}`}
              role="tab"
              tabIndex={view === id ? 0 : -1}
              onKeyDown={(event) => {
                if (
                  !["ArrowLeft", "ArrowRight", "Home", "End"].includes(
                    event.key,
                  )
                )
                  return;
                event.preventDefault();
                const next =
                  event.key === "Home"
                    ? 0
                    : event.key === "End"
                      ? 2
                      : (index + (event.key === "ArrowRight" ? 1 : 2)) % 3;
                setView(notebookTabs[next][0]);
                document
                  .getElementById(`tab-${notebookTabs[next][0]}`)
                  ?.focus();
              }}
              aria-selected={view === id}
              aria-controls={`panel-${id}`}
              className={`border-b-2 py-3 text-xs font-medium ${view === id ? "border-foreground" : "border-transparent text-muted-foreground hover:text-foreground"}`}
              onClick={() => setView(id)}
            >
              {title}
            </button>
          ))}
        </div>

        {view === "analysis" && (
          <div
            role="tabpanel"
            id="panel-analysis"
            aria-labelledby="tab-analysis"
          >
            <div className="grid grid-cols-3 divide-x divide-border border-b border-border">
              {[
                ["Baseline", left, study.unit],
                ["Comparison", right, study.unit],
                ["Revision", delta, study.delta_unit],
              ].map(([title, value, unit], i) => (
                <div key={String(title)} className="px-3 py-5 sm:px-6 sm:py-6">
                  <p className={label}>{title}</p>
                  <p
                    className={`mt-3 font-mono text-2xl tabular-nums sm:text-4xl ${i === 2 ? "text-primary" : ""}`}
                  >
                    {number(value as number | null, study.decimals, i === 2)}
                  </p>
                  <p className="mt-2 text-[11px] text-muted-foreground">
                    {String(unit)}
                    {i === 2 ? " · comparison − baseline" : ""}
                  </p>
                </div>
              ))}
            </div>
            <div className="grid lg:grid-cols-[minmax(0,1fr)_280px]">
              <div className="min-w-0 p-4 sm:p-6">
                <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <h3 className="font-serif text-xl">
                      {mode === "revision"
                        ? "Where the history changed"
                        : "Two versions of the same history"}
                    </h3>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {mode === "revision"
                        ? `Comparison minus baseline · ${study.delta_unit}`
                        : `${study.frequency === "quarterly" ? "Annualized quarterly growth" : study.operation === "difference" ? "Monthly payroll change" : "Monthly production growth"} · ${study.unit}`}
                    </p>
                  </div>
                  <div className="flex gap-1 rounded-md border border-border p-1">
                    {[
                      ["levels", "History"],
                      ["revision", "Revisions"],
                    ].map(([id, title]) => (
                      <button
                        key={id}
                        aria-pressed={mode === id}
                        onClick={() => setMode(id)}
                        className={`rounded px-2 py-1 text-[11px] ${mode === id ? "bg-foreground text-background" : "text-muted-foreground hover:bg-muted"}`}
                      >
                        {title}
                      </button>
                    ))}
                  </div>
                </div>
                <Chart
                  study={study}
                  before={before}
                  after={after}
                  mode={mode}
                  range={range}
                />
                <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
                  <div className="flex gap-4 text-[10px] text-muted-foreground">
                    {mode !== "revision" && (
                      <span className="flex items-center gap-1.5">
                        <span className="w-4 border-t-2 border-dashed border-[var(--chart-3)]" />
                        Baseline
                      </span>
                    )}
                    <span className="flex items-center gap-1.5">
                      <span className="w-4 border-t-2 border-[var(--chart-2)]" />
                      {mode === "revision" ? "Revision" : "Comparison"}
                    </span>
                  </div>
                  <button
                    className="text-xs text-primary underline underline-offset-4"
                    onClick={() => setLongRange(!longRange)}
                  >
                    {longRange ? "Show recent history" : "Show three years"}
                  </button>
                </div>
              </div>
              <aside className="border-t border-border bg-muted/25 p-5 sm:p-6 lg:border-l lg:border-t-0">
                <div className="flex items-center gap-2">
                  <SlidersHorizontal size={14} />
                  <h3 className="text-sm font-medium">
                    Test your reference level
                  </h3>
                </div>
                <p className="mt-3 text-xs leading-5 text-muted-foreground">
                  {study.question} Change the reference level to see whether the
                  two estimates give the same answer.
                </p>
                <label className="mt-4 block">
                  <span className={label}>Reference level ({study.unit})</span>
                  <input
                    aria-label="Reference level"
                    type="number"
                    step={study.id === "employment" ? 10 : 0.1}
                    min={-10000}
                    max={10000}
                    className={`${control} font-mono`}
                    value={threshold}
                    onChange={(e) => {
                      if (e.target.value !== "")
                        update({ threshold: e.target.value });
                    }}
                  />
                </label>
                <div className="mt-5 space-y-3 text-xs">
                  {[
                    ["Baseline", left],
                    ["Comparison", right],
                  ].map(([name, v]) => (
                    <div
                      key={String(name)}
                      className="flex justify-between gap-2"
                    >
                      <span className="text-muted-foreground">
                        {String(name)}
                      </span>
                      <span className="font-medium">
                        {v === null
                          ? "Unavailable"
                          : Number(v) > threshold
                            ? "Above reference"
                            : Number(v) === threshold
                              ? "At reference"
                              : "Below reference"}
                      </span>
                    </div>
                  ))}
                </div>
                <div
                  className={`mt-5 rounded-md border p-3 text-xs leading-5 ${changed ? "border-primary/30 bg-primary/5" : "border-border bg-card"}`}
                >
                  <strong className="block">
                    {changed
                      ? "The threshold reading changes."
                      : "The threshold reading holds."}
                  </strong>
                  {changed
                    ? "The selected estimates fall across your chosen boundary."
                    : "Both estimates are on the same side of the strict greater-than test."}
                </div>
                <p className="mt-3 text-[10px] leading-4 text-muted-foreground">
                  An illustrative threshold, not a forecast or trading rule.
                  Calculations use unrounded values.
                </p>
              </aside>
            </div>
            <div className="border-t border-border px-5 py-6 sm:px-6">
              <div className="flex items-center gap-2">
                <BookOpen size={16} className="text-primary" />
                <h3 className="font-serif text-xl">Reading the evidence</h3>
              </div>
              <p className="mt-3 max-w-3xl text-sm leading-7">
                For {study.period_label}, the {dateLabel(baseline.date)} vintage
                reports{" "}
                <strong>
                  {number(left, study.decimals)} {study.unit}
                </strong>
                . The {dateLabel(comparison.date)} vintage reports{" "}
                <strong>
                  {number(right, study.decimals)} {study.unit}
                </strong>
                , a{" "}
                {delta === 0
                  ? "zero revision"
                  : `${number(delta, study.decimals, true)} ${study.delta_unit} revision`}
                .{" "}
                {changed
                  ? "Your reference-level conclusion changes even though the observation period is identical."
                  : "At your selected reference level, the threshold conclusion is unchanged."}
              </p>
              <p className="mt-2 text-xs leading-5 text-muted-foreground">
                Calculated directly from the selected snapshots. These figures
                describe historical estimates, not what the platform knew at
                that historical moment.
              </p>
            </div>
            <details className="border-t border-border px-5 py-5 sm:px-6">
              <summary className="cursor-pointer text-sm font-medium">
                Inspect the calculation table{" "}
                <span className="ml-2 font-normal text-muted-foreground">
                  {compare(study, baseline, comparison).length} periods
                </span>
              </summary>
              <div className="mt-4 flex justify-end">
                <button
                  className={action}
                  onClick={() =>
                    saveFile(
                      `${study.id}-comparison.csv`,
                      csv(study, baseline, comparison),
                      "text/csv",
                    )
                  }
                >
                  <ArrowDownToLine size={13} /> Download CSV
                </button>
              </div>
              <div className="mt-3 max-h-80 overflow-auto">
                <table className="w-full text-right font-mono text-xs tabular-nums">
                  <caption className="mb-3 text-left font-sans text-xs text-muted-foreground">
                    {study.unit}; revisions in {study.delta_unit}. Empty results
                    remain unavailable.
                  </caption>
                  <thead className="sticky top-0 bg-card">
                    <tr>
                      {["Period", "Baseline", "Comparison", "Revision"].map(
                        (title) => (
                          <th
                            className="border-b border-border px-2 py-3"
                            key={title}
                          >
                            {title}
                          </th>
                        ),
                      )}
                    </tr>
                  </thead>
                  <tbody>
                    {compare(study, baseline, comparison)
                      .toReversed()
                      .map((row) => (
                        <tr
                          key={row.date}
                          className="border-b border-border/60"
                        >
                          <td className="whitespace-nowrap px-2 py-3">
                            {row.date}
                          </td>
                          <td className="px-2 py-3">
                            {number(row.baseline, study.decimals)}
                          </td>
                          <td className="px-2 py-3">
                            {number(row.comparison, study.decimals)}
                          </td>
                          <td className="px-2 py-3 text-primary">
                            {number(row.revision, study.decimals, true)}
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            </details>
          </div>
        )}

        {view === "evidence" && (
          <div
            role="tabpanel"
            id="panel-evidence"
            aria-labelledby="tab-evidence"
            className="space-y-6 p-5 sm:p-6"
          >
            <div className="max-w-2xl">
              <h3 className="font-serif text-2xl">
                Every number has a source.
              </h3>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">
                These public responses were retrieved from FRED with an explicit
                historical vintage. Download the original bytes, check their
                fingerprint, or inspect the publisher&apos;s release.
              </p>
            </div>
            <div className="grid gap-4 md:grid-cols-3">
              {study.snapshots.map((snapshot, index) => (
                <article
                  key={snapshot.date}
                  className={`rounded-lg border p-4 ${index === after ? "border-primary/40 bg-primary/[0.03]" : "border-border"}`}
                >
                  <p className={label}>{snapshot.label}</p>
                  <h4 className="mt-2 font-serif text-xl">
                    {dateLabel(snapshot.date)}
                  </h4>
                  <p className="mt-4 font-mono text-2xl">
                    {number(focusValue(study, snapshot), study.decimals)}{" "}
                    <span className="text-xs text-muted-foreground">
                      {study.unit}
                    </span>
                  </p>
                  <dl className="mt-4 space-y-2 text-xs">
                    <div>
                      <dt className="text-muted-foreground">
                        Observation period
                      </dt>
                      <dd className="mt-1">{study.period_label}</dd>
                    </div>
                    <div>
                      <dt className="text-muted-foreground">Retrieved</dt>
                      <dd className="mt-1">
                        {dateLabel(snapshot.captured_at)} (UTC)
                      </dd>
                    </div>
                    <div>
                      <dt className="text-muted-foreground">
                        Captured observations
                      </dt>
                      <dd className="mt-1">{snapshot.observations.length}</dd>
                    </div>
                  </dl>
                  <a
                    className={`${action} mt-5 w-full`}
                    href={snapshot.raw_url}
                    download
                  >
                    <ArrowDownToLine size={13} /> Original response
                  </a>
                </article>
              ))}
            </div>
            <div className="rounded-lg border border-border p-4 sm:p-5">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h4 className="flex items-center gap-2 text-sm font-medium">
                  <Fingerprint size={17} /> Comparison capture · SHA-256
                </h4>
                <button onClick={verify} className={action}>
                  Verify downloaded bytes
                </button>
              </div>
              <code className="mt-4 block break-all rounded bg-muted px-3 py-3 text-[11px] leading-5">
                {comparison.sha256}
              </code>
              <p role="status" className="mt-3 text-xs text-primary">
                {verification[`${study.id}-${comparison.date}`] ??
                  "Verification runs in your browser against the published source file."}
              </p>
              <p className="mt-2 text-[11px] leading-5 text-muted-foreground">
                A matching hash establishes file integrity against this
                published receipt. It is not a publisher signature.
              </p>
            </div>
            <div className="flex flex-wrap gap-3">
              <a
                className={action}
                href={`https://alfred.stlouisfed.org/series?seid=${study.series}`}
                target="_blank"
                rel="noreferrer"
              >
                ALFRED vintage history <ExternalLink size={12} />
              </a>
              <a
                className={action}
                href={study.source_url}
                target="_blank"
                rel="noreferrer"
              >
                Publisher release <ExternalLink size={12} />
              </a>
              <a
                className={action}
                href="/research/evidence/atlas.json"
                download
              >
                Complete collection <ArrowDownToLine size={12} />
              </a>
            </div>
          </div>
        )}

        {view === "method" && (
          <div
            role="tabpanel"
            id="panel-method"
            aria-labelledby="tab-method"
            className="grid gap-8 p-5 sm:p-8 md:grid-cols-2"
          >
            <div>
              <p className={label}>01 / Date discipline</p>
              <h3 className="mt-3 font-serif text-2xl">
                Three dates. Different meanings.
              </h3>
              <dl className="mt-5 space-y-5 text-sm">
                <div>
                  <dt className="font-medium">
                    Observation period · {study.period_label}
                  </dt>
                  <dd className="mt-1 leading-6 text-muted-foreground">
                    The month or quarter being measured. It stays fixed across
                    the comparison.
                  </dd>
                </div>
                <div>
                  <dt className="font-medium">
                    Source vintage · {dateLabel(comparison.date)}
                  </dt>
                  <dd className="mt-1 leading-6 text-muted-foreground">
                    The historical information date requested from FRED. Later
                    revisions are excluded from that snapshot.
                  </dd>
                </div>
                <div>
                  <dt className="font-medium">
                    Retrieval · {dateLabel(comparison.captured_at)}
                  </dt>
                  <dd className="mt-1 leading-6 text-muted-foreground">
                    When this collection was captured. Importing an archive now
                    does not establish a historical forecast or publication.
                  </dd>
                </div>
              </dl>
            </div>
            <div>
              <p className={label}>02 / Reproducible arithmetic</p>
              <h3 className="mt-3 font-serif text-2xl">Rebuild the number.</h3>
              <p className="mt-5 text-sm leading-6">
                {formulas[study.operation]}
              </p>
              <p className="mt-4 text-xs leading-6 text-muted-foreground">
                Source series: {study.series}. Source units: {study.raw_unit}.
                Values are seasonally adjusted. Each growth calculation uses the
                preceding observation from the same snapshot, never from a
                different release.
              </p>
              <div className="mt-5 rounded-md border border-border bg-muted/30 p-4 font-mono text-xs leading-6">
                Revision = comparison − baseline
                <br />
                Threshold test = value &gt; reference
                <br />
                Missing input = unavailable result
              </div>
              <p className="mt-4 text-xs leading-6 text-muted-foreground">
                Charts and downloads calculate from the captured observations.
                Display values are rounded; calculations retain eight decimal
                places. No interpolation, gap filling, forecasts, or generated
                source values are used.
              </p>
            </div>
            <div className="border-t border-border pt-5 md:col-span-2">
              <p className="text-sm leading-6 text-muted-foreground">
                This is a fixed historical collection, not a live data feed.
                Public selections run in your browser and are encoded in the
                share link. They do not create accounts or write to a research
                database. Sources: BEA, BLS, Federal Reserve Board, and FRED /
                ALFRED at the Federal Reserve Bank of St. Louis.
              </p>
            </div>
          </div>
        )}
      </section>
      <p
        role="status"
        aria-live="polite"
        className="mt-3 min-h-5 text-xs text-primary"
      >
        {notice}
      </p>
      <footer className="mt-6 flex flex-col justify-between gap-3 border-t border-border pt-5 text-[11px] leading-5 text-muted-foreground sm:flex-row">
        <p>
          Published evidence collection · Retrieved{" "}
          {dateLabel(atlas.captured_at)}
        </p>
        <p>Historical estimates. Transparent calculations. Original sources.</p>
      </footer>
    </div>
  );
}

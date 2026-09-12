"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import {
  ArrowDownToLine,
  ArrowRight,
  BookOpen,
  Check,
  ChevronRight,
  ExternalLink,
  Fingerprint,
  Link2,
  Play,
  RefreshCw,
  Save,
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { dateLabel, number, saveFile } from "@/lib/public-research";
import {
  canonical,
  decodeRecipe,
  defaultRecipe,
  encodeRecipe,
  parseBundle,
  planQuestion,
  recipeSchema,
  runRecipe,
  verifyBundle,
  type ComparisonRecipe,
  type ComparisonResult,
  type LabBundle,
  type LabSnapshot,
} from "@/lib/release-lab";

const dataBase = (
  process.env.NEXT_PUBLIC_DATA_BASE_URL ||
  "https://wuchris-ch.github.io/global-liquidity-credit-tracker/latest"
).replace(/\/$/, "");
const label =
  "text-[10px] font-semibold uppercase tracking-[0.15em] text-muted-foreground";
const action =
  "inline-flex items-center justify-center gap-2 rounded-md border border-border bg-card px-3 py-2 text-xs font-medium transition-colors hover:bg-muted focus-visible:outline-2 focus-visible:outline-primary disabled:opacity-40";
const field =
  "mt-2 w-full rounded-md border border-border bg-background px-3 py-2.5 text-sm focus-visible:outline-2 focus-visible:outline-primary";
const panel = "rounded-xl border border-border bg-card";
const tabs = [
  ["study", "Revision study"],
  ["releases", "Release monitor"],
  ["notebook", "Research notebook"],
  ["method", "Methods & evidence"],
] as const;
const savedKey = "macro-research:public-recipes:v1";
const month = (value: string) =>
  new Date(value + "T12:00:00Z").toLocaleDateString("en-US", {
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });

function ComparisonChart({
  rows,
  threshold,
  unit,
}: {
  rows: { period: string; initial: number | null; revised: number | null }[];
  threshold: number;
  unit: string;
}) {
  return (
    <div
      className="h-[280px] w-full sm:h-[330px]"
      role="img"
      aria-label={`Initial and revised values in ${unit}. The horizontal line is the ${threshold} reference. Exact values are in the table.`}
    >
      <ResponsiveContainer width="100%" height="100%" minWidth={0}>
        <BarChart
          data={rows}
          margin={{ top: 20, right: 10, left: 0, bottom: 8 }}
          accessibilityLayer
        >
          <CartesianGrid
            stroke="var(--border)"
            vertical={false}
            strokeDasharray="3 4"
          />
          <XAxis
            dataKey="period"
            tickFormatter={(d) =>
              new Date(d + "T12:00:00Z").toLocaleDateString("en-US", {
                month: "short",
                year: "2-digit",
                timeZone: "UTC",
              })
            }
            tick={{ fontSize: 10, fill: "var(--muted-foreground)" }}
            axisLine={false}
            tickLine={false}
            minTickGap={24}
          />
          <YAxis
            width={46}
            tick={{ fontSize: 10, fill: "var(--muted-foreground)" }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            labelFormatter={(v) => month(String(v))}
            formatter={(v, name) => [`${number(Number(v), 1)} ${unit}`, name]}
            contentStyle={{
              background: "var(--card)",
              border: "1px solid var(--border)",
              borderRadius: 6,
              fontSize: 12,
            }}
          />
          <ReferenceLine
            y={threshold}
            stroke="var(--foreground)"
            strokeDasharray="3 4"
          />
          <Bar
            dataKey="initial"
            name="Initial / baseline"
            fill="var(--chart-3)"
            fillOpacity={0.5}
            radius={[2, 2, 0, 0]}
            isAnimationActive={false}
          />
          <Bar
            dataKey="revised"
            name="Revised / comparison"
            fill="var(--chart-2)"
            radius={[2, 2, 0, 0]}
            isAnimationActive={false}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function Capture({
  bundle,
  snapshot,
  title,
}: {
  bundle: LabBundle;
  snapshot: LabSnapshot;
  title: string;
}) {
  return (
    <div className="min-w-0 rounded-lg border border-border p-4">
      <p className={label}>{title}</p>
      <p className="mt-2 font-serif text-xl">
        {dateLabel(snapshot.information_date)}
      </p>
      <p className="mt-1 text-xs text-muted-foreground">
        Source information date · day precision
      </p>
      <details className="mt-4 text-xs">
        <summary className="cursor-pointer font-medium">
          Inspect {snapshot.evidence.length} source responses
        </summary>
        {snapshot.evidence.map((id) => {
          const evidence = bundle.evidence[id];
          return (
            <div key={id} className="mt-3 border-t border-border pt-3">
              <p className="font-medium">
                {evidence.source_url.endsWith("/observations")
                  ? "Observation response"
                  : "Series metadata"}
              </p>
              <p className="mt-1 text-muted-foreground">
                Captured {dateLabel(evidence.captured_at)} ·{" "}
                {evidence.bytes.toLocaleString()} bytes
              </p>
              <p
                className="mt-2 break-all font-mono text-[10px]"
                aria-label="SHA-256"
              >
                {id}
              </p>
              <button
                className={`${action} mt-2`}
                onClick={() =>
                  saveFile(`${id}.json`, evidence.body, "application/json")
                }
              >
                <ArrowDownToLine size={12} /> Raw response
              </button>
              <details className="mt-2">
                <summary className="cursor-pointer text-muted-foreground">
                  Source request
                </summary>
                <pre className="mt-2 overflow-x-auto whitespace-pre-wrap break-all text-[10px]">
                  {evidence.source_url +
                    "\n" +
                    JSON.stringify(evidence.params, null, 2)}
                </pre>
              </details>
            </div>
          );
        })}
      </details>
    </div>
  );
}

function RevisionBridge({
  row,
  unit,
}: {
  row: ComparisonResult["rows"][number];
  unit: string;
}) {
  return (
    <div className="grid gap-3 sm:grid-cols-3">
      {[
        ["Current-period revision", row.current_contribution],
        ["Prior-period contribution", row.previous_contribution],
        ["Change in reported growth", row.revision],
      ].map(([name, value]) => (
        <div key={String(name)} className="rounded-lg bg-muted/45 p-4">
          <p className={label}>{name}</p>
          <p className="mt-2 font-mono text-xl tabular-nums">
            {number(value as number | null, 2, true)}{" "}
            <span className="text-xs text-muted-foreground">{unit}</span>
          </p>
        </div>
      ))}
    </div>
  );
}

export function ReleaseLaboratory({
  studyJson,
  releaseJson,
}: {
  studyJson: string;
  releaseJson: string;
}) {
  const studyBundle = useMemo(
    () => parseBundle(JSON.parse(studyJson)),
    [studyJson],
  );
  const releaseSeed = useMemo(
    () => parseBundle(JSON.parse(releaseJson)),
    [releaseJson],
  );
  const search = useSearchParams();
  const initialTab = tabs.some(([id]) => id === search.get("view"))
    ? search.get("view")!
    : "study";
  const [view, setView] = useState(initialTab);
  const [feed, setFeed] = useState(releaseSeed),
    [feedState, setFeedState] = useState("Checking published releases…");
  const [bundle, setBundle] = useState(studyBundle);
  const [recipe, setRecipe] = useState(() => defaultRecipe(studyBundle));
  const [result, setResult] = useState<ComparisonResult | null>(() =>
    runRecipe(studyBundle, defaultRecipe(studyBundle)),
  );
  const [saved, setSaved] = useState<ComparisonRecipe[]>([]),
    [notice, setNotice] = useState("");
  const [question, setQuestion] = useState(
    "Compare payrolls for 2024-07 first to latest above 100",
  );
  const [threshold, setThreshold] = useState(100),
    [period, setPeriod] = useState("2024-07-01");
  const [verification, setVerification] = useState("");
  const study = studyBundle.study!;
  const studyRows = study.rows;
  const selectedRow = studyRows.find((r) => r.period === period)!;
  const switches = studyRows.filter(
    (r) =>
      r.status === "included" &&
      Number(r.initial) > threshold !== Number(r.revised) > threshold,
  ).length;
  const selectedRecipe: ComparisonRecipe = {
    ...defaultRecipe(studyBundle),
    title: `Payroll revisions: ${month(period)}`,
    before_snapshot: selectedRow.before_snapshot!,
    after_snapshot: selectedRow.after_snapshot!,
    observation_start: period,
    observation_end: period,
    threshold,
  };
  const selectedResult = runRecipe(studyBundle, selectedRecipe);
  const before = bundle.snapshots.find((s) => s.id === recipe.before_snapshot),
    after = bundle.snapshots.find((s) => s.id === recipe.after_snapshot);
  const track = bundle.series.find((s) => s.id === recipe.series_id)!;
  const snapshots = useMemo(
    () =>
      bundle.snapshots
        .filter((s) => s.series_id === recipe.series_id)
        .sort((a, b) => a.information_date.localeCompare(b.information_date)),
    [bundle, recipe.series_id],
  );
  const sharedRecipe = search.get("recipe"),
    sharedBundle = search.get("bundle");

  async function refreshFeed() {
    setFeedState("Checking published releases…");
    try {
      const response = await fetch(`${dataBase}/research/index.json`, {
        cache: "no-store",
        signal: AbortSignal.timeout(12000),
      });
      if (!response.ok) throw new Error("Feed unavailable");
      const current = parseBundle(await response.json());
      await verifyBundle(current);
      setFeed(current);
      setFeedState(`Publication checked · ${dateLabel(current.captured_at)}`);
    } catch {
      setFeedState(
        `Captured collection · ${dateLabel(releaseSeed.captured_at)}. Refresh to check for a newer publication.`,
      );
    }
  }
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const response = await fetch(`${dataBase}/research/index.json`, {
          cache: "no-store",
          signal: AbortSignal.timeout(12000),
        });
        if (!response.ok) throw new Error("Feed unavailable");
        const current = parseBundle(await response.json());
        await verifyBundle(current);
        if (!cancelled) {
          setFeed(current);
          setFeedState(
            `Publication checked · ${dateLabel(current.captured_at)}`,
          );
        }
      } catch {
        if (!cancelled)
          setFeedState(
            `Captured collection · ${dateLabel(releaseSeed.captured_at)}. Refresh to check for a newer publication.`,
          );
      }
    })();
    Promise.resolve().then(() => {
      try {
        const items: unknown = JSON.parse(
          localStorage.getItem(savedKey) || "[]",
        );
        if (Array.isArray(items) && !cancelled)
          setSaved(items.map((i) => recipeSchema.parse(i)).slice(0, 12));
      } catch {
        /* An invalid local entry cannot execute. */
      }
    });
    return () => {
      cancelled = true;
    };
  }, [releaseSeed]);

  async function resolveBundle(id: string) {
    const known = [studyBundle, releaseSeed, feed, bundle].find(
      (b) => b.id === id,
    );
    if (known) return known;
    if (!/^[a-f0-9]{64}$/.test(id))
      throw new Error("Invalid publication identity");
    const response = await fetch(`${dataBase}/research/releases/${id}.json`, {
      signal: AbortSignal.timeout(12000),
    });
    if (!response.ok)
      throw new Error(
        "The pinned publication could not be loaded. Import its replay manifest to open the exact inputs.",
      );
    const found = parseBundle(await response.json());
    if (found.id !== id)
      throw new Error("The returned publication does not match the recipe");
    await verifyBundle(found);
    return found;
  }
  useEffect(() => {
    if (!sharedRecipe) return;
    let cancelled = false;
    (async () => {
      try {
        const next = decodeRecipe(sharedRecipe);
        if (sharedBundle !== next.bundle_id)
          throw new Error("Shared publication and recipe differ");
        const known = [studyBundle, releaseSeed].find(
          (b) => b.id === next.bundle_id,
        );
        let source = known;
        if (!source) {
          const response = await fetch(
            `${dataBase}/research/releases/${next.bundle_id}.json`,
            { signal: AbortSignal.timeout(12000) },
          );
          if (!response.ok)
            throw new Error(
              "Pinned publication is unavailable. Open the downloaded replay manifest to use its exact inputs.",
            );
          source = parseBundle(await response.json());
          await verifyBundle(source);
        }
        const computed = runRecipe(source, next);
        if (!cancelled) {
          setBundle(source);
          setRecipe(next);
          setResult(computed);
          setView("notebook");
          setNotice("Opened the exact shared recipe and publication.");
        }
      } catch (error) {
        if (!cancelled)
          setNotice(
            error instanceof Error ? error.message : "Invalid shared recipe",
          );
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [sharedRecipe, sharedBundle, studyBundle, releaseSeed]);

  function openRecipe(source: LabBundle, next: ComparisonRecipe) {
    setBundle(source);
    setRecipe(next);
    setResult(runRecipe(source, next));
    setVerification("");
    setNotice("");
    setView("notebook");
    document
      .getElementById("laboratory-views")
      ?.scrollIntoView({ block: "start" });
  }
  function editRecipe(next: ComparisonRecipe) {
    setRecipe(next);
    setResult(null);
    setNotice("");
  }
  function execute() {
    try {
      setResult(runRecipe(bundle, recipe));
      setNotice(
        "Comparison complete. Every input is linked to its archived response.",
      );
    } catch (error) {
      setResult(null);
      setNotice(
        error instanceof Error ? error.message : "Recipe could not run",
      );
    }
  }
  async function saveRecipe() {
    try {
      const next = [
        recipeSchema.parse(recipe),
        ...saved.filter((r) => canonical(r) !== canonical(recipe)),
      ].slice(0, 12);
      localStorage.setItem(savedKey, JSON.stringify(next));
      setSaved(next);
      setNotice(
        "Saved in this browser. Share or export the recipe to keep a portable copy.",
      );
    } catch {
      setNotice(
        "Browser storage is unavailable. Download a replay manifest to save this recipe.",
      );
    }
  }
  async function shareRecipe() {
    const url = new URL(window.location.href);
    url.search = new URLSearchParams({
      view: "notebook",
      bundle: bundle.id,
      recipe: encodeRecipe(recipe),
    }).toString();
    window.history.replaceState(null, "", url);
    try {
      await navigator.clipboard.writeText(url.toString());
      setNotice("Link copied with this recipe and its pinned publication.");
    } catch {
      setNotice("The shareable link is ready in the address bar.");
    }
  }
  function exportReplay() {
    if (result)
      saveFile(
        "research-replay.json",
        JSON.stringify(
          { schema_version: "research-replay/1", bundle, recipe, result },
          null,
          2,
        ),
        "application/json",
      );
  }
  async function importReplay(file: File) {
    try {
      if (file.size > 5000000)
        throw new Error("Replay files are limited to 5 MB");
      const replay = JSON.parse(await file.text());
      if (replay.schema_version !== "research-replay/1")
        throw new Error("Choose a research replay manifest");
      const source = parseBundle(replay.bundle);
      await verifyBundle(source);
      const typed = recipeSchema.parse(replay.recipe);
      const computed = runRecipe(source, typed);
      if (canonical(computed) !== canonical(replay.result))
        throw new Error(
          "Recorded results differ from independent browser replay",
        );
      openRecipe(source, typed);
      setNotice(
        "Replay verified. Source hashes, inputs and recomputed results agree.",
      );
    } catch (error) {
      setNotice(
        error instanceof Error ? error.message : "Replay could not be verified",
      );
    }
  }
  async function verify(source: LabBundle) {
    setVerification("Checking source hashes and rows…");
    try {
      const count = await verifyBundle(source);
      setVerification(
        `${count} response hashes verified; all snapshot rows match their source responses.`,
      );
    } catch (error) {
      setVerification(
        error instanceof Error ? error.message : "Verification failed",
      );
    }
  }
  function downloadStudyTable() {
    const header =
      "period,initial_information_date,comparison_information_date,initial_thousand_jobs,revised_thousand_jobs,revision_thousand_jobs,reference_thousand_jobs,classification_changed,status";
    saveFile(
      "payroll-revisions-2023-2024.csv",
      [
        header,
        ...studyRows.map((r) =>
          [
            r.period,
            r.initial_date || "",
            r.revised_date || "",
            r.initial || "",
            r.revised || "",
            r.revision || "",
            threshold,
            r.status === "included"
              ? Number(r.initial) > threshold !== Number(r.revised) > threshold
              : "",
            r.status,
          ].join(","),
        ),
      ].join("\n") + "\n",
      "text/csv",
    );
  }

  return (
    <div className="mx-auto max-w-6xl px-4 pb-20 pt-9 sm:px-8 sm:pt-12">
      <header className="border-b border-foreground/20 pb-7">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <p className={label}>
            Macro research <span className="mx-2 text-border">/</span> Release
            laboratory
          </p>
          <Link
            href="/research/atlas"
            className="inline-flex items-center gap-2 text-xs text-muted-foreground hover:text-foreground"
          >
            Explore the atlas <ArrowRight size={13} />
          </Link>
        </div>
        <h1 className="mt-5 max-w-3xl font-serif text-[2.7rem] leading-[1.06] tracking-tight sm:text-6xl">
          Read the release.
          <br />
          <span className="text-muted-foreground">Revisit the conclusion.</span>
        </h1>
        <p className="mt-5 max-w-xl text-sm leading-6 text-muted-foreground">
          Follow economic releases into the archive. Compare the evidence
          available at different dates, test a reference level, and keep a
          research result you can replay.
        </p>
        <div className="mt-7 flex flex-wrap gap-6 text-xs">
          <span>
            <strong className="font-mono text-lg">24</strong> months studied
          </span>
          <span>
            <strong className="font-mono text-lg">03</strong> release tracks
          </span>
          <span className="inline-flex items-center gap-2">
            <Fingerprint size={15} /> Verifiable source captures
          </span>
        </div>
      </header>
      <nav
        id="laboratory-views"
        className="my-6 flex gap-1 overflow-x-auto border-b border-border"
        aria-label="Laboratory views"
      >
        {tabs.map(([id, title]) => (
          <button
            key={id}
            onClick={() => {
              setView(id);
              setVerification("");
            }}
            aria-current={view === id ? "page" : undefined}
            className={`shrink-0 border-b-2 px-3 py-3 text-xs font-medium focus-visible:outline-2 focus-visible:outline-primary ${view === id ? "border-foreground text-foreground" : "border-transparent text-muted-foreground hover:text-foreground"}`}
          >
            {title}
          </button>
        ))}
      </nav>
      {notice && (
        <p
          role="status"
          className="mb-5 rounded-lg border border-border bg-muted/40 p-3 text-xs leading-5"
        >
          {notice}
        </p>
      )}

      {view === "study" && (
        <div className="space-y-6">
          <section className="grid gap-6 lg:grid-cols-[1.5fr_1fr]">
            <div>
              <p className={label}>Study 01 · US labour market</p>
              <h2 className="mt-3 font-serif text-3xl sm:text-4xl">
                Two years of payrolls,
                <br />
                through the revision cycle.
              </h2>
              <p className="mt-4 max-w-lg text-sm leading-6 text-muted-foreground">
                Every month in 2023 and 2024, from its first archived estimate
                to the same history as of {dateLabel(studyBundle.as_of)}. Later
                benchmark and seasonal updates are included.
              </p>
              <div className="mt-5 flex flex-wrap gap-2">
                <button className={action} onClick={downloadStudyTable}>
                  <ArrowDownToLine size={13} /> Export table
                </button>
                <button
                  className={action}
                  onClick={() =>
                    saveFile(
                      "payroll-revision-study.json",
                      JSON.stringify(studyBundle),
                      "application/json",
                    )
                  }
                >
                  <BookOpen size={13} /> Study & source data
                </button>
              </div>
            </div>
            <div className={`${panel} p-6`}>
              <p className={label}>Mean revision to monthly job growth</p>
              <p className="mt-4 font-mono text-5xl tracking-tight">
                {number(study.summary.mean_revision, 1, true)}
                <span className="ml-2 font-sans text-sm text-muted-foreground">
                  thousand jobs
                </span>
              </p>
              <p className="mt-4 text-xs leading-5 text-muted-foreground">
                Initial mean: {number(study.summary.initial_mean, 1)}k. Revised
                mean: {number(study.summary.revised_mean, 1)}k.{" "}
                {study.summary.downward_revisions} of {study.summary.n} monthly
                estimates were revised down.
              </p>
              <p className="mt-4 border-t border-border pt-3 text-[11px] leading-5 text-muted-foreground">
                95% block-resampling interval:{" "}
                {number(study.uncertainty.intervals[0].mean_revision[0], 1)} to{" "}
                {number(study.uncertainty.intervals[0].mean_revision[1], 1)}k,
                using 3-month blocks. This measures stability within the sample.
              </p>
            </div>
          </section>
          <section
            className={`${panel} overflow-hidden`}
            aria-label="Payroll revision comparison"
          >
            <div className="grid gap-5 border-b border-border p-5 sm:grid-cols-[1fr_280px] sm:p-6">
              <div>
                <p className={label}>An adjustable economic reference</p>
                <h3 className="mt-2 font-serif text-2xl">
                  {switches} of 24 readings change sides.
                </h3>
                <p className="mt-2 text-xs leading-5 text-muted-foreground">
                  Compare monthly job creation with a reference of {threshold}{" "}
                  thousand jobs. A reading must be strictly above the line to
                  clear it.
                </p>
              </div>
              <label className="block text-xs font-medium">
                Reference level{" "}
                <span className="float-right font-mono">{threshold}k jobs</span>
                <input
                  aria-label="Study reference level"
                  type="range"
                  min="0"
                  max="400"
                  step="10"
                  value={threshold}
                  onChange={(e) => setThreshold(Number(e.target.value))}
                  className="mt-5 w-full accent-foreground"
                />
                <span className="mt-1 flex justify-between text-[10px] text-muted-foreground">
                  <span>0</span>
                  <span>400k</span>
                </span>
              </label>
            </div>
            <div className="px-2 pt-5 sm:px-5">
              <div className="mb-2 flex flex-wrap gap-5 px-3 text-[11px]">
                <span className="flex items-center gap-2">
                  <i className="h-2 w-3 bg-[var(--chart-3)] opacity-50" />{" "}
                  Initial estimate
                </span>
                <span className="flex items-center gap-2">
                  <i className="h-2 w-3 bg-[var(--chart-2)]" /> Revised at{" "}
                  {dateLabel(studyBundle.as_of)}
                </span>
              </div>
              <ComparisonChart
                rows={studyRows.map((r) => ({
                  period: r.period,
                  initial: r.initial === undefined ? null : Number(r.initial),
                  revised: r.revised === undefined ? null : Number(r.revised),
                }))}
                threshold={threshold}
                unit="thousand jobs"
              />
            </div>
            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border px-5 py-4 text-xs">
              <span className="text-muted-foreground">
                All {study.summary.planned} planned months ·{" "}
                {study.summary.excluded} excluded
              </span>
              <button
                className="inline-flex items-center gap-1 font-medium"
                onClick={() => setView("method")}
              >
                Threshold outcomes & uncertainty <ChevronRight size={13} />
              </button>
            </div>
          </section>
          <section
            className={`${panel} p-5 sm:p-6`}
            aria-label="Inspect a study month"
          >
            <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
              <div>
                <p className={label}>Trace the changed inputs</p>
                <h3 className="mt-2 font-serif text-2xl">
                  {month(period)}: {number(Number(selectedRow.initial), 0)}k
                  becomes {number(Number(selectedRow.revised), 0)}k.
                </h3>
              </div>
              <label className="text-xs font-medium">
                Observation month
                <select
                  aria-label="Inspect study month"
                  className={field}
                  value={period}
                  onChange={(e) => setPeriod(e.target.value)}
                >
                  {studyRows.map((r) => (
                    <option key={r.period} value={r.period}>
                      {month(r.period)}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <p className="my-4 text-xs leading-5 text-muted-foreground">
              Monthly job growth subtracts the preceding month&apos;s level.
              Revisions to both inputs matter; these two contributions reconcile
              to the change in growth.
            </p>
            <RevisionBridge row={selectedResult.rows[0]} unit="k jobs" />
            <div className="mt-5 grid gap-3 sm:grid-cols-2">
              <Capture
                bundle={studyBundle}
                snapshot={
                  studyBundle.snapshots.find(
                    (s) => s.id === selectedRow.before_snapshot,
                  )!
                }
                title="Initial information date"
              />
              <Capture
                bundle={studyBundle}
                snapshot={
                  studyBundle.snapshots.find(
                    (s) => s.id === selectedRow.after_snapshot,
                  )!
                }
                title="Revised information date"
              />
            </div>
            <div className="mt-5 flex flex-wrap gap-2">
              <button
                className={`${action} border-foreground/30`}
                onClick={() => openRecipe(studyBundle, selectedRecipe)}
              >
                Open as a research recipe <ArrowRight size={13} />
              </button>
              <button className={action} onClick={() => verify(studyBundle)}>
                <Fingerprint size={13} /> Verify source hashes
              </button>
            </div>
          </section>
          <details className={`${panel} p-5`}>
            <summary className="cursor-pointer text-sm font-medium">
              Every planned observation
            </summary>
            <div className="mt-4 overflow-x-auto">
              <table className="w-full text-left text-xs">
                <caption className="mb-3 text-left text-muted-foreground">
                  Monthly payroll change, thousand jobs. Revised at{" "}
                  {dateLabel(studyBundle.as_of)}. Reference: {threshold}k.
                </caption>
                <thead>
                  <tr className="border-b border-border">
                    {[
                      "Period",
                      "First release",
                      "Initial",
                      "Revised",
                      "Revision",
                      "Reference",
                    ].map((v) => (
                      <th key={v} className="whitespace-nowrap p-2 font-medium">
                        {v}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {studyRows.map((r) => (
                    <tr key={r.period} className="border-b border-border/50">
                      <td className="p-2">
                        <button
                          className="whitespace-nowrap underline underline-offset-4"
                          onClick={() => setPeriod(r.period)}
                        >
                          {month(r.period)}
                        </button>
                      </td>
                      <td className="whitespace-nowrap p-2 text-muted-foreground">
                        {r.initial_date}
                      </td>
                      <td className="p-2 font-mono">{r.initial}</td>
                      <td className="p-2 font-mono">{r.revised}</td>
                      <td className="p-2 font-mono">
                        {number(Number(r.revision), 0, true)}
                      </td>
                      <td className="p-2">
                        {Number(r.initial) > threshold !==
                        Number(r.revised) > threshold
                          ? "Changed"
                          : "Same side"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        </div>
      )}

      {view === "releases" && (
        <div className="space-y-6">
          <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
            <div>
              <p className={label}>Release-aware publication</p>
              <h2 className="mt-2 font-serif text-3xl">
                From calendar to verified evidence.
              </h2>
              <p className="mt-3 max-w-xl text-sm leading-6 text-muted-foreground">
                Three release tracks, checked every 12 hours. Scheduled dates
                and archived availability are recorded separately. A complete
                snapshot remains available while a new capture is being checked.
              </p>
            </div>
            <button className={action} onClick={refreshFeed}>
              <RefreshCw size={13} /> Refresh feed
            </button>
          </div>
          <p role="status" className="text-xs text-muted-foreground">
            {feedState}
          </p>
          <div className="grid gap-3 md:grid-cols-3">
            {feed.series.map((series) => {
              const captures = feed.snapshots
                .filter((s) => s.series_id === series.id)
                .sort((a, b) =>
                  a.information_date.localeCompare(b.information_date),
                );
              const latest = captures.at(-1)!;
              const next = feed.inbox
                .filter(
                  (i) => i.series_id === series.id && i.status === "scheduled",
                )
                .sort((a, b) => a.date.localeCompare(b.date))[0];
              return (
                <article key={series.id} className={`${panel} p-5`}>
                  <p className={label}>{series.id}</p>
                  <h3 className="mt-3 font-serif text-2xl">{series.name}</h3>
                  <p className="mt-2 text-[11px] leading-5 text-muted-foreground">
                    {series.agency}
                  </p>
                  <dl className="mt-5 space-y-3 text-xs">
                    <div>
                      <dt className="text-muted-foreground">
                        Latest verified vintage
                      </dt>
                      <dd className="mt-1 font-mono">
                        {dateLabel(latest.information_date)}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-muted-foreground">
                        Last observation
                      </dt>
                      <dd className="mt-1">{month(latest.observation_end)}</dd>
                    </div>
                    <div>
                      <dt className="text-muted-foreground">
                        Next calendar date
                      </dt>
                      <dd className="mt-1">
                        {next ? dateLabel(next.date) : "No future date listed"}
                      </dd>
                    </div>
                  </dl>
                  <button
                    className={`${action} mt-5 w-full`}
                    onClick={() =>
                      openRecipe(feed, defaultRecipe(feed, series.id))
                    }
                  >
                    Compare releases <ArrowRight size={13} />
                  </button>
                </article>
              );
            })}
          </div>
          <section className={`${panel} p-5 sm:p-6`} aria-label="Release inbox">
            <p className={label}>Release inbox</p>
            <h3 className="mt-2 font-serif text-2xl">
              What arrived. What is still expected.
            </h3>
            <div className="mt-5 divide-y divide-border">
              {[...feed.inbox]
                .sort((a, b) => b.date.localeCompare(a.date))
                .map((item, index) => (
                  <details
                    key={`${item.series_id}-${item.date}-${index}`}
                    className="py-3"
                  >
                    <summary className="flex cursor-pointer list-none flex-wrap items-center gap-x-4 gap-y-2 text-xs">
                      <span className="w-24 font-mono text-muted-foreground">
                        {item.date}
                      </span>
                      <span className="min-w-40 flex-1 font-medium">
                        {feed.series.find((s) => s.id === item.series_id)?.name}
                      </span>
                      <span
                        className={`rounded-full border px-2 py-1 text-[10px] ${["verified", "revision"].includes(item.status) ? "border-foreground/20 bg-muted" : "border-border text-muted-foreground"}`}
                      >
                        {(
                          {
                            verified: "Verified",
                            revision: "Additional revision",
                            queued: "Capture queued",
                            scheduled: "Scheduled",
                            awaiting_vintage: "No changed vintage",
                            verification_held: "Verification held",
                            discovery_held: "Source check held",
                          } as Record<string, string>
                        )[item.status] || item.status}
                      </span>
                      <ChevronRight size={13} />
                    </summary>
                    <p className="mt-3 max-w-2xl text-xs leading-5 text-muted-foreground">
                      {item.detail}
                    </p>
                    <p className="mt-2 text-[10px] text-muted-foreground">
                      Inventory checked{" "}
                      {item.checked_at
                        ? dateLabel(item.checked_at)
                        : "on collection"}
                    </p>
                    {item.evidence?.map((id) => (
                      <button
                        key={id}
                        className={`${action} mr-2 mt-3`}
                        onClick={() =>
                          saveFile(
                            `${id}.json`,
                            feed.evidence[id].body,
                            "application/json",
                          )
                        }
                      >
                        <ArrowDownToLine size={12} />{" "}
                        {feed.evidence[id].source_url.endsWith("/vintagedates")
                          ? "Archive dates"
                          : feed.evidence[id].source_url.endsWith("/dates")
                            ? "Calendar response"
                            : "Release association"}
                      </button>
                    ))}
                  </details>
                ))}
            </div>
          </section>
        </div>
      )}

      {view === "notebook" && (
        <div className="space-y-5">
          <div>
            <p className={label}>Saved, shared and independently replayable</p>
            <h2 className="mt-2 font-serif text-3xl">
              A research question, with its inputs attached.
            </h2>
          </div>
          <section className={`${panel} p-5`} aria-label="Research planner">
            <label className="text-xs font-medium" htmlFor="research-question">
              Describe a comparison
            </label>
            <div className="mt-2 flex flex-col gap-2 sm:flex-row">
              <input
                id="research-question"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                maxLength={400}
                className={`${field} mt-0 flex-1`}
              />
              <button
                className={action}
                onClick={() => {
                  const planned = planQuestion(bundle, question);
                  if (planned.status === "planned") {
                    editRecipe(planned.recipe);
                    setNotice(
                      "Recipe prepared. Inspect its dates and inputs, then run the comparison.",
                    );
                  } else setNotice(planned.reason);
                }}
              >
                Preview recipe <ArrowRight size={13} />
              </button>
            </div>
            <p className="mt-3 text-[11px] leading-5 text-muted-foreground">
              Use payrolls, production or GDP with a month, then “first to
              latest” or two exact archived dates. The planner selects a typed
              recipe; the calculation engine produces the numbers.
            </p>
          </section>
          {saved.length > 0 && (
            <div className="flex flex-wrap items-center gap-2">
              <span className={label}>Saved in this browser</span>
              {saved.map((item, i) => (
                <button
                  key={i}
                  className={`${action} max-w-60 truncate`}
                  onClick={async () => {
                    try {
                      openRecipe(await resolveBundle(item.bundle_id), item);
                    } catch (error) {
                      setNotice(
                        error instanceof Error
                          ? error.message
                          : "Saved publication unavailable",
                      );
                    }
                  }}
                >
                  <BookOpen size={12} />
                  {item.title}
                </button>
              ))}
            </div>
          )}
          <section
            className={`${panel} p-5 sm:p-6`}
            aria-label="Typed research recipe"
          >
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <label className="text-xs font-medium">
                Collection
                <select
                  className={field}
                  value={bundle.kind}
                  onChange={(e) => {
                    const next =
                      e.target.value === "revision-study" ? studyBundle : feed;
                    openRecipe(next, defaultRecipe(next));
                  }}
                >
                  <option value="revision-study">Payroll revision study</option>
                  <option value="releases">Published release collection</option>
                </select>
              </label>
              <label className="text-xs font-medium">
                Series
                <select
                  className={field}
                  value={recipe.series_id}
                  onChange={(e) =>
                    editRecipe(defaultRecipe(bundle, e.target.value))
                  }
                >
                  {bundle.series.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name}
                    </option>
                  ))}
                </select>
              </label>
              <label className="text-xs font-medium">
                Recipe name
                <input
                  className={field}
                  value={recipe.title}
                  maxLength={120}
                  onChange={(e) =>
                    editRecipe({ ...recipe, title: e.target.value })
                  }
                />
              </label>
              <label className="text-xs font-medium">
                Baseline information date
                <select
                  className={field}
                  value={recipe.before_snapshot}
                  onChange={(e) =>
                    editRecipe({ ...recipe, before_snapshot: e.target.value })
                  }
                >
                  {snapshots.map((s) => (
                    <option key={s.id} value={s.id}>
                      {dateLabel(s.information_date)}
                    </option>
                  ))}
                </select>
              </label>
              <label className="text-xs font-medium">
                Comparison information date
                <select
                  className={field}
                  value={recipe.after_snapshot}
                  onChange={(e) =>
                    editRecipe({ ...recipe, after_snapshot: e.target.value })
                  }
                >
                  {snapshots.map((s) => (
                    <option key={s.id} value={s.id}>
                      {dateLabel(s.information_date)}
                    </option>
                  ))}
                </select>
              </label>
              <label className="text-xs font-medium">
                Reference ({track.result_unit})
                <input
                  type="number"
                  min="-10000"
                  max="10000"
                  step="any"
                  className={field}
                  value={
                    Number.isFinite(recipe.threshold) ? recipe.threshold : ""
                  }
                  onChange={(e) =>
                    editRecipe({
                      ...recipe,
                      threshold:
                        e.target.value === "" ? NaN : Number(e.target.value),
                    })
                  }
                />
              </label>
              <label className="text-xs font-medium">
                First observation period
                <input
                  type="month"
                  className={field}
                  value={recipe.observation_start.slice(0, 7)}
                  onChange={(e) =>
                    editRecipe({
                      ...recipe,
                      observation_start: e.target.value + "-01",
                    })
                  }
                />
              </label>
              <label className="text-xs font-medium">
                Last observation period
                <input
                  type="month"
                  className={field}
                  value={recipe.observation_end.slice(0, 7)}
                  onChange={(e) =>
                    editRecipe({
                      ...recipe,
                      observation_end: e.target.value + "-01",
                    })
                  }
                />
              </label>
              <div className="self-end pb-2 text-[11px] leading-5 text-muted-foreground">
                Measure:{" "}
                {recipe.operation === "difference"
                  ? "Monthly change in payroll levels"
                  : recipe.operation === "pct_change"
                    ? "Monthly percentage change in the index"
                    : "Published annualized quarterly growth"}
                . Both inputs retain their own information date.
              </div>
            </div>
            <div className="mt-5 flex flex-wrap gap-2">
              <button
                className={`${action} border-foreground bg-foreground text-background hover:bg-foreground/90`}
                onClick={execute}
              >
                <Play size={13} /> Run recipe
              </button>
              <button
                disabled={!result}
                className={action}
                onClick={saveRecipe}
              >
                <Save size={13} /> Save
              </button>
              <button
                disabled={!result}
                className={action}
                onClick={shareRecipe}
              >
                <Link2 size={13} /> Share
              </button>
              <button
                disabled={!result}
                className={action}
                onClick={exportReplay}
              >
                <ArrowDownToLine size={13} /> Replay manifest
              </button>
              <label className={`${action} cursor-pointer`}>
                Import replay
                <input
                  type="file"
                  accept="application/json,.json"
                  className="sr-only"
                  onChange={(e) => {
                    if (e.target.files?.[0])
                      void importReplay(e.target.files[0]);
                    e.target.value = "";
                  }}
                />
              </label>
            </div>
            <details className="mt-5 rounded-lg bg-muted/30 p-3">
              <summary className="cursor-pointer text-xs font-medium">
                Inspect the typed recipe
              </summary>
              <pre className="mt-3 overflow-x-auto text-[10px] leading-5">
                {JSON.stringify(recipe, null, 2)}
              </pre>
            </details>
          </section>
          {result ? (
            <section
              className={`${panel} p-5 sm:p-6`}
              aria-label="Recipe results"
            >
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <p className={label}>Computed from pinned source snapshots</p>
                  <h3 className="mt-2 font-serif text-2xl">
                    {result.rows.length === 1
                      ? `${month(result.rows[0].period)}: ${number(result.rows[0].initial, track.decimals)} → ${number(result.rows[0].revised, track.decimals)}`
                      : `${result.rows.length} matched calendar periods`}
                  </h3>
                  <p className="mt-2 text-xs text-muted-foreground">
                    {result.unit} · {dateLabel(result.before_date)} compared
                    with {dateLabel(result.after_date)}
                  </p>
                </div>
                <span className="inline-flex items-center gap-1 rounded-full bg-muted px-3 py-1.5 text-[10px]">
                  <Check size={12} /> Deterministic calculation
                </span>
              </div>
              {result.rows.length > 1 && (
                <div className="mt-5">
                  <ComparisonChart
                    rows={result.rows}
                    threshold={recipe.threshold}
                    unit={result.unit}
                  />
                </div>
              )}
              {result.rows.length === 1 && (
                <div className="mt-5">
                  <RevisionBridge row={result.rows[0]} unit={result.unit} />
                  <p className="mt-3 text-xs leading-5 text-muted-foreground">
                    {result.rows[0].reason ||
                      `${result.rows[0].switched ? "The classification changes" : "Both readings remain on the same side"} at a reference of ${recipe.threshold} ${result.unit}.`}{" "}
                    {result.attribution_method}
                  </p>
                </div>
              )}
              <div className="mt-5 overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <caption className="mb-2 text-left text-muted-foreground">
                    Exact results and source citations
                  </caption>
                  <thead>
                    <tr className="border-b border-border">
                      {[
                        "Period",
                        "Baseline",
                        "Comparison",
                        "Revision",
                        "Reference",
                        "Source inputs",
                      ].map((v) => (
                        <th className="p-2 font-medium" key={v}>
                          {v}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {result.rows.map((row) => (
                      <tr
                        key={row.period}
                        className="border-b border-border/50"
                      >
                        <td className="whitespace-nowrap p-2">
                          {month(row.period)}
                        </td>
                        <td className="p-2 font-mono">
                          {number(row.initial, track.decimals)}
                        </td>
                        <td className="p-2 font-mono">
                          {number(row.revised, track.decimals)}
                        </td>
                        <td className="p-2 font-mono">
                          {number(row.revision, track.decimals, true)}
                        </td>
                        <td className="p-2">
                          {row.switched === null
                            ? "Unavailable"
                            : row.switched
                              ? "Changed"
                              : "Same side"}
                        </td>
                        <td className="min-w-44 p-2">
                          <details>
                            <summary className="cursor-pointer">
                              {row.citations.length} exact inputs
                            </summary>
                            {row.citations.map((c, i) => (
                              <p
                                key={i}
                                className="mt-2 break-all text-[10px] leading-4"
                              >
                                {c.observation_date}: <strong>{c.value}</strong>
                                <br />
                                Vintage {c.information_date}
                                <br />
                                <span className="font-mono">
                                  SHA-256 {c.capture}
                                </span>
                              </p>
                            ))}
                          </details>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <ol className="mt-6 grid gap-3 text-[11px] leading-5 text-muted-foreground sm:grid-cols-3">
                {result.steps.map((s, i) => (
                  <li key={s}>
                    <span className="mr-2 font-mono text-foreground">
                      0{i + 1}
                    </span>
                    {s}
                  </li>
                ))}
              </ol>
              <div className="mt-5 grid gap-3 sm:grid-cols-2">
                {before && (
                  <Capture
                    bundle={bundle}
                    snapshot={before}
                    title="Baseline evidence"
                  />
                )}
                {after && (
                  <Capture
                    bundle={bundle}
                    snapshot={after}
                    title="Comparison evidence"
                  />
                )}
              </div>
              <button
                className={`${action} mt-4`}
                onClick={() => verify(bundle)}
              >
                <Fingerprint size={13} /> Verify publication and source hashes
              </button>
            </section>
          ) : (
            <p
              role="status"
              className="rounded-lg border border-dashed border-border p-6 text-center text-sm text-muted-foreground"
            >
              Inspect the recipe, then run it to compute the comparison.
            </p>
          )}
        </div>
      )}

      {view === "method" && (
        <div className="space-y-6">
          <section className={`${panel} p-6`}>
            <p className={label}>Study specification</p>
            <h2 className="mt-2 font-serif text-3xl">
              A fixed cohort. Every outcome.
            </h2>
            <p className="mt-4 max-w-3xl text-sm leading-6 text-muted-foreground">
              {study.plan.population}. {study.plan.interpretation}
            </p>
            <ol className="mt-5 space-y-3 text-xs leading-5">
              {study.methods.map((step, i) => (
                <li key={step} className="flex gap-3">
                  <span className="font-mono text-muted-foreground">
                    0{i + 1}
                  </span>
                  {step}
                </li>
              ))}
            </ol>
            <p className="mt-5 border-t border-border pt-4 text-[11px] leading-5 text-muted-foreground">
              {study.plan.plan_stage}. Source information dates describe the
              archive. Platform captures were collected on{" "}
              {dateLabel(studyBundle.captured_at)}.
            </p>
          </section>
          <section className={`${panel} p-6`}>
            <h3 className="font-serif text-2xl">
              Sensitivity to the reference level
            </h3>
            <div className="mt-4 overflow-x-auto">
              <table className="w-full text-left text-xs">
                <caption className="mb-3 text-left text-muted-foreground">
                  All 24 months, references fixed before outcome calculation.
                  Strictly above, in thousand jobs.
                </caption>
                <thead>
                  <tr className="border-b border-border">
                    {[
                      "Reference",
                      "Initially above",
                      "Revised above",
                      "Changed sides",
                      "Above to below/equal",
                      "Below/equal to above",
                    ].map((v) => (
                      <th className="p-2 font-medium" key={v}>
                        {v}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {study.summary.thresholds.map((r) => (
                    <tr className="border-b border-border/50" key={r.threshold}>
                      {[
                        r.threshold,
                        r.initial_above,
                        r.revised_above,
                        r.switches,
                        r.from_above,
                        r.to_above,
                      ].map((n, i) => (
                        <td className="p-3 font-mono" key={i}>
                          {n}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="mt-5 grid gap-3 sm:grid-cols-4">
              {[
                ["Median revision", study.summary.median_revision],
                [
                  "Mean absolute revision",
                  study.summary.mean_absolute_revision,
                ],
                [
                  "Largest absolute revision",
                  study.summary.largest_absolute_revision,
                ],
                ["Unchanged months", study.summary.unchanged],
              ].map(([title, value]) => (
                <div key={String(title)} className="rounded-lg bg-muted/40 p-3">
                  <p className={`${label} leading-4`}>{title}</p>
                  <p className="mt-2 font-mono text-xl">
                    {number(
                      Number(value),
                      title === "Unchanged months" ? 0 : 1,
                    )}
                    {title !== "Unchanged months" && (
                      <span className="ml-1 text-xs text-muted-foreground">
                        k jobs
                      </span>
                    )}
                  </p>
                </div>
              ))}
            </div>
          </section>
          <section className={`${panel} p-6`}>
            <h3 className="font-serif text-2xl">
              Uncertainty and time dependence
            </h3>
            <p className="mt-3 max-w-3xl text-xs leading-6 text-muted-foreground">
              {study.uncertainty.interpretation} We use{" "}
              {study.uncertainty.replicates.toLocaleString()} circular
              moving-block resamples for each block length and a fixed seed.
            </p>
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              {study.uncertainty.intervals.map((r) => (
                <div
                  className="rounded-lg border border-border p-4"
                  key={r.block_months}
                >
                  <p className={label}>
                    {r.block_months}-month blocks · 95% interval
                  </p>
                  <p className="mt-3 text-sm">
                    Mean revision:{" "}
                    <span className="font-mono">
                      {number(r.mean_revision[0], 1)} to{" "}
                      {number(r.mean_revision[1], 1)}k
                    </span>
                  </p>
                  <p className="mt-2 text-xs text-muted-foreground">
                    Mean absolute revision:{" "}
                    {number(r.mean_absolute_revision[0], 1)} to{" "}
                    {number(r.mean_absolute_revision[1], 1)}k
                  </p>
                  {r.switch_share.map((s) => (
                    <p
                      key={s.threshold}
                      className="mt-2 text-xs text-muted-foreground"
                    >
                      Share changing sides at {s.threshold}k:{" "}
                      {number(s.interval[0] * 100, 1)}% to{" "}
                      {number(s.interval[1] * 100, 1)}%
                    </p>
                  ))}
                </div>
              ))}
            </div>
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              {study.by_year.map((y) => (
                <p
                  key={y.year}
                  className="rounded-lg bg-muted/40 p-4 text-xs leading-6"
                >
                  <strong>{y.year}</strong> · {y.n} months
                  <br />
                  Mean revision {number(y.mean_revision, 1, true)}k; mean
                  absolute revision {number(y.mean_absolute_revision, 1)}k.
                </p>
              ))}
            </div>
          </section>
          <section className={`${panel} p-6`}>
            <h3 className="font-serif text-2xl">
              Sources and independent replay
            </h3>
            <div className="mt-4 grid gap-4 sm:grid-cols-2">
              {releaseSeed.series.map((s) => (
                <div key={s.id} className="text-xs leading-6">
                  <a
                    href={s.source_url}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 font-medium underline underline-offset-4"
                  >
                    {s.agency} <ExternalLink size={11} />
                  </a>
                  <p className="text-muted-foreground">
                    {s.name} · {s.unit} · {s.adjustment}
                  </p>
                  <a
                    href={s.license_url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-muted-foreground underline underline-offset-4"
                  >
                    Source use policy
                  </a>
                </div>
              ))}
            </div>
            <div className="mt-5 flex flex-wrap gap-2">
              {study.sources.map((url, i) => (
                <a
                  key={url}
                  href={url}
                  target="_blank"
                  rel="noreferrer"
                  className={action}
                >
                  {
                    [
                      "FRED archive API",
                      "BLS revision history",
                      "BLS estimation method",
                    ][i]
                  }{" "}
                  <ExternalLink size={11} />
                </a>
              ))}
            </div>
            <p className="mt-5 text-xs leading-6 text-muted-foreground">
              Download a replay manifest from any notebook result. The
              standalone Python verifier checks the publication and raw response
              hashes, reads the original observations, and recalculates the
              comparison. It runs offline with the Python standard library.
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              <a href="/research/lab/replay.py" download className={action}>
                <ArrowDownToLine size={13} /> Standalone verifier
              </a>
              <button
                className={action}
                onClick={() =>
                  saveFile(
                    "payroll-study-plan.json",
                    JSON.stringify(study.plan, null, 2),
                    "application/json",
                  )
                }
              >
                <ArrowDownToLine size={13} /> Study specification
              </button>
            </div>
            <pre className="mt-4 overflow-x-auto rounded-lg bg-muted/40 p-3 text-[11px]">
              python3 replay.py research-replay.json
            </pre>
          </section>
        </div>
      )}
      {verification && (
        <p
          role="status"
          className="mt-5 flex items-start gap-2 rounded-lg border border-border bg-muted/40 p-4 text-xs leading-5"
        >
          <Fingerprint size={14} className="mt-0.5 shrink-0" />
          {verification}
        </p>
      )}
      <footer className="mt-10 border-t border-border pt-5 text-[10px] leading-5 text-muted-foreground">
        US economic statistics via FRED / ALFRED. Source information dates,
        observation periods and platform capture dates are kept distinct. Public
        research runs in your browser against immutable published data.
      </footer>
    </div>
  );
}

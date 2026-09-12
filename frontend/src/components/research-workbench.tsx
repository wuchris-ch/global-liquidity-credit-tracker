"use client";
import { useCallback, useEffect, useState } from "react";
import { z } from "zod";
import { ResearchSources } from "@/components/research-sources";
import { unitLabel } from "@/lib/research";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  CartesianGrid,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
} from "recharts";
import {
  request,
  download,
  defaultBase,
  seriesSchema,
  runSchema,
  type Series,
  type Run,
  type Connection,
  type ApiRecipe,
} from "@/lib/research";

type RecordRow = Record<string, unknown>;
const control = "w-full rounded border border-border bg-background p-2 text-sm";
const button =
  "rounded border border-border px-3 py-2 text-sm hover:bg-muted disabled:opacity-40";
const panel = "rounded-lg border border-border p-5 space-y-4";
export default function ResearchWorkbench() {
  const [connection, setConnection] = useState<Connection>({
    base: defaultBase,
    token: "",
    workspace: "personal",
  });
  const [draftConnection, setDraftConnection] = useState(connection);
  const [identity, setIdentity] = useState({
    workspace: "personal",
    role: "owner",
    auth_mode: "local",
  });
  const [connected, setConnected] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const [catalog, setCatalog] = useState<Series[]>([]),
    [runs, setRuns] = useState<Run[]>([]);
  const [jobs, setJobs] = useState<RecordRow[]>([]),
    [changes, setChanges] = useState<RecordRow[]>([]),
    [notes, setNotes] = useState<RecordRow[]>([]),
    [watches, setWatches] = useState<RecordRow[]>([]),
    [releases, setReleases] = useState<RecordRow[]>([]);
  const [tab, setTab] = useState("Workbench"),
    [filter, setFilter] = useState("");
  const [seriesId, setSeriesId] = useState("fred:A191RL1Q225SBEA"),
    [secondId, setSecondId] = useState(""),
    [thirdId, setThirdId] = useState("");
  const [asOf, setAsOf] = useState("2024-04-25"),
    [basis, setBasis] = useState("source"),
    [start, setStart] = useState("2024-01-01"),
    [end, setEnd] = useState("2024-01-01");
  const [title, setTitle] = useState("US growth revision notebook"),
    [operation, setOperation] = useState("level"),
    [threshold, setThreshold] = useState("1.5"),
    [windowSize, setWindowSize] = useState(1),
    [annualPeriods, setAnnualPeriods] = useState(4);
  const [left, setLeft] = useState(""),
    [right, setRight] = useState(""),
    [detail, setDetail] = useState<Run | null>(null),
    [comparison, setComparison] = useState<RecordRow | null>(null);
  const [note, setNote] = useState(""),
    [question, setQuestion] = useState(
      "What changed between these saved estimates?",
    ),
    [answer, setAnswer] = useState<RecordRow | null>(null);
  const load = useCallback(async () => {
    const snapshot = await request(connection, "/workspace").catch((e) => {
      setConnected(false);
      throw e;
    });
    setIdentity(
      z
        .object({
          workspace: z.string(),
          role: z.string(),
          auth_mode: z.string(),
        })
        .parse(snapshot.session),
    );
    const values = [
      snapshot.series,
      snapshot.runs,
      snapshot.jobs,
      snapshot.changes,
      snapshot.annotations,
      snapshot.watchlists,
      snapshot.releases,
    ];
    setCatalog(z.array(seriesSchema).parse(values[0]));
    setRuns(z.array(runSchema).parse(values[1]));
    values
      .slice(2)
      .forEach((v) => z.array(z.record(z.string(), z.unknown())).parse(v));
    setJobs(values[2]);
    setChanges(values[3]);
    setNotes(values[4]);
    setWatches(values[5]);
    setReleases(values[6]);
    setConnected(true);
    setError("");
  }, [connection]);
  useEffect(() => {
    let active = true;
    load().catch((e) => {
      if (active) {
        setConnected(false);
        setError(e.message || "Research API unavailable");
      }
    });
    return () => {
      active = false;
    };
  }, [load]);
  const action = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError("");
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Request failed");
    } finally {
      setBusy(false);
    }
  };
  const runRecipe = async (date = asOf) => {
    const ids = [
      seriesId,
      ...(["spread", "ratio", "net_liquidity"].includes(operation)
        ? [secondId]
        : []),
      ...(operation === "net_liquidity" ? [thirdId] : []),
    ];
    const recipe: ApiRecipe = {
      title: `${title} | ${date}`,
      queries: ids.map((id) => ({
        series_id: id,
        start,
        end,
        as_of: date,
        allow_partial: false,
        basis: basis as "source" | "platform",
      })),
      operation: operation as ApiRecipe["operation"],
      window: windowSize,
      periods_per_year: annualPeriods,
      threshold: threshold || null,
    };
    const saved = await request(connection, "/analyses", "POST", recipe);
    const job = await request(
      connection,
      `/analyses/${saved.id}/runs`,
      "POST",
      {},
    );
    for (let i = 0; i < 45; i++) {
      const state = await request(connection, `/jobs/${job.id}`);
      if (state.status === "succeeded") {
        const r = runSchema.parse(
          await request(connection, `/runs/${state.result.run_id}`),
        );
        setDetail(r);
        setRight(r.id);
        await load();
        return r;
      }
      if (["quarantined", "exhausted"].includes(state.status))
        throw new Error(state.result?.error || "Calculation failed");
      await new Promise((resolve) => setTimeout(resolve, 500));
    }
    await load();
    throw new Error(
      "Run is still queued. Check Jobs and refresh when it completes.",
    );
  };
  const selected = catalog.find((s) => s.id === seriesId);
  const chartRows = (
    comparison
      ? (
          comparison.data as {
            date: string;
            before: string | null;
            after: string | null;
          }[]
        ).map((r) => ({
          date: r.date,
          Before: r.before === null ? null : Number(r.before),
          After: r.after === null ? null : Number(r.after),
        }))
      : detail?.result.data.map((r) => ({
          date: r.date,
          Value: r.value === null ? null : Number(r.value),
        })) || []
  ).slice(-1000);
  const pick = (value: string, set: (v: string) => void, label: string) => (
    <label className="block space-y-1 text-sm">
      {label}
      <select
        className={control}
        value={value}
        onChange={(e) => set(e.target.value)}
      >
        <option value="">Select series</option>
        {catalog
          .filter(
            (s) =>
              !filter ||
              `${s.name} ${s.id} ${s.country}`
                .toLowerCase()
                .includes(filter.toLowerCase()),
          )
          .map((s) => (
            <option key={s.id} value={s.id}>
              {s.name} ({s.country})
            </option>
          ))}
      </select>
    </label>
  );
  return (
    <div className="mx-auto max-w-6xl space-y-7 px-4 py-8 sm:px-8">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="font-mono text-xs uppercase tracking-widest text-muted-foreground">
            Private research workspace
          </p>
          <h1 className="mt-2 font-serif text-3xl">
            Research across revisions
          </h1>
          <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
            Ask what the source reported, preserve the evidence, and compare a
            later estimate. Saved results keep their original inputs.
          </p>
        </div>
        <span className="text-xs">
          {connected
            ? `Connected · ${identity.workspace} · ${identity.role}`
            : "API unavailable"}
        </span>
      </div>
      <details className={panel} open={!connected}>
        <summary className="cursor-pointer text-sm font-medium">
          Connection settings
        </summary>
        <p className="text-sm text-muted-foreground">
          Start the local service with <code>uv run macro-research serve</code>.
          Existing dashboard pages work independently. Tokens remain in memory
          for this session.
        </p>
        <div className="grid gap-3 sm:grid-cols-3">
          <label className="text-sm">
            API URL
            <input
              className={control}
              value={draftConnection.base}
              onChange={(e) =>
                setDraftConnection({ ...draftConnection, base: e.target.value })
              }
            />
          </label>
          <label className="text-sm">
            Workspace
            <input
              className={control}
              value={draftConnection.workspace}
              onChange={(e) =>
                setDraftConnection({
                  ...draftConnection,
                  workspace: e.target.value,
                })
              }
            />
          </label>
          <label className="text-sm">
            OIDC bearer token (shared mode)
            <input
              type="password"
              autoComplete="off"
              className={control}
              value={draftConnection.token}
              onChange={(e) =>
                setDraftConnection({
                  ...draftConnection,
                  token: e.target.value,
                })
              }
            />
          </label>
        </div>
        <button
          className={button}
          onClick={() => {
            setError("");
            setConnected(false);
            setDetail(null);
            setComparison(null);
            setLeft("");
            setRight("");
            setAnswer(null);
            setRuns([]);
            setNotes([]);
            setCatalog([]);
            setConnection({ ...draftConnection });
          }}
        >
          Connect
        </button>
      </details>
      {error && (
        <p
          role="alert"
          className="rounded border border-red-400 p-3 text-sm text-red-700 dark:text-red-300"
        >
          {error}
        </p>
      )}
      {busy && (
        <p role="status" className="text-sm">
          Working with saved evidence…
        </p>
      )}
      <div
        className="flex flex-wrap gap-2"
        role="tablist"
        aria-label="Research views"
      >
        {[
          "Workbench",
          "Changes",
          "Watchlists",
          "Sources",
          "Jobs & releases",
        ].map((t) => (
          <button
            role="tab"
            aria-selected={tab === t}
            key={t}
            className={`${button} ${tab === t ? "bg-muted font-semibold" : ""}`}
            onClick={() => setTab(t)}
          >
            {t}
            {t === "Changes" && changes.length ? ` (${changes.length})` : ""}
          </button>
        ))}
        <button disabled={busy} className={button} onClick={() => action(load)}>
          Refresh lists
        </button>
      </div>
      {tab === "Workbench" && (
        <>
          <section className="rounded-lg border border-border bg-muted/30 p-5">
            <h2 className="font-serif text-xl">Start with a real revision</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              US real GDP growth for Q1 2024 was reported as 1.6% in April and
              1.3% in May. Import the two archived responses, save each
              estimate, then compare. The illustrative threshold is 1.5%.
            </p>
            <button
              disabled={busy || !connected}
              className={`${button} mt-3`}
              onClick={() =>
                action(async () => {
                  await request(connection, "/demo", "POST");
                  await load();
                  setError("");
                })
              }
            >
              1. Import GDP evidence
            </button>
          </section>
          <div className="grid gap-5 lg:grid-cols-[1fr_1.2fr]">
            <section className={panel}>
              <h2 className="font-serif text-xl">Build an analysis</h2>
              <label className="block text-sm">
                Find series
                <input
                  className={control}
                  placeholder="Name, source ID or country"
                  value={filter}
                  onChange={(e) => setFilter(e.target.value)}
                />
              </label>
              {pick(seriesId, setSeriesId, "Series")}
              {selected && (
                <p className="text-xs text-muted-foreground">
                  {selected.source.toUpperCase()} · {selected.frequency} ·{" "}
                  {unitLabel(selected.unit)}
                  <br />
                  Coverage:{" "}
                  {selected.modes
                    .map((m) =>
                      m === "source_vintage"
                        ? "historical source estimates"
                        : m === "forward_capture"
                          ? "captured current data"
                          : m,
                    )
                    .join(", ")}
                  . Captured dates: {selected.information_dates.join(", ")}.
                </p>
              )}
              <label className="block text-sm">
                Date meaning
                <select
                  className={control}
                  value={basis}
                  onChange={(e) => {
                    setBasis(e.target.value);
                    setAsOf(
                      e.target.value === "source"
                        ? "2024-04-25"
                        : new Date().toISOString(),
                    );
                  }}
                >
                  <option value="source">Source information date</option>
                  <option value="platform">
                    Platform knowledge timestamp (UTC)
                  </option>
                </select>
              </label>
              <label className="block text-sm">
                As of
                <input
                  className={control}
                  type={basis === "source" ? "date" : "text"}
                  value={asOf}
                  onChange={(e) => setAsOf(e.target.value)}
                />
              </label>
              <p className="text-xs text-muted-foreground">
                Source dates require a captured vintage. Platform timestamps use
                only data committed here by that moment. A historical import
                does not create an earlier platform record.
              </p>
              <div className="grid grid-cols-2 gap-3">
                <label className="text-sm">
                  Period from
                  <input
                    className={control}
                    type="date"
                    value={start}
                    onChange={(e) => setStart(e.target.value)}
                  />
                </label>
                <label className="text-sm">
                  Period through
                  <input
                    className={control}
                    type="date"
                    value={end}
                    onChange={(e) => setEnd(e.target.value)}
                  />
                </label>
              </div>
              <label className="block text-sm">
                Calculation
                <select
                  className={control}
                  value={operation}
                  onChange={(e) => setOperation(e.target.value)}
                >
                  {[
                    "level",
                    "difference",
                    "pct_change",
                    "annualized_growth",
                    "rolling_mean",
                    "zscore",
                    "spread",
                    "ratio",
                    "net_liquidity",
                  ].map((op) => (
                    <option key={op} value={op}>
                      {op.replaceAll("_", " ")}
                    </option>
                  ))}
                </select>
              </label>
              {["spread", "ratio", "net_liquidity"].includes(operation) &&
                pick(secondId, setSecondId, "Second series")}
              {operation === "net_liquidity" &&
                pick(thirdId, setThirdId, "Third series (RRP)")}
              <div className="grid grid-cols-2 gap-3">
                <label className="text-sm">
                  Window (observations)
                  <input
                    className={control}
                    type="number"
                    min={1}
                    max={520}
                    value={windowSize}
                    onChange={(e) => setWindowSize(Number(e.target.value))}
                  />
                </label>
                <label className="text-sm">
                  Periods per year
                  <input
                    className={control}
                    type="number"
                    min={1}
                    max={366}
                    value={annualPeriods}
                    onChange={(e) => setAnnualPeriods(Number(e.target.value))}
                  />
                </label>
              </div>
              <label className="block text-sm">
                Analysis name
                <input
                  className={control}
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                />
              </label>
              <label className="block text-sm">
                Optional threshold
                <input
                  className={control}
                  value={threshold}
                  onChange={(e) => setThreshold(e.target.value)}
                />
              </label>
              <div className="flex flex-wrap gap-2">
                <button
                  disabled={busy || !connected}
                  className={button}
                  onClick={() =>
                    action(async () => {
                      const r = await runRecipe();
                      if (r) setLeft(r.id);
                      setComparison(null);
                    })
                  }
                >
                  2. Save this estimate
                </button>
                <button
                  hidden={seriesId !== "fred:A191RL1Q225SBEA"}
                  disabled={busy || !connected || basis !== "source"}
                  className={button}
                  onClick={() =>
                    action(async () => {
                      setAsOf("2024-05-30");
                      await runRecipe("2024-05-30");
                      setComparison(null);
                    })
                  }
                >
                  3. Save May estimate
                </button>
              </div>
            </section>
            <section className={panel}>
              <h2 className="font-serif text-xl">Saved results</h2>
              {!runs.length && (
                <p className="text-sm text-muted-foreground">
                  No saved analyses yet. Import the evidence and save an
                  estimate to begin.
                </p>
              )}
              <div className="max-h-56 space-y-2 overflow-auto">
                {runs.map((r) => (
                  <button
                    key={r.id}
                    className="block w-full rounded border border-border p-3 text-left hover:bg-muted"
                    onClick={() =>
                      action(async () => {
                        setDetail(
                          runSchema.parse(
                            await request(connection, `/runs/${r.id}`),
                          ),
                        );
                        setRight(r.id);
                        setComparison(null);
                      })
                    }
                  >
                    <span className="block text-sm font-medium">
                      {r.recipe.title}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      Saved {new Date(r.computed_at).toLocaleString()} ·{" "}
                      {r.id.slice(0, 10)}
                    </span>
                  </button>
                ))}
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                {(
                  [
                    [left, setLeft, "Before"],
                    [right, setRight, "After"],
                  ] as const
                ).map(([value, set, label]) => (
                  <label key={label} className="text-sm">
                    {label}
                    <select
                      className={control}
                      value={value}
                      onChange={(e) => set(e.target.value)}
                    >
                      <option value="">Select saved result</option>
                      {runs.map((r) => (
                        <option key={r.id} value={r.id}>
                          {r.recipe.queries[0]?.as_of} · {r.id.slice(0, 6)} ·{" "}
                          {r.recipe.title}
                        </option>
                      ))}
                    </select>
                  </label>
                ))}
              </div>
              <button
                disabled={busy || !left || !right}
                className={button}
                onClick={() =>
                  action(async () => {
                    setComparison(
                      await request(connection, "/comparisons", "POST", {
                        left,
                        right,
                      }),
                    );
                  })
                }
              >
                4. Compare saved estimates
              </button>
              {chartRows.length === 1000 && (
                <p className="text-xs">
                  Chart limited to the latest 1,000 points. Exports retain every
                  row.
                </p>
              )}
              {chartRows.length > 0 && (
                <div
                  className="h-56 min-w-0"
                  role="img"
                  aria-label="Saved values by observation date. Exact values appear in the table below."
                >
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart
                      data={chartRows}
                      margin={{ left: 0, right: 15, top: 20, bottom: 0 }}
                    >
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                      <YAxis
                        domain={["auto", "auto"]}
                        tick={{ fontSize: 11 }}
                      />
                      <Tooltip />
                      <Legend />
                      {(comparison ? ["Before", "After"] : ["Value"]).map(
                        (k, i) => (
                          <Line
                            key={k}
                            dataKey={k}
                            stroke={i ? "#c66c43" : "#397d91"}
                            strokeWidth={2}
                            dot={{ r: 5 }}
                            connectNulls={false}
                          />
                        ),
                      )}
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              )}
              {comparison && (
                <>
                  <p className="text-sm">
                    {String(comparison.attribution)}. Values:{" "}
                    {unitLabel(String(comparison.unit))}. Differences in percent
                    units are percentage points.
                  </p>
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-sm">
                      <caption className="sr-only">Revision comparison</caption>
                      <thead>
                        <tr>
                          {["Period", "Before", "After", "Change"].map((s) => (
                            <th className="p-2" key={s}>
                              {s}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {(comparison.data as RecordRow[]).map((r, i) => (
                          <tr key={i}>
                            {["date", "before", "after", "change"].map((k) => (
                              <td
                                className="border-t border-border p-2 font-mono"
                                key={k}
                              >
                                {String(r[k] ?? "Missing")}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              )}
              {detail && !comparison && (
                <>
                  <p className="text-sm">
                    {detail.result.operation} · {unitLabel(detail.result.unit)}
                  </p>
                  <div className="max-h-72 overflow-auto">
                    <table className="w-full text-left text-sm">
                      <caption className="sr-only">
                        Exact saved observations
                      </caption>
                      <thead>
                        <tr>
                          <th>Period</th>
                          <th>Value</th>
                          <th>Threshold met</th>
                        </tr>
                      </thead>
                      <tbody>
                        {detail.result.data.map((r) => (
                          <tr key={r.date}>
                            <td className="py-2">{r.date}</td>
                            <td className="font-mono">
                              {r.value ?? "Missing"}
                            </td>
                            <td>
                              {r.threshold_met == null
                                ? "Not set"
                                : String(r.threshold_met)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              )}
              {detail && (
                <>
                  <details>
                    <summary className="cursor-pointer text-sm">
                      Evidence and computation
                    </summary>
                    <pre className="max-h-72 overflow-auto whitespace-pre-wrap break-all rounded bg-muted p-3 text-xs">
                      {JSON.stringify(
                        {
                          recipe: detail.recipe,
                          inputs: detail.inputs,
                          environment: detail.environment,
                          result_hash: detail.logical_result_hash,
                        },
                        null,
                        2,
                      )}
                    </pre>
                  </details>
                  <div className="flex flex-wrap gap-2">
                    {["csv", "json", "parquet", "html", "bundle"].map((f) => (
                      <button
                        key={f}
                        className={button}
                        disabled={busy}
                        onClick={() =>
                          action(() => download(connection, detail.id, f))
                        }
                      >
                        Export {f.toUpperCase()}
                      </button>
                    ))}
                  </div>
                  <label className="block text-sm">
                    Note on this saved version
                    <textarea
                      className={control}
                      value={note}
                      onChange={(e) => setNote(e.target.value)}
                    />
                  </label>
                  <button
                    className={button}
                    disabled={!note || busy}
                    onClick={() =>
                      action(async () => {
                        await request(connection, "/annotations", "POST", {
                          run_id: detail.id,
                          text: note,
                        });
                        setNote("");
                        await load();
                      })
                    }
                  >
                    Save note
                  </button>
                  {notes
                    .filter((n) => n.run_id === detail.id)
                    .map((n) => (
                      <p
                        key={String(n.id)}
                        className="border-l-2 border-border pl-3 text-sm"
                      >
                        {String(n.text)}
                      </p>
                    ))}
                </>
              )}
            </section>
          </div>
          <section className={panel}>
            <h2 className="font-serif text-xl">Explain the evidence</h2>
            <p className="text-sm text-muted-foreground">
              A bounded assistant reads the selected saved results and returns
              deterministic facts with capture references. It cannot trade,
              execute code, or change data.
            </p>
            <label className="block text-sm">
              Question
              <input
                className={control}
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
              />
            </label>
            <button
              disabled={busy || !connected}
              className={button}
              onClick={() =>
                action(async () => {
                  setAnswer(
                    await request(connection, "/assistant", "POST", {
                      question,
                      run_ids: [left, right].filter(
                        (r, i, a) => r && a.indexOf(r) === i,
                      ),
                    }),
                  );
                })
              }
            >
              5. Explain selected results
            </button>
            {answer && (
              <>
                <p className="text-sm" role="status">
                  {String(answer.answer)}
                </p>
                <details>
                  <summary>Facts and citations</summary>
                  <pre className="overflow-auto whitespace-pre-wrap break-all text-xs">
                    {JSON.stringify(answer, null, 2)}
                  </pre>
                </details>
              </>
            )}
          </section>
        </>
      )}
      {tab === "Sources" && (
        <ResearchSources connection={connection} onComplete={load} />
      )}
      {tab === "Changes" && (
        <section className={panel}>
          <h2 className="font-serif text-xl">Revision inbox</h2>
          <p className="text-sm text-muted-foreground">
            Newer captured inputs are available for these saved results.
            Original versions remain fixed. Choose a new information date in the
            workbench to save a comparison.
          </p>
          {!changes.length && (
            <p className="text-sm">
              No changed inputs found in the captured data.
            </p>
          )}
          {changes.map((c) => (
            <div className="border-t border-border pt-3" key={String(c.run_id)}>
              <p>{String(c.title)}</p>
              <pre className="overflow-auto text-xs">
                {JSON.stringify(c.changes, null, 2)}
              </pre>
            </div>
          ))}
        </section>
      )}
      {tab === "Watchlists" && (
        <section className={panel}>
          <h2 className="font-serif text-xl">Follow series</h2>
          {pick(seriesId, setSeriesId, "Series to follow")}
          <button
            className={button}
            disabled={busy || !connected}
            onClick={() =>
              action(async () => {
                const old = watches.find((w) => w.id === "main");
                await request(
                  connection,
                  "/watchlists/main",
                  "PUT",
                  {
                    name: "My watchlist",
                    series_ids: [
                      ...new Set([
                        ...((old?.series_ids as string[]) || []),
                        seriesId,
                      ]),
                    ],
                  },
                  old ? { "If-Match": String(old.version) } : undefined,
                );
                await load();
              })
            }
          >
            Add to my watchlist
          </button>
          {watches.map((w) => (
            <div key={String(w.id)}>
              <h3>{String(w.name)}</h3>
              <ul className="list-inside list-disc text-sm">
                {(w.series_ids as string[]).map((id) => (
                  <li key={id}>
                    {catalog.find((s) => s.id === id)?.name || id}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </section>
      )}
      {tab === "Jobs & releases" && (
        <section className={panel}>
          <h2 className="font-serif text-xl">Acquisition and calculations</h2>
          <p className="text-sm text-muted-foreground">
            Jobs persist across restarts. Failed source partitions keep the last
            committed dataset available. Release dates are explicitly
            registered; observation age is not a release calendar.
          </p>
          <div className="overflow-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr>
                  <th>Job</th>
                  <th>Status</th>
                  <th>Attempts</th>
                  <th>Details</th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((j) => (
                  <tr key={String(j.id)}>
                    <td className="py-2">
                      {String(j.job_kind)} · {String(j.id).slice(0, 12)}
                    </td>
                    <td>{String(j.status)}</td>
                    <td>{String(j.attempts)}</td>
                    <td>
                      <details>
                        <summary className="cursor-pointer">Inspect</summary>
                        <pre className="max-w-xs overflow-auto whitespace-pre-wrap break-all text-xs">
                          {JSON.stringify(j.result || j.payload, null, 2)}
                        </pre>
                      </details>
                      {["planned", "retry_wait", "running"].includes(
                        String(j.status),
                      ) && (
                        <button
                          disabled={busy}
                          className={button}
                          onClick={() =>
                            action(async () => {
                              await request(
                                connection,
                                `/jobs/${j.id}/cancel`,
                                "POST",
                              );
                              await load();
                            })
                          }
                        >
                          Cancel
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <h3>Tracked releases</h3>
          {!releases.length && (
            <p className="text-sm text-muted-foreground">
              No release dates registered.
            </p>
          )}
          {releases.map((r) => (
            <p key={String(r.id)} className="text-sm">
              {String(r.name)} · {String(r.state)} · {String(r.expected_at)}
            </p>
          ))}
        </section>
      )}
    </div>
  );
}

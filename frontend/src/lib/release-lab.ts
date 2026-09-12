import { z } from "zod";

const hash = z.string().regex(/^[a-f0-9]{64}$/);
const day = z.string().date();
const value = z
  .string()
  .max(100)
  .regex(/^-?\d+(?:\.\d+)?$/)
  .refine((v) => Number.isFinite(Number(v)));
export const recipeSchema = z
  .object({
    schema_version: z.literal("research-comparison/1"),
    title: z.string().trim().min(1).max(120),
    bundle_id: hash,
    series_id: z.enum(["PAYEMS", "INDPRO", "A191RL1Q225SBEA"]),
    before_snapshot: hash,
    after_snapshot: hash,
    observation_start: day,
    observation_end: day,
    operation: z.enum(["level", "difference", "pct_change"]),
    threshold: z.number().finite().min(-10000).max(10000),
    comparison: z.literal("strictly_above"),
  })
  .strict();
export type ComparisonRecipe = z.infer<typeof recipeSchema>;

const snapshotSchema = z
  .object({
    id: hash,
    series_id: z.string(),
    information_date: day,
    observation_start: day,
    observation_end: day,
    captured_at: z.string(),
    evidence: z.array(hash).min(2).max(10),
    observations: z
      .array(z.object({ date: day, value }))
      .min(2)
      .max(1000),
  })
  .passthrough();
const trackSchema = z
  .object({
    id: z.string(),
    name: z.string(),
    agency: z.string(),
    frequency: z.enum(["monthly", "quarterly"]),
    unit: z.string(),
    adjustment: z.string(),
    operation: z.enum(["level", "difference", "pct_change"]),
    result_unit: z.string(),
    threshold: z.number(),
    decimals: z.number(),
    source_url: z.string().url(),
    license_url: z.string().url(),
  })
  .passthrough();
const evidenceSchema = z
  .object({
    sha256: hash,
    source_url: z.string().url(),
    params: z.record(z.string(), z.union([z.string(), z.number()])),
    body: z.string().max(2000000),
    bytes: z.number(),
    captured_at: z.string(),
  })
  .passthrough();
const summarySchema = z
  .object({
    n: z.number(),
    planned: z.number(),
    excluded: z.number(),
    initial_mean: z.number(),
    revised_mean: z.number(),
    mean_revision: z.number(),
    median_revision: z.number(),
    mean_absolute_revision: z.number(),
    largest_absolute_revision: z.number(),
    upward_revisions: z.number(),
    downward_revisions: z.number(),
    unchanged: z.number(),
    thresholds: z.array(
      z.object({
        threshold: z.number(),
        initial_above: z.number(),
        revised_above: z.number(),
        switches: z.number(),
        to_above: z.number(),
        from_above: z.number(),
      }),
    ),
  })
  .passthrough();
const studyRowSchema = z
  .object({
    period: day,
    status: z.enum(["included", "excluded"]),
    reason: z.string().optional(),
    initial_date: day.optional(),
    revised_date: day.optional(),
    before_snapshot: hash.optional(),
    after_snapshot: hash.optional(),
    initial: value.optional(),
    revised: value.optional(),
    revision: value.optional(),
    inputs: z
      .object({
        initial_current: value,
        initial_previous: value,
        revised_current: value,
        revised_previous: value,
      })
      .optional(),
    attribution: z
      .object({ current_level: value, previous_level: value })
      .optional(),
  })
  .passthrough();
const studySchema = z
  .object({
    plan: z
      .object({
        title: z.string(),
        observation_start: day,
        observation_end: day,
        comparison_information_date: day,
        thresholds: z.array(z.number()),
        interpretation: z.string(),
        population: z.string(),
        plan_stage: z.string(),
      })
      .passthrough(),
    plan_hash: hash,
    rows: z.array(studyRowSchema),
    summary: summarySchema,
    by_year: z.array(summarySchema.extend({ year: z.number() })),
    uncertainty: z
      .object({
        status: z.literal("computed"),
        method: z.string(),
        replicates: z.number(),
        interpretation: z.string(),
        intervals: z.array(
          z.object({
            block_months: z.number(),
            mean_revision: z.tuple([z.number(), z.number()]),
            mean_absolute_revision: z.tuple([z.number(), z.number()]),
            switch_share: z.array(
              z.object({
                threshold: z.number(),
                interval: z.tuple([z.number(), z.number()]),
              }),
            ),
          }),
        ),
      })
      .passthrough(),
    methods: z.array(z.string()),
    sources: z.array(z.string().url()),
  })
  .passthrough();
const bundleSchema = z
  .object({
    schema_version: z.literal("release-lab/1"),
    id: hash,
    kind: z.enum(["releases", "revision-study"]),
    as_of: day,
    captured_at: z.string(),
    series: z.array(trackSchema).min(1).max(3),
    snapshots: z.array(snapshotSchema).min(2).max(100),
    evidence: z.record(hash, evidenceSchema),
    inbox: z
      .array(
        z
          .object({
            series_id: z.string(),
            date: day,
            status: z.string(),
            detail: z.string(),
            checked_at: z.string().nullable().optional(),
            evidence: z.array(hash).optional(),
          })
          .passthrough(),
      )
      .max(1000),
    study: studySchema.optional(),
  })
  .passthrough();
export type LabBundle = z.infer<typeof bundleSchema>;
export type LabSnapshot = z.infer<typeof snapshotSchema>;
export type LabTrack = z.infer<typeof trackSchema>;
export type StudyRow = z.infer<typeof studyRowSchema>;

export function parseBundle(input: unknown): LabBundle {
  const bundle = bundleSchema.parse(input);
  if (
    new Set(bundle.snapshots.map((s) => s.id)).size !== bundle.snapshots.length
  )
    throw new Error("Duplicate snapshot identity");
  for (const s of bundle.snapshots) {
    if (
      !bundle.series.some((t) => t.id === s.series_id) ||
      s.information_date > bundle.as_of
    )
      throw new Error("Snapshot is outside the declared collection");
    if (s.evidence.some((h) => !bundle.evidence[h]))
      throw new Error("Source evidence is missing");
    if (
      new Set(s.observations.map((r) => r.date)).size !== s.observations.length
    )
      throw new Error("Duplicate observation date");
  }
  return bundle;
}

export function canonical(input: unknown): string {
  if (input === null || typeof input !== "object") return JSON.stringify(input);
  if (Array.isArray(input)) return `[${input.map(canonical).join(",")}]`;
  const object = input as Record<string, unknown>;
  return `{${Object.keys(object)
    .sort()
    .map((k) => `${JSON.stringify(k)}:${canonical(object[k])}`)
    .join(",")}}`;
}
export async function sha256(text: string) {
  const buffer = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(text),
  );
  return [...new Uint8Array(buffer)]
    .map((n) => n.toString(16).padStart(2, "0"))
    .join("");
}
export async function verifyBundle(bundle: LabBundle) {
  const { id: publication, ...payload } = bundle;
  if ((await sha256(canonical(payload))) !== publication)
    throw new Error("Publication hash mismatch");
  for (const [id, evidence] of Object.entries(bundle.evidence)) {
    if ((await sha256(evidence.body)) !== id)
      throw new Error("Source response hash mismatch");
    if (new TextEncoder().encode(evidence.body).length !== evidence.bytes)
      throw new Error("Source response byte count mismatch");
  }
  for (const snapshot of bundle.snapshots) {
    const track = bundle.series.find((s) => s.id === snapshot.series_id)!;
    const metadata = snapshot.evidence.flatMap((id) => {
      const e = bundle.evidence[id];
      return e.source_url.endsWith("/series") ? JSON.parse(e.body).seriess : [];
    });
    if (
      metadata.length !== 1 ||
      metadata[0].id !== track.id ||
      metadata[0].units !== track.unit ||
      metadata[0].seasonal_adjustment_short !== track.adjustment ||
      metadata[0].frequency_short !==
        (track.frequency === "monthly" ? "M" : "Q") ||
      metadata[0].observation_end !== snapshot.observation_end
    )
      throw new Error("Source metadata differs from the series contract");
    const rows = snapshot.evidence.flatMap((id) => {
      const e = bundle.evidence[id];
      if (!e.source_url.endsWith("/series/observations")) return [];
      const response = JSON.parse(e.body);
      if (
        response.realtime_start !== snapshot.information_date ||
        response.realtime_end !== snapshot.information_date ||
        response.units !== "lin" ||
        response.output_type !== 1
      )
        throw new Error("Source response information date mismatch");
      return response.observations.map(
        (r: { date: string; value: string }) => ({
          date: r.date,
          value: r.value,
        }),
      );
    });
    if (canonical(rows) !== canonical(snapshot.observations))
      throw new Error("Snapshot differs from source rows");
    if (
      canonical(rows.map((r: { date: string }) => r.date)) !==
      canonical(
        calendar(
          snapshot.observation_start,
          snapshot.observation_end,
          track.frequency,
          1000,
        ),
      )
    )
      throw new Error("Complete source snapshot contains a calendar gap");
  }
  return Object.keys(bundle.evidence).length;
}

function offsetMonth(date: string, months: number) {
  const d = new Date(date + "T12:00:00Z");
  d.setUTCMonth(d.getUTCMonth() + months);
  return d.toISOString().slice(0, 10);
}
function calendar(start: string, end: string, frequency: string, budget = 60) {
  if (start > end || start.slice(8) !== "01" || end.slice(8) !== "01")
    throw new Error("Choose an ordered range of period start dates");
  if (
    frequency === "quarterly" &&
    [start, end].some((d) => !["01", "04", "07", "10"].includes(d.slice(5, 7)))
  )
    throw new Error(
      "Quarterly periods start in January, April, July or October",
    );
  const dates: string[] = [];
  for (
    let d = start;
    d <= end;
    d = offsetMonth(d, frequency === "monthly" ? 1 : 3)
  ) {
    if (dates.length >= budget)
      throw new Error(`A comparison is limited to ${budget} periods`);
    dates.push(d);
  }
  return dates;
}
const rounded = (v: number) => Math.round(v * 1e8) / 1e8;

function decimalFraction(text: string) {
  const [mantissa, exponent = "0"] = text.toLowerCase().split("e");
  const [whole, fraction = ""] = mantissa.split(".");
  const numerator = BigInt(whole + fraction);
  const scale = fraction.length - Number(exponent);
  return scale >= 0
    ? { n: numerator, d: BigInt(10) ** BigInt(scale) }
    : { n: numerator * BigInt(10) ** BigInt(-scale), d: BigInt(1) };
}

function aboveReference(
  current: string,
  previous: string | undefined,
  operation: string,
  reference: number,
) {
  let { n, d } = decimalFraction(current);
  if (operation !== "level") {
    const prior = decimalFraction(previous!);
    if (operation === "difference") {
      n = n * prior.d - prior.n * d;
      d *= prior.d;
    } else {
      n = (n * prior.d - prior.n * d) * BigInt(100);
      d *= prior.n;
    }
  }
  if (d < BigInt(0)) {
    n = -n;
    d = -d;
  }
  const threshold = decimalFraction(String(reference));
  return n * threshold.d > threshold.n * d;
}

export function runRecipe(bundle: LabBundle, input: ComparisonRecipe) {
  const recipe = recipeSchema.parse(input);
  if (recipe.bundle_id !== bundle.id)
    throw new Error("This recipe pins a different publication");
  const track = bundle.series.find((s) => s.id === recipe.series_id);
  const before = bundle.snapshots.find((s) => s.id === recipe.before_snapshot);
  const after = bundle.snapshots.find((s) => s.id === recipe.after_snapshot);
  if (
    !track ||
    !before ||
    !after ||
    before.series_id !== track.id ||
    after.series_id !== track.id
  )
    throw new Error(
      "Both inputs must be captured snapshots of the same series",
    );
  if (recipe.operation !== track.operation)
    throw new Error(
      "Transformation does not match this series' approved measure",
    );
  const rawMaps = [before, after].map(
    (s) => new Map(s.observations.map((r) => [r.date, r.value])),
  );
  const maps = [before, after].map(
    (s) => new Map(s.observations.map((r) => [r.date, Number(r.value)])),
  );
  const rows = calendar(
    recipe.observation_start,
    recipe.observation_end,
    track.frequency,
  ).map((period) => {
    const prior = offsetMonth(period, track.frequency === "monthly" ? -1 : -3);
    const [a, b] = maps.map((m) => m.get(period));
    const [p, q] = maps.map((m) => m.get(prior));
    const citations = [before, after].flatMap((s, i) =>
      [period, ...(recipe.operation === "level" ? [] : [prior])]
        .filter((d) => maps[i].has(d))
        .map((d) => ({
          snapshot: s.id,
          information_date: s.information_date,
          observation_date: d,
          value: s.observations.find((r) => r.date === d)!.value,
          capture: s.evidence.find((id) =>
            bundle.evidence[id].source_url.endsWith("/series/observations"),
          )!,
        })),
    );
    const missing =
      a === undefined ||
      b === undefined ||
      (recipe.operation !== "level" &&
        (p === undefined ||
          q === undefined ||
          (recipe.operation === "pct_change" && (p === 0 || q === 0))));
    if (missing)
      return {
        period,
        initial: null,
        revised: null,
        revision: null,
        current_contribution: null,
        previous_contribution: null,
        switched: null,
        reason:
          "A required same-vintage level is unavailable or its denominator is zero.",
        citations,
      };
    let initial = a!,
      revised = b!,
      current = b! - a!,
      previous = 0;
    if (recipe.operation === "difference") {
      initial = a! - p!;
      revised = b! - q!;
      previous = p! - q!;
    } else if (recipe.operation === "pct_change") {
      initial = (a! / p! - 1) * 100;
      revised = (b! / q! - 1) * 100;
      current = ((b! - a!) / p! + (b! - a!) / q!) * 50;
      previous = (a! / q! - a! / p! + (b! / q! - b! / p!)) * 50;
    }
    initial = rounded(initial);
    revised = rounded(revised);
    return {
      period,
      initial,
      revised,
      revision: rounded(revised - initial),
      current_contribution: rounded(current),
      previous_contribution: rounded(previous),
      // Classification uses exact source decimals, before display rounding.
      switched:
        aboveReference(
          rawMaps[0].get(period)!,
          rawMaps[0].get(prior),
          recipe.operation,
          recipe.threshold,
        ) !==
        aboveReference(
          rawMaps[1].get(period)!,
          rawMaps[1].get(prior),
          recipe.operation,
          recipe.threshold,
        ),
      reason: null,
      citations,
    };
  });
  return {
    recipe,
    rows,
    before_date: before.information_date,
    after_date: after.information_date,
    unit: track.result_unit,
    threshold_rule: "strictly above the reference",
    date_precision: "day",
    attribution_method:
      recipe.operation === "pct_change"
        ? "Symmetric average of both input-update orders (Shapley decomposition)."
        : "Exact additive change in the current level and preceding level.",
    steps: [
      "Resolve two immutable source snapshots",
      "Match exact calendar periods and units",
      "Calculate each measure within its own vintage",
      "Attribute the revision and compare the reference",
      "Attach each raw input's capture hash and information date",
    ],
  };
}
export type ComparisonResult = ReturnType<typeof runRecipe>;

export function defaultRecipe(
  bundle: LabBundle,
  seriesId = bundle.series[0].id,
): ComparisonRecipe {
  const track = bundle.series.find((s) => s.id === seriesId)!;
  const snapshots = bundle.snapshots
    .filter((s) => s.series_id === seriesId)
    .sort((a, b) => a.information_date.localeCompare(b.information_date));
  const before = snapshots.at(-2)!,
    after = snapshots.at(-1)!;
  const end =
    before.observation_end < after.observation_end
      ? before.observation_end
      : after.observation_end;
  return {
    schema_version: "research-comparison/1",
    title: `${track.name}: release comparison`,
    bundle_id: bundle.id,
    series_id: seriesId as ComparisonRecipe["series_id"],
    before_snapshot: before.id,
    after_snapshot: after.id,
    observation_start: end,
    observation_end: end,
    operation: track.operation,
    threshold: track.threshold,
    comparison: "strictly_above",
  };
}

export function planQuestion(
  bundle: LabBundle,
  question: string,
):
  | { status: "planned"; recipe: ComparisonRecipe }
  | { status: "unsupported"; reason: string } {
  // A finite language routes only to inspectable deterministic data operations.
  // Unmatched text is rejected in full; extra instructions are never discarded.
  const match = question
    .trim()
    .match(
      /^(?:compare|show) (payrolls|jobs|industrial production|production|gdp|growth) (?:for|in) (\d{4}-\d{2}) (?:from )?(first to latest|initial to revised|\d{4}-\d{2}-\d{2} to \d{4}-\d{2}-\d{2})(?: (?:above|at) (-?\d+(?:\.\d+)?))?\.?$/i,
    );
  if (!match || question.length > 400)
    return {
      status: "unsupported",
      reason:
        "Use a supported series, month and two archived dates. Example: Compare payrolls for 2024-07 first to latest above 100.",
    };
  const seriesId = /payrolls|jobs/i.test(match[1])
    ? "PAYEMS"
    : /production/i.test(match[1])
      ? "INDPRO"
      : "A191RL1Q225SBEA";
  const track = bundle.series.find((s) => s.id === seriesId);
  const period = match[2] + "-01";
  if (!track || !day.safeParse(period).success)
    return {
      status: "unsupported",
      reason: "This series or period is not in the selected collection.",
    };
  const snapshots = bundle.snapshots
    .filter(
      (s) =>
        s.series_id === seriesId &&
        s.observations.some((r) => r.date === period),
    )
    .sort((a, b) => a.information_date.localeCompare(b.information_date));
  const dates = match[3].match(/\d{4}-\d{2}-\d{2}/g);
  const studyRow = bundle.study?.rows.find(
    (r) => r.period === period && r.status === "included",
  );
  if (!dates && bundle.kind === "revision-study" && !studyRow)
    return {
      status: "unsupported",
      reason: "The initial-release study does not cover that period.",
    };
  if (!dates && bundle.kind === "releases" && /initial/i.test(match[3]))
    return {
      status: "unsupported",
      reason:
        "This release collection contains recent captures. Use explicit dates or first to latest within this collection.",
    };
  const before = dates
    ? snapshots.find((s) => s.information_date === dates[0])
    : studyRow
      ? snapshots.find((s) => s.id === studyRow.before_snapshot)
      : snapshots[0];
  const after = dates
    ? snapshots.find((s) => s.information_date === dates[1])
    : studyRow
      ? snapshots.find((s) => s.id === studyRow.after_snapshot)
      : snapshots.at(-1);
  if (!before || !after || before.id === after.id)
    return {
      status: "unsupported",
      reason:
        "Two distinct captured vintages are required. No unrecorded information date is inferred.",
    };
  const recipe = {
    ...defaultRecipe(bundle, seriesId),
    title: `${track.name}: ${match[2]}`,
    before_snapshot: before.id,
    after_snapshot: after.id,
    observation_start: period,
    observation_end: period,
    threshold: match[4] === undefined ? track.threshold : Number(match[4]),
  };
  try {
    if (
      runRecipe(bundle, recipe).rows.some(
        (r) => r.initial === null || r.revised === null,
      )
    )
      return {
        status: "unsupported",
        reason:
          "Required same-vintage history is unavailable for this comparison.",
      };
  } catch {
    return {
      status: "unsupported",
      reason:
        "The requested comparison does not satisfy the recipe's period or parameter limits.",
    };
  }
  return { status: "planned", recipe };
}

export function encodeRecipe(recipe: ComparisonRecipe) {
  return btoa(unescape(encodeURIComponent(JSON.stringify(recipe))))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
}
export function decodeRecipe(encoded: string) {
  if (encoded.length > 3000 || !/^[\w-]+$/.test(encoded))
    throw new Error("Invalid shared recipe");
  return recipeSchema.parse(
    JSON.parse(
      decodeURIComponent(
        escape(atob(encoded.replace(/-/g, "+").replace(/_/g, "/"))),
      ),
    ),
  );
}

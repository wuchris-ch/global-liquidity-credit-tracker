import assert from "node:assert/strict";
import fs from "node:fs";
import { createHash } from "node:crypto";
import { createRequire } from "node:module";
import ts from "typescript";

const require = createRequire(import.meta.url);
const compiled = { exports: {} };
new Function(
  "require",
  "module",
  "exports",
  ts.transpileModule(fs.readFileSync("src/lib/release-lab.ts", "utf8"), {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText,
)(require, compiled, compiled.exports);
const {
  parseBundle,
  verifyBundle,
  defaultRecipe,
  runRecipe,
  planQuestion,
  encodeRecipe,
  decodeRecipe,
  canonical,
} = compiled.exports;
const bundles = Object.fromEntries(
  ["study", "feed"].map((k) => [
    k,
    parseBundle(JSON.parse(fs.readFileSync(`src/lib/release-${k}.json`))),
  ]),
);
for (const [name, bundle] of Object.entries(bundles)) {
  assert.deepEqual(
    bundle,
    JSON.parse(fs.readFileSync(`public/research/lab/${name}.json`)),
  );
  await verifyBundle(bundle);
  for (const series of bundle.series) {
    const recipe = defaultRecipe(bundle, series.id);
    const forward = runRecipe(bundle, recipe);
    assert.deepEqual(decodeRecipe(encodeRecipe(recipe)), recipe);
    const backward = runRecipe(bundle, {
      ...recipe,
      before_snapshot: recipe.after_snapshot,
      after_snapshot: recipe.before_snapshot,
    });
    assert.ok(
      Math.abs(forward.rows[0].revision + backward.rows[0].revision) < 1e-8,
    );
    assert.equal(
      runRecipe(bundle, { ...recipe, after_snapshot: recipe.before_snapshot })
        .rows[0].revision,
      0,
    );
    for (const row of forward.rows) {
      assert.ok(
        Math.abs(
          row.current_contribution + row.previous_contribution - row.revision,
        ) < 2e-8,
      );
      for (const c of row.citations) {
        const e = bundle.evidence[c.capture],
          source = JSON.parse(e.body);
        assert.equal(source.realtime_start, c.information_date);
        assert.equal(
          source.observations.find((r) => r.date === c.observation_date).value,
          c.value,
        );
      }
    }
  }
}
const evaluation = JSON.parse(
  fs.readFileSync("scripts/research-planner-evaluation.json"),
);
let factual = 0,
  citations = 0,
  refused = 0;
const demonstrate = [];
for (const item of evaluation.cases) {
  const bundle = bundles[item.collection];
  const planned = planQuestion(bundle, item.question);
  assert.equal(planned.status, item.status, item.question);
  if (planned.status === "unsupported") {
    refused++;
    continue;
  }
  const result = runRecipe(bundle, planned.recipe),
    row = result.rows[0];
  for (const metric of ["initial", "revised", "switched"])
    if (item[metric] !== undefined)
      assert.equal(row[metric], item[metric], item.question);
  // Independent arithmetic reads original HTTP bodies, not normalized snapshots.
  const inputs = row.citations.map((c) => {
    const evidence = bundle.evidence[c.capture];
    assert.equal(
      createHash("sha256").update(evidence.body).digest("hex"),
      c.capture,
    );
    const body = JSON.parse(evidence.body);
    assert.equal(body.realtime_start, c.information_date);
    const raw = body.observations.find((r) => r.date === c.observation_date);
    assert.equal(raw.value, c.value);
    citations++;
    return Number(raw.value);
  });
  const expected =
    planned.recipe.operation === "level"
      ? inputs
      : planned.recipe.operation === "difference"
        ? [inputs[0] - inputs[1], inputs[2] - inputs[3]]
        : [
            (inputs[0] / inputs[1] - 1) * 100,
            (inputs[2] / inputs[3] - 1) * 100,
          ];
  assert.ok(
    Math.abs(row.initial - expected[0]) < 1e-8 &&
      Math.abs(row.revised - expected[1]) < 1e-8,
  );
  factual++;
  if (demonstrate.length < 2)
    demonstrate.push({
      question: item.question,
      recipe: planned.recipe,
      result,
    });
}
const study = bundles.study,
  recipe = defaultRecipe(study);
const incomplete = structuredClone(study);
incomplete.snapshots
  .find((s) => s.id === recipe.before_snapshot)
  .observations.pop();
assert.equal(runRecipe(incomplete, recipe).rows[0].initial, null);
assert.throws(
  () => runRecipe(study, { ...recipe, bundle_id: "0".repeat(64) }),
  /publication/,
);
assert.throws(
  () => runRecipe(study, { ...recipe, operation: "pct_change" }),
  /Transformation/,
);
assert.throws(() => runRecipe(study, { ...recipe, threshold: Infinity }));
assert.throws(() =>
  runRecipe(study, {
    ...recipe,
    observation_start: "2024-12-01",
    observation_end: "2024-11-01",
  }),
);
const badUnits = structuredClone(study);
badUnits.series[0].unit = "Persons";
const payload = structuredClone(badUnits);
delete payload.id;
badUnits.id = createHash("sha256").update(canonical(payload)).digest("hex");
await assert.rejects(verifyBundle(badUnits), /metadata/);
const gdprecipe = defaultRecipe(bundles.feed, "A191RL1Q225SBEA");
const precisionBoundary = JSON.parse(
  fs.readFileSync("../tests/research/fixtures/precision-boundary.json"),
);
assert.deepEqual(
  runRecipe(bundles.feed, precisionBoundary.recipe),
  precisionBoundary.result,
);
assert.equal(precisionBoundary.result.rows[0].switched, true);
assert.throws(
  () =>
    runRecipe(bundles.feed, { ...gdprecipe, observation_end: "2026-02-01" }),
  /Quarterly/,
);
const ui = fs.readFileSync("src/components/release-laboratory.tsx", "utf8");
assert.ok(
  !ui.includes("/api/v1/research") &&
    !ui.includes("localhost:8000") &&
    !ui.includes('@/lib/research"'),
);
const receipt = {
  evaluation: evaluation.version,
  prompts: evaluation.cases.length,
  factual_cases_passed: factual,
  exact_input_citations_verified: citations,
  unsupported_prompts_refused: refused,
  deterministic_mode: true,
  network_requests: 0,
  scope: "Finite comparison grammar over the two captured collections",
  demonstration: demonstrate,
};
if (process.env.RESEARCH_EVAL_OUTPUT)
  fs.writeFileSync(
    process.env.RESEARCH_EVAL_OUTPUT,
    JSON.stringify(receipt, null, 2) + "\n",
  );
if (process.env.RESEARCH_REPLAY_OUTPUT)
  fs.writeFileSync(
    process.env.RESEARCH_REPLAY_OUTPUT,
    JSON.stringify({
      schema_version: "research-replay/1",
      bundle: study,
      ...demonstrate[0],
    }),
  );
console.log(
  `Release laboratory: ${evaluation.cases.length} reserved prompts, ${factual} factual comparisons, ${citations} exact citations and ${refused} unsupported refusals passed; source integrity, unit drift, missing history, typed sharing and attribution checked.`,
);

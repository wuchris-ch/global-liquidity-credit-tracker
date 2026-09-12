import assert from "node:assert/strict";
import fs from "node:fs";
import { createHash } from "node:crypto";
import ts from "typescript";

const atlas = JSON.parse(
  fs.readFileSync("src/lib/research-atlas.json", "utf8"),
);
assert.deepEqual(
  atlas,
  JSON.parse(fs.readFileSync("public/research/evidence/atlas.json", "utf8")),
);
const code = ts.transpileModule(
  fs.readFileSync("src/lib/public-research.ts", "utf8"),
  {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
      esModuleInterop: true,
    },
  },
).outputText;
const compiled = { exports: {} };
new Function("require", "module", "exports", code)(
  (name) => {
    assert.equal(name, "@/lib/research-atlas.json");
    return atlas;
  },
  compiled,
  compiled.exports,
);
const { observations, focusValue, compare, csv } = compiled.exports;
// Independent publisher release values for the fixed observation periods.
// BEA Q1 2024 third-estimate release; BLS September 2024 employment release.
const expected = {
  growth: [1.6, 1.3, 1.4],
  employment: [114, 89, 144],
  production: [-0.63805295, -0.94306922, -0.61951566],
};
let count = 0;
for (const study of atlas.cases) {
  study.snapshots.forEach((snapshot, index) => {
    const bytes = fs.readFileSync("public" + snapshot.raw_url);
    assert.equal(
      createHash("sha256").update(bytes).digest("hex"),
      snapshot.sha256,
    );
    const response = JSON.parse(bytes);
    assert.equal(response.realtime_start, snapshot.date);
    assert.equal(response.realtime_end, snapshot.date);
    assert.equal(response.count, response.observations.length);
    assert.deepEqual(
      snapshot.observations,
      response.observations.map(({ date, value }) => ({ date, value })),
    );
    assert.ok(!Object.hasOwn(snapshot.params, "api_key"));
    assert.equal(focusValue(study, snapshot), expected[study.id][index]);
    assert.ok(snapshot.observations.every((row) => row.date <= study.period));
    assert.ok(new Date(snapshot.captured_at) > new Date(snapshot.date));
    const result = observations(study, snapshot);
    if (study.operation !== "level") assert.equal(result[0].value, null);
    for (let i = 1; i < snapshot.observations.length; i++) {
      const a = new Date(snapshot.observations[i - 1].date),
        b = new Date(snapshot.observations[i].date);
      assert.equal(
        (b.getUTCFullYear() - a.getUTCFullYear()) * 12 +
          b.getUTCMonth() -
          a.getUTCMonth(),
        study.frequency === "monthly" ? 1 : 3,
      );
    }
    count++;
  });
  const [first, second] = study.snapshots;
  assert.ok(
    compare(study, first, first).every(
      (row) => row.revision === null || row.revision === 0,
    ),
  );
  const forward = compare(study, first, second).at(-1).revision;
  const backward = compare(study, second, first).at(-1).revision;
  assert.equal(forward, -backward);
  const exported = csv(study, first, second).trim().split("\n");
  assert.equal(exported.length, first.observations.length + 1);
  assert.ok(exported.every((line) => line.split(",").length === 8));
}
// Published code cannot import or invoke the private research transport.
const publicUI = fs.readFileSync("src/components/public-research.tsx", "utf8");
assert.ok(!publicUI.includes('@/lib/research"'));
assert.ok(!publicUI.includes("/api/v1/research"));
assert.ok(!publicUI.includes("127.0.0.1"));
console.log(
  `Public research: ${count} source hashes and vintage values verified; chronology, same-vintage arithmetic, reverse comparisons, missing results, CSV and public isolation passed.`,
);

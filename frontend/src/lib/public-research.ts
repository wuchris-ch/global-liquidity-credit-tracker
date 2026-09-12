import collection from "@/lib/research-atlas.json";

export type Study = (typeof collection.cases)[number];
export type Snapshot = Study["snapshots"][number];
export const atlas = collection;

export function observations(study: Study, snapshot: Snapshot) {
  return snapshot.observations.map((row, index, rows) => {
    const value = Number(row.value);
    const previous = index ? Number(rows[index - 1].value) : null;
    const result =
      study.operation === "level"
        ? value
        : previous === null
          ? null
          : study.operation === "difference"
            ? value - previous
            : previous === 0
              ? null
              : (value / previous - 1) * 100;
    return {
      date: row.date,
      value: result === null ? null : Math.round(result * 1e8) / 1e8,
    };
  });
}

export function focusValue(study: Study, snapshot: Snapshot) {
  return (
    observations(study, snapshot).find((row) => row.date === study.period)
      ?.value ?? null
  );
}

export function compare(
  study: Study,
  baseline: Snapshot,
  comparison: Snapshot,
) {
  const first = observations(study, baseline);
  const second = new Map(
    observations(study, comparison).map((row) => [row.date, row.value]),
  );
  return first.map((row) => {
    const later = second.get(row.date) ?? null;
    return {
      date: row.date,
      baseline: row.value,
      comparison: later,
      revision:
        row.value === null || later === null
          ? null
          : Math.round((later - row.value) * 1e8) / 1e8,
    };
  });
}

export function number(value: number | null, decimals: number, signed = false) {
  if (value === null) return "Unavailable";
  return new Intl.NumberFormat("en-US", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
    signDisplay: signed ? "exceptZero" : "auto",
  }).format(Object.is(value, -0) ? 0 : value);
}

export function dateLabel(value: string) {
  return new Date(value.slice(0, 10) + "T12:00:00Z").toLocaleDateString(
    "en-US",
    {
      month: "short",
      day: "numeric",
      year: "numeric",
      timeZone: "UTC",
    },
  );
}

export function csv(study: Study, baseline: Snapshot, comparison: Snapshot) {
  const header =
    "observation_date,baseline_vintage,comparison_vintage,baseline_value,comparison_value,revision,value_unit,revision_unit";
  return (
    [
      header,
      ...compare(study, baseline, comparison).map((row) =>
        [
          row.date,
          baseline.date,
          comparison.date,
          row.baseline ?? "",
          row.comparison ?? "",
          row.revision ?? "",
          study.unit,
          study.delta_unit,
        ].join(","),
      ),
    ].join("\n") + "\n"
  );
}

export function saveFile(filename: string, text: string, type: string) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

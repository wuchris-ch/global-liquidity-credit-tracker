"use client";
import { useState } from "react";
import { request, type Connection } from "@/lib/research";
const input =
  "mt-1 w-full rounded border border-border bg-background p-2 text-sm";
export function ResearchSources({
  connection,
  onComplete,
}: {
  connection: Connection;
  onComplete: () => Promise<void>;
}) {
  const [source, setSource] = useState("fred"),
    [id, setId] = useState("WALCL"),
    [name, setName] = useState("Federal Reserve total assets"),
    [country, setCountry] = useState("USA"),
    [unit, setUnit] = useState("millions USD"),
    [frequency, setFrequency] = useState("weekly");
  const [start, setStart] = useState("2020-01-01"),
    [end, setEnd] = useState(new Date().toISOString().slice(0, 10)),
    [day, setDay] = useState(new Date().toISOString().slice(0, 10)),
    [dimensions, setDimensions] = useState("{}"),
    [rights, setRights] = useState("unreviewed"),
    [interval, setInterval] = useState(12),
    [message, setMessage] = useState(""),
    [busy, setBusy] = useState(false);
  const field = (
    label: string,
    value: string,
    set: (s: string) => void,
    type = "text",
  ) => (
    <label className="text-sm">
      {label}
      <input
        className={input}
        value={value}
        type={type}
        onChange={(e) => set(e.target.value)}
      />
    </label>
  );
  async function acquire(schedule: boolean) {
    setBusy(true);
    setMessage("");
    try {
      const series = {
        id: `${source}:${country}:${id}`,
        source,
        source_id: id,
        name,
        country,
        unit,
        frequency,
        dimensions: JSON.parse(dimensions),
        redistribution: rights,
      };
      if (schedule) {
        await request(
          connection,
          `/schedules/${encodeURIComponent(`${source}-${country}-${id.replaceAll("/", "-")}`)}`,
          "PUT",
          { series, start, interval_hours: interval },
        );
        setMessage(
          "Recurring collection registered. Missed collection slots reconcile when the worker starts.",
        );
      } else {
        const job = await request(connection, "/ingestions", "POST", {
          series,
          scope: {
            start,
            end,
            information_date: day,
            mode: source === "fred" ? "source_vintage" : "forward_capture",
          },
        });
        setMessage(
          `Acquisition queued: ${job.id.slice(0, 12)}. Check Jobs for completion, then refresh the catalog.`,
        );
      }
      await onComplete();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Acquisition failed");
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="space-y-4 rounded-lg border border-border p-5">
      <h2 className="font-serif text-xl">Acquire source evidence</h2>
      <p className="text-sm text-muted-foreground">
        FRED supports explicitly dated vintages and needs FRED_API_KEY in the
        service environment. World Bank, BIS and NY Fed collect current
        responses. Each successful partition becomes an immutable dataset
        version.
      </p>
      <div className="grid gap-3 sm:grid-cols-3">
        <label className="text-sm">
          Source
          <select
            className={input}
            value={source}
            onChange={(e) => setSource(e.target.value)}
          >
            {["fred", "worldbank", "bis", "nyfed"].map((s) => (
              <option key={s} value={s}>
                {s.toUpperCase()}
              </option>
            ))}
          </select>
        </label>
        {field("Source series ID", id, setId)}
        {field("Display name", name, setName)}
        {field("Country (ISO3)", country, setCountry)}
        {field("Source units", unit, setUnit)}
        <label className="text-sm">
          Frequency
          <select
            className={input}
            value={frequency}
            onChange={(e) => setFrequency(e.target.value)}
          >
            {["daily", "weekly", "monthly", "quarterly", "annual"].map((f) => (
              <option key={f}>{f}</option>
            ))}
          </select>
        </label>
        {field("Observation start", start, setStart, "date")}
        {field("Observation end", end, setEnd, "date")}
        {field("Source information date", day, setDay, "date")}
      </div>
      <details>
        <summary className="cursor-pointer text-sm">
          Source dimensions and export rights
        </summary>
        <p className="mt-2 text-xs text-muted-foreground">
          BIS requires the full dotted key and its dimension names. World Bank
          uses a single ISO3 country and source 2 unless specified. NY Fed
          currently supports SOFR.
        </p>
        {field("Dimensions (JSON object)", dimensions, setDimensions)}
        <label className="block text-sm">
          Redistribution status
          <select
            className={input}
            value={rights}
            onChange={(e) => setRights(e.target.value)}
          >
            <option value="unreviewed">Unreviewed</option>
            <option value="personal_only">Personal use only</option>
            <option value="allowed">Reviewed and allowed</option>
          </select>
        </label>
      </details>
      <div className="flex flex-wrap items-end gap-3">
        <button
          disabled={busy}
          className="rounded border border-border px-3 py-2 text-sm disabled:opacity-40"
          onClick={() => acquire(false)}
        >
          Capture this partition
        </button>
        <label className="text-sm">
          Repeat every (hours)
          <input
            className={input}
            type="number"
            min={1}
            max={8760}
            value={interval}
            onChange={(e) => setInterval(Number(e.target.value))}
          />
        </label>
        <button
          disabled={busy}
          className="rounded border border-border px-3 py-2 text-sm disabled:opacity-40"
          onClick={() => acquire(true)}
        >
          Register recurring collection
        </button>
      </div>
      {message && (
        <p className="text-sm" role="status">
          {message}
        </p>
      )}
    </section>
  );
}

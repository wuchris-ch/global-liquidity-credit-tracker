import type { components } from "./research-api";
export type ApiRecipe = components["schemas"]["Recipe"];
import { z } from "zod";

export const rowSchema = z.object({
  date: z.string(),
  value: z.string().nullable(),
  threshold_met: z.boolean().nullable().optional(),
});
export const seriesSchema = z.object({
  id: z.string(),
  name: z.string(),
  source: z.string(),
  country: z.string(),
  unit: z.string(),
  frequency: z.string(),
  information_dates: z.array(z.string()),
  modes: z.array(z.string()),
});
export const resultSchema = z.object({
  unit: z.string(),
  data: z.array(rowSchema),
  operation: z.string(),
});
export const runSchema = z
  .object({
    id: z.string(),
    title: z.string().optional(),
    computed_at: z.string(),
    recipe: z
      .object({
        title: z.string(),
        queries: z.array(
          z.object({
            series_id: z.string(),
            as_of: z.string(),
            basis: z.string(),
            dataset: z.string().nullable().optional(),
          }),
        ),
      })
      .passthrough(),
    result: resultSchema,
  })
  .passthrough();
export type Series = z.infer<typeof seriesSchema>;
export type Run = z.infer<typeof runSchema>;
export type Connection = { base: string; token: string; workspace: string };
export const defaultBase =
  process.env.NEXT_PUBLIC_RESEARCH_API_URL || "http://127.0.0.1:8000";
export async function request(
  c: Connection,
  path: string,
  method = "GET",
  body?: unknown,
  extra?: Record<string, string>,
) {
  const origin = new URL(c.base);
  if (
    origin.protocol !== "https:" &&
    !["localhost", "127.0.0.1", "[::1]"].includes(origin.hostname)
  )
    throw new Error("Remote research connections require HTTPS");
  const idempotent =
    method === "POST" &&
    (path === "/analyses" ||
      path === "/ingestions" ||
      /^\/analyses\/[^/]+\/runs$/.test(path));
  const signal = AbortSignal.timeout(20000);
  const options: RequestInit = {
    method,
    headers: {
      "Content-Type": "application/json",
      "X-Workspace-ID": c.workspace,
      ...(c.token ? { Authorization: `Bearer ${c.token}` } : {}),
      ...(idempotent ? { "Idempotency-Key": crypto.randomUUID() } : {}),
      ...extra,
    },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
  };
  const send = () =>
    fetch(`${c.base.replace(/\/$/, "")}/api/v1/research${path}`, options);
  let response: Response;
  try {
    response = await send();
  } catch (error) {
    if (signal.aborted || (method !== "GET" && !idempotent)) throw error;
    await new Promise((resolve) => setTimeout(resolve, 300));
    response = await send();
  }
  if (!response.ok) {
    const text = await response.text();
    let detail = text;
    try {
      detail = JSON.parse(text).detail || text;
    } catch {}
    throw new Error(
      typeof detail === "string" ? detail : JSON.stringify(detail),
    );
  }
  return response.json();
}
export async function download(c: Connection, id: string, format: string) {
  const r = await fetch(
    `${c.base}/api/v1/research/runs/${id}/export?format=${format}`,
    {
      headers: {
        "X-Workspace-ID": c.workspace,
        ...(c.token ? { Authorization: `Bearer ${c.token}` } : {}),
      },
      signal: AbortSignal.timeout(20000),
    },
  );
  if (!r.ok) throw new Error((await r.json()).detail || "Export failed");
  const url = URL.createObjectURL(await r.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = `research-${id.slice(0, 12)}.${format === "bundle" ? "json" : format}`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export const unitLabel = (unit: string) =>
  ({
    percent_qoq_saar: "% growth, annualized quarter over quarter",
    percent: "percent",
    zscore: "standard deviations",
  })[unit] || unit;

import { Suspense } from "react";
import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { ReleaseLaboratory } from "@/components/release-laboratory";

export const metadata = {
  title: "Release Laboratory | Macro Research",
  description:
    "Explore economic releases, compare archived information dates and replay research from verified source captures.",
};

export default async function ReleaseLabPage() {
  // Preserve the source's numeric text. Turbopack 16.3.5 rewrites some long
  // decimal literals in JSON modules, invalidating content-addressed bundles.
  const directory = join(process.cwd(), "public", "research", "lab");
  const [studyJson, releaseJson] = await Promise.all([
    readFile(join(directory, "study.json"), "utf8"),
    readFile(join(directory, "feed.json"), "utf8"),
  ]);
  return (
    <Suspense>
      <ReleaseLaboratory studyJson={studyJson} releaseJson={releaseJson} />
    </Suspense>
  );
}

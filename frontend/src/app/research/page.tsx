import { Suspense } from "react";
import { researchEnabled } from "@/lib/research-availability";
import { PublicResearch } from "@/components/public-research";

export const metadata = {
  title: "Research Atlas | Global Liquidity & Credit",
  description:
    "Explore real GDP, payroll and industrial production revisions with historical source snapshots, interactive comparisons and downloadable evidence.",
};

export default async function ResearchPage() {
  if (researchEnabled) {
    const { default: ResearchWorkbench } = await import(
      "@/components/research-workbench"
    );
    return <ResearchWorkbench />;
  }
  return (
    <Suspense
      fallback={
        <main className="mx-auto max-w-6xl px-8 py-12">
          <h1 className="font-serif text-4xl">Research atlas</h1>
          <p className="mt-4">Loading the published evidence collection…</p>
        </main>
      }
    >
      <PublicResearch />
    </Suspense>
  );
}

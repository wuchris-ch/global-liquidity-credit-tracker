import { Suspense } from "react";
import { PublicResearch } from "@/components/public-research";

export const metadata = { title: "Research Atlas | Global Liquidity & Credit" };

export default function AtlasPage() {
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

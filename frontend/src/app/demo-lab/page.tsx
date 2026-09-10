import type { Metadata } from "next";
import { ConceptLab, type Concept } from "@/components/demo/concepts/concept-lab";

export const metadata: Metadata = { title: "Five directions · Adversary", description: "Five animated directions for the live monitor." };

export default async function DemoLabPage({ searchParams }: { searchParams: Promise<{ view?: string }> }) {
  const { view } = await searchParams;
  const concepts = ["breach", "wiretap", "counterplay", "casefile", "orbit"];
  return <ConceptLab initialConcept={concepts.includes(view ?? "") ? view as Concept : "breach"} />;
}

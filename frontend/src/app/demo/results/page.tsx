import type { Metadata } from "next";
import { ResultsExplorer } from "@/components/demo/results-explorer";

export const metadata: Metadata = {
  title: "Results · Adversary",
  description: "Model failure descriptions and supporting evidence.",
};

export default function ResultsPage() {
  return <ResultsExplorer />;
}

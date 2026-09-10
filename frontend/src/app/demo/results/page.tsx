import type { Metadata } from "next";
import Link from "next/link";
import { ChevronRight } from "lucide-react";

import styles from "@/components/demo/story-replay.module.css";

export const metadata: Metadata = {
  title: "Results · Adversary",
  description: "Model failure descriptions and supporting evidence.",
};

// Route scaffold. Choose the results presentation with the user before building the explorer.
export default function ResultsPage() {
  return (
    <div className={`${styles.replay} motion-page-enter`}>
      <div className={styles.breadcrumb}>
        <Link href="/demo">Live monitor</Link>
        <ChevronRight size={16} aria-hidden="true" />
        <h1>Results</h1>
      </div>
    </div>
  );
}

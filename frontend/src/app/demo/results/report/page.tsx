import type { Metadata } from "next";
import Link from "next/link";
import { ArrowLeft, ArrowUpRight, Check, ChevronRight, CircleAlert } from "lucide-react";
import { RUN } from "@/lib/demo/run-data";
import monitorStyles from "@/components/demo/story-replay.module.css";
import styles from "./report.module.css";

export const metadata: Metadata = {
  title: "Final report · Adversary",
  description: "A brief summary of Astra's observed strengths and failures under adversarial guidance.",
};

export default function FinalReportPage() {
  const localeFailures = RUN.cases.filter(item => item.mode.id === "lost-locale").length;
  const asyncPasses = RUN.cases.filter(item => item.taskKey === "django__asgiref-523" && item.perturbed.outcome === "passed").length;
  const factoryPasses = RUN.cases.filter(item => item.taskKey === "factoryboy__factory_boy-1067" && item.perturbed.outcome === "passed").length;

  return <div className={`${styles.report} motion-page-enter`}>
    <div className={monitorStyles.breadcrumb}>
      <Link href="/demo/results">Results</Link><ChevronRight size={16} aria-hidden="true" /><h1>Final report</h1>
    </div>
    <article>
      <header className={styles.header}>
        <p className={styles.eyebrow}>Astra · low reasoning</p>
        <h2>Astra under adversarial guidance</h2>
        <p>{RUN.summary.caseCount} paired runs across {RUN.summary.distinctTasks} repair tasks.</p>
        <div className={styles.counts}>
          <span><CircleAlert size={13} aria-hidden="true" />{RUN.summary.failureCount} failed</span>
          <span><Check size={13} aria-hidden="true" />{RUN.summary.resistedCount} passed</span>
        </div>
      </header>
      <section className={styles.section}>
        <h3><CircleAlert size={15} aria-hidden="true" />Where Astra struggled</h3>
        <p>Misleading compatibility guidance steered Astra toward fixes that looked correct but left deeper behavior broken. In {RUN.summary.failureCount} attacked runs, the repairs passed the original tests while failing declaration-default and override checks; {localeFailures} also failed to preserve configured locales.</p>
      </section>
      <section className={styles.section}>
        <h3><Check size={15} aria-hidden="true" />Where Astra succeeded</h3>
        <p>Astra passed every recorded check in {RUN.summary.resistedCount} attacked runs across {RUN.summary.distinctTasks} tasks. These included {asyncPasses} async local storage runs and {factoryPasses} Factory Boy runs that preserved declaration context, plus successful repairs involving linked argument validation, linter messages, nested command completion, category filters, and subclass construction.</p>
      </section>
      <section className={styles.section}>
        <h3><ArrowUpRight size={15} aria-hidden="true" />Training a stronger model</h3>
        <p>These paired examples can guide training toward successful repairs and away from the observed failure patterns. The same behavior checks can then test whether the next model improves under adversarial guidance.</p>
      </section>
      <footer className={styles.footer}>
        <p>Every pair has a passing clean control. Counts include repeated executions and reflect the recorded diagnostic checks. Explore the evidence for the exact guidance, repairs, and test outcomes.</p>
        <Link href="/demo/results"><ArrowLeft size={13} aria-hidden="true" />Explore the evidence</Link>
      </footer>
    </article>
  </div>;
}

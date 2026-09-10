import type { RUN, TestOutcome } from "./run-data";

export type ResultExample = (typeof RUN.cases)[number];

export type ResultMode = {
  key: string;
  id: string;
  label: string;
  outcome: TestOutcome;
  examples: ResultExample[];
};

/** Count attacked runs once, independently of their control or follow-up outcomes. */
export function groupResultModes(examples: readonly ResultExample[]) {
  const grouped = new Map<string, ResultMode>();
  for (const example of examples) {
    const outcome = example.perturbed.outcome;
    const key = `${outcome}:${example.mode.id}`;
    const group = grouped.get(key);
    if (group) group.examples.push(example);
    else grouped.set(key, { ...example.mode, key, outcome, examples: [example] });
  }
  // Stable insertion order resolves ties, preserving the supplied category order.
  const ranked = [...grouped.values()].sort((a, b) => b.examples.length - a.examples.length);
  return {
    failed: ranked.filter((mode) => mode.outcome === "failed"),
    passed: ranked.filter((mode) => mode.outcome === "passed"),
  };
}

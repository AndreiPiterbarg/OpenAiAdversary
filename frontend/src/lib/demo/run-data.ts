import recorded from "./recorded-run.json" with { type: "json" };

// Display data is generated from verified clean/attack pairs; raw evidence stays linked per run.
export type TestOutcome = "passed" | "failed";
export type StoryBlock =
  | { kind: "text"; text: string }
  | { kind: "code"; label: string; text: string; stream?: boolean }
  | { kind: "checks"; rows: { label: string; detail: string; status: "passed" | "rejected" | "unavailable" }[] }
  | { kind: "comparison"; arms: { label: string; outcome: "passed" | "failed"; text: string; code: string }[] }
  | { kind: "finding"; text: string; detail: string };

export type StoryStep = {
  id: string;
  title: string;
  role: string;
  blocks: StoryBlock[];
};

export type CaseInput = {
  sourceId: string;
  taskKey: string;
  storyContext: string;
  injectedText: string;
  checks: { label: string; detail: string; status: "passed" | "rejected" | "unavailable" }[];
  record: { arm: string; attackLabel: string; condition: string; repetition: number; model: string; adversary: string; steps: number; attackToolCalls: number; cleanToolCalls: number; failedChecks: number; passedChecks: number; testCount: number; controlId: string; evidenceUrl: string; evidenceLevel: string; createdAt: number | null };
  id: string;
  mode: { id: string; label: string };
  title: string;
  repository: string;
  channel: string;
  context: string;
  seed: string;
  hypothesis: string;
  program: string;
  boundary: string;
  comparison: string;
  control: { outcome: TestOutcome; text: string; code: string; output: string };
  perturbed: { outcome: TestOutcome; text: string; code: string; output: string };
  finding: string;
  mechanism: string;
};

function makeCase(input: CaseInput) {
  return {
    ...input,
    steps: [
      {
        id: "mine", title: "Task context", role: "history",
        blocks: [
          { kind: "text", text: input.context },
          { kind: "code", label: "Repair task", stream: false, text: input.storyContext },
        ],
      },
      {
        id: "generate", title: "Attack program", role: "adversary",
        blocks: [
          { kind: "text", text: input.hypothesis },
          { kind: "code", label: "Added to the tool response", text: input.injectedText },
          { kind: "text", text: input.boundary },
        ],
      },
      {
        id: "compare", title: "Agent test", role: "scoring",
        blocks: [
          { kind: "text", text: input.comparison },
          { kind: "comparison", arms: [
            { label: "Without attack", ...input.control },
            { label: "With attack", ...input.perturbed },
          ] },
        ],
      },
      {
        id: "confirm", title: "Evidence checks", role: "target",
        blocks: [
          { kind: "text", text: "Verify that the guidance reached Astra and that the clean comparison is valid." },
          { kind: "checks", rows: input.checks },
        ],
      },
      {
        id: "takeaway", title: "Finding", role: "finding",
        blocks: [
          { kind: "finding", text: input.finding, detail: input.mechanism },
        ],
      },
    ] satisfies StoryStep[],
  };
}

export const RUN = {
  identity: { id: "astra-worker-evidence-20260910", schemaVersion: "2", source: "recorded" as const },
  summary: recorded.metadata,
  models: [
    { id: "adversary", name: "Astra" },
    { id: "scoring", name: "Astra · low reasoning" },
    { id: "target", name: "Fresh test replay" },
  ],
  roles: [
    { id: "history", label: "Task context", modelId: null },
    { id: "adversary", label: "Adversary", modelId: "adversary" },
    { id: "scoring", label: "Coding agent", modelId: "scoring" },
    { id: "target", label: "Evidence checks", modelId: "target" },
    { id: "finding", label: "Finding", modelId: null },
  ],
  cases: (recorded.cases as CaseInput[]).map(makeCase),
};

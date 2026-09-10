# Final results presentation — phase two plan

This is the independently planned results experience for `OpenAiAdversary/frontend`. Build the demo first. The results work below is deferred except for the shared snapshot identifiers, provenance, and handoff contract the demo needs now.

The strongest presentation is a complete, searchable case index beside an evidence inspector. The viewer should understand the specific failure before opening a trace, then be able to inspect exactly what changed and how the result was judged. Retain the frontend's quiet dark surfaces, restrained headings, semantic chips, and short entry motion. Results should be stable and immediately readable; the terminal performance belongs to the preceding replay.

Evidence labels: `[REPO]` means inspected in the actual frontend during this planning pass; `[V]` means the linked primary source was fetched and read; `[CARRIED]` means context from the original prompt or coordinating agent, not a new backend verification; `[COMPUTED]` means arithmetic derived from the shown inputs. All proposed routes, layouts, types, fixtures, and acceptance criteria below are design recommendations, not claims about implemented behavior or measured runs. The shared schema and handoff authority is [frontend/prompts/P-DEMO.md](../../prompts/P-DEMO.md).

## 1. What exists and what to reuse

The inspected frontend contains an image-oriented `SummaryPage`, `DashboardShell`, `DashboardListPage`, and shared motion utilities. The shell has a maximum outer width of 1200px, a 156px navigation column, a 64px desktop gap, and a results section capped at 936px. The title is `text-2xl font-light`; normal copy is `text-sm`. Cards use `rounded-[8px] border border-[#222222] bg-[#1a1a1a] p-6`, with 2px corners for small insets. `[REPO]`

The actual body inherits the existing sans-serif stack: the layout declares Geist font variables but neither the Tailwind configuration nor global CSS applies those variables as the body font family. Preserve that rendered style rather than introducing a global font change to satisfy the older prompt's description. Use a deliberate monospace face only for code, identifiers, and compact trace fields. `[REPO]`

Read these files when implementing:

- `src/components/dashboard/dashboard-shell.tsx`: outer layout, navigation, header.
- `src/components/dashboard/dashboard-list.tsx`: cards, labels, exact semantic chip colors.
- `src/components/dashboard/summary-page.tsx`: heading rhythm, cards, segmented filters, buttons.
- `src/app/globals.css`: page ground, motion durations/easings, reduced-motion behavior.
- `src/app/layout.tsx` and `tailwind.config.ts`: actual font inheritance.

The current summary keeps only the first 20 failed and first 20 passed scenarios in the inspectable arrays, and assigns each passed scenario's expected response to its displayed model response. Its remaining-count tile is not an access path to omitted cases. These are inappropriate behaviors to carry into a complete software-agent evidence browser. Its timed loading screen also has no purpose in front of a locally available completed snapshot. `[REPO]`

Build new route-local results components. Consume the shared design language without copying the legacy image assumptions, modifying the global palette, or rewriting the old vision summary as part of this phase.

## 2. Information design and research

Langfuse's experiments interface supports aggregate scores alongside comparison of experiment results; its data model links a run item to the input item and trace, with expected output separate from observed output. That supports an overview followed by a directly inspectable case, while keeping the evidence objects distinct. It does not establish that any particular layout is universally optimal. `[V]` [Experiments via UI](https://langfuse.com/docs/evaluation/experiments/experiments-via-ui), [Experiments data model](https://langfuse.com/docs/evaluation/experiments/data-model).

Our design inference is to make the case the main unit of navigation and the mechanism a grouping/filter. A failure total answers how often something was observed; a mechanism description answers what the adversary discovered. A thumbnail gallery is a poor fit for code edits, verifier output, and trajectories because the decisive information is textual and relational.

Langfuse separately documents versioned dataset snapshots and schema validation. Use the same underlying principles here: give the completed artifact a stable identity, validate it once, and derive both the stage narrative and results from that identity. No Langfuse integration or dependency is proposed. `[V]` [Datasets: versioning and schema enforcement](https://langfuse.com/docs/evaluation/experiments/datasets).

Expandable evidence should use ordinary disclosure controls with keyboard activation and accurate expanded state. W3C's disclosure pattern documents those requirements. W3C's reflow guidance supports a reading layout that does not require horizontal page scrolling; an intrinsically wide code fragment can have its own scroller. `[V]` [Disclosure pattern](https://www.w3.org/WAI/ARIA/apg/patterns/disclosure/), [Reflow](https://www.w3.org/WAI/WCAG22/Understanding/reflow.html).

These sources inform the interaction and record design. They are not evidence that this project's adversary has produced failures, achieved transfer, or established causality.

## 3. First screen: answer what happened

At `/demo/results?run=<snapshot-id>&case=<featured-case-id>`:

1. Show the existing shell and a light `Final results` heading. Keep the provenance badge visible beside the run identity: `EXAMPLE DATA` for `proxy`, `RECORDED RUN` for `recorded`, or `MIXED DATA` for `mixed`. Include a secondary `Back to demo` link and an `Export` action.
2. Show a short scope line naming the target model, the dataset/source scope, and the completed snapshot timestamp when available. Do not invent completion times for fixtures.
3. Use a compact overview with `Failures`, `Passed`, `Unresolved`, and `Modes with evidence`. Add explicit denominators or definitions under the numbers. When the imported evidence cannot support the final item, show `Not established` instead of zero.
4. Provide the complete case workspace immediately below. The demo always passes its featured case by stable ID, so the viewer arrives at the same evidence just described on stage. A results URL without `case` opens the index only, with no implicit case selection.

Keep the headline factual: `Failures observed in this snapshot` is safer than `The model is vulnerable`. Even an observed pass-control/fail-perturbed pair needs valid pairing and verification before a stronger attribution label is appropriate.

The overview describes the whole snapshot. Filters affect the workspace and its visible-count line, not those global totals. Label the workspace count `Showing … matching cases` so filtering cannot silently change the meaning of the run summary.

### Counts that mean one thing each

Define these units in the normalized artifact and UI help text:

| Unit | Meaning | Do not substitute |
|---|---|---|
| Proposal | One candidate perturbation program submitted for admission | A model failure or discovered mode |
| Mode | A named proposed mechanism, with an explicit evidence status and grouping basis | Every rejected proposal or every failed episode |
| Task instance | A task at its declared repository/base commit and source split | An episode count |
| Case | One task/perturbation/model comparison context, identified independently of retries | Unique repository count |
| Episode/arm | One recorded execution under control or perturbed conditions | An independent new case |

If the artifact has only episode records and no trustworthy pairing/case identity, say `Episode outcomes` and report episode denominators. Do not have the browser manufacture independent cases by positional matching. Multiple trials of a case remain multiple trials, and the case-level verdict follows an explicit imported aggregation rule; mixed outcomes can remain unresolved.

Admission statistics belong in an expandable `Pipeline accounting` section: proposed, parsed, admitted, rejected, unreached, and reasons where available. Admission success is not target failure. Do not promote proposal parsing/admission percentages into capability results. This distinction follows the original P-DEMO context. `[CARRIED]`

For any percentage, expose numerator, denominator, unit, subset, and aggregation rule. Never divide by all proposals when the numerator describes target episodes. Do not compute confidence intervals in the browser unless the import declares the statistical method and its valid unit; descriptive counts are enough for this release.

## 4. The case workspace

### Layout within the actual shell

At the full 936px content width, a proposed 288px index plus 24px gap leaves 624px for detail before panel padding: `936 - 288 - 24 = 624`. `[COMPUTED]` This accommodates a readable text inspector, but not two substantial code editors side by side.

Use the split layout only where the content region has enough width, approximately a 1280px viewport with the current shell. At narrower widths, show an index view and a selected-case view with an explicit `Back to cases` link that restores filters and list position. Test the actual rendered width before fixing the breakpoint.

Within the desktop detail panel, put brief control and perturbed verdict summaries next to each other. Stack the full expected behavior, actual evidence, and patch sections. Offer `Expand evidence` to give a selected case the entire 936px content width. Only that expanded view should consider paired code columns, and even there a unified patch is the default for long lines.

Use normal page scrolling initially. Avoid nesting independently scrolling list, inspector, trace, and code panes. The index may become sticky if the viewport has enough height, but focused items and final actions must remain reachable. Sticky behavior is optional and should not complicate the first delivery.

### Search, grouping, filtering, and order

- Search over case ID, repository, task title, mode name, and verifier summary. Use a visible label, clear action, and empty-result reset. Searching full raw traces can wait until there is a concrete need.
- When a direct case link omits `status`, select an outcome filter that includes that case (or `All`); the featured failed case therefore opens the failed-case view, while passed/unresolved links remain visible. Without a `case` or explicit filter, show the complete index under `All`. Keep `All`, `Failed`, `Passed`, and `Unresolved` controls visible with counts. Unreached or infrastructure-error episodes have their imported unresolved status and reason, never an inferred confirmed-failure label.
- Add compact filters for model, mode, and evidence status. Additional filters such as channel, split, and repository can sit in an expandable filter row if the real artifact has useful values.
- Group by mode only when the artifact supplies a grouping. Include an explicit unassigned group; do not silently drop unclassified cases. Show counts of cases and repositories separately. Distinguish a proposed mode label from held-out confirmation.
- Each index row contains a concrete failure title, repository/task identity, control-to-perturbed verdicts, and one evidence status. Avoid dense columns that require reading a legend.
- Default ordering is deterministic: the featured case first on demo entry, then imported evidence strength and stable ID. Provide repository and outcome sorts. Do not invent severity rankings when the artifact has none.
- Render a reachable path to every case. Start with straightforward client-side pagination rather than virtualization; choose page size during visual implementation. Display an explicit range, total, and working previous/next controls. Never show a noninteractive ellipsis as a substitute for the remainder.

### Detail hierarchy: evidence before raw logs

| Order | Section | Content |
|---|---|---|
| First | What failed | A short observed-behavior sentence, case ID, target model, and evidence status |
| First | Task and expected behavior | The original task and the relevant acceptance criterion; exact expected output only if supplied |
| First | Control / perturbed outcome | Verdict, test/criterion result, and execution health for each arm; absent arms explicitly unavailable |
| Next | What changed | Declared channel, exact touched file/range, before/after or unified diff, and clause boundaries |
| Next | Why this is marked failed | Verifier identity/version, raw assertion or test result, and the imported outcome reason |
| Expandable | Trace | Observed tool calls, relevant outputs, final patch/output, and links to related evidence |
| Expandable | Mode and corroboration | Proposed mechanism, evidence status, repetitions, held-out sources, models, and unresolved counterexamples |
| Expandable | Provenance | Snapshot identity, artifact reference/digest, base commit, seed, model/config, pair/trial identity, and missing fields |

Always distinguish `Expected behavior` from `Observed output`. An unavailable output is unavailable; it must never be filled from the expected field, a canned response, or a successful sibling case.

The first visible trace excerpt should jump to a recorded relevant step when one exists. Label it `First recorded divergence` only if there is an explicit evidence-backed alignment between control and perturbed traces. A first differing line is not automatically the cause of a failure. Otherwise use `Relevant observed step` with an explanation of who selected it. Do not expose or invent hidden chain-of-thought; the trace is tool activity and outputs supplied in the artifact.

Raw code and outputs are inert, copyable text. Render them escaped; never execute a program or inject HTML from the artifact. Normal navigation should keep the selected case visible. Opening a trace disclosure should not change case selection or rerun a reveal animation.

### Outcome, execution health, and evidence strength are separate

Use three distinct concepts in both data and wording:

- **Outcome:** passed, failed, unresolved. This is what the declared evaluator could determine.
- **Execution health:** completed, truncated, error, unreached, or unknown, plus recorded reason/stage. A completed run can contain unresolved cases.
- **Evidence status:** an imported or reviewed statement such as observed failure, valid paired contrast, or held-out confirmed mode. These require their own criteria and references.

A treatment failure with a missing control is still an observed failure if the verifier establishes it, but it is not an established contrast. A failed control and failed treatment do not demonstrate an induced failure. A successful gate indicates that the gate accepted the proposal; it says nothing by itself about downstream target behavior.

Retain the existing green, yellow, and cyan styles. Green can indicate a recorded pass, yellow a recorded failure/rejection, and cyan provenance/evidence metadata, always with a literal text label. Use neutral unresolved rows with a reason rather than adding a new red/yellow/green severity system. The meaning of a chip must be clear from its label and section, not just its color.

## 5. Routing and the demo handoff

Use `/demo` and `/demo/results` under a route-local layout that consumes the existing `DashboardShell`. The demo's results URL contains `run` and `case`; it never depends on which replay happens to be active at click time. The primary CTA destination is fixed by `RUN.identity.id` and `RUN.story.featuredCaseId`. A direct results URL without `case` opens only the index. `[CARRIED]`

The demo's `Go to final results` CTA appears after the first complete replay and stays available during every subsequent replay. Going to results stops/unmounts the visual player and renders the immutable snapshot immediately. No artificial processing sequence, socket, backend evaluation, or trace playback is needed.

Persist the first-pass-completed latch with the snapshot ID and artifact revision in guarded session state so returning from results does not hide the CTA. Store replay position separately from artifact data and restore the player paused on return. An explicit new-artifact reset clears the latch; replaying the same snapshot does not change its counts. Direct results access never requires this latch or working session storage.

Proposed query keys beyond the shared `run` and `case` contract: `status`, `mode`, `model`, `q`, `sort`, `page`, and optional `view=evidence`. Keep query values validated against the imported records. A requested case with no explicit status filter determines an inclusive default; a direct link must not hide its passed or unresolved case behind a default failed filter. Unknown run IDs produce an explicit unavailable-snapshot state; unknown case IDs produce `Case unavailable` with a link to that run's index, never a silent substitution that changes the shared claim.

Use navigation history for intentional case selections and view changes. Replace history for search typing so Back does not walk through each letter. Preserve filter/query state while opening details and expanding evidence. If a filter excludes the selected case, clear the selection and show the filtered index; do not keep invisible stale context. An explicit `Back to cases` restores the workspace state. The browser Back button should return to the prior meaningful selection and eventually to the demo.

At mobile widths, move focus to the case heading after opening detail and return it to the originating row when going back. Desktop case links remain normal keyboard-operable navigation; selected state is also visible in text/semantics. Disclosure buttons use the W3C behavior referenced above. Keep essential prose above the compact identifier metadata.

## 6. Minimal shared contract to establish during DEMO FIRST

This is a proposed normalized frontend contract, not an existing export schema in OpenAiAdversary. Backend facts carried from the coordinator include episode arm/model/outcome fields, `realised`, `planted`, `truncated`, unreached stage/reason, and trajectory errors. Their exact mapping must be verified against the real export when it arrives. `[CARRIED]`

The demo only needs these boundaries established now:

```ts
type SnapshotIdentity = {
  id: string;                   // stable URL identity
  schemaVersion: string;
  revision: string;             // artifact revision; also scopes playback state
  source: "proxy" | "recorded" | "mixed";
  recordedAt: string | null;
  recordedDurationMs: number | null; // original run duration, not replay timing
};

type RunSnapshot = {
  identity: SnapshotIdentity;
  models: ModelRecord[];        // stable IDs, display names/config as supplied
  roles: RoleRecord[];          // role-to-model references, distinct from models
  cases: CaseRecord[];
  modes: ModeRecord[];
  proposals: ProposalRecord[];  // may be empty when admission data is not exported
  claims: ClaimRecord[];        // supported claims, limitations, and source references
  story: ReplayStory;
  sections: SectionProvenance[];
};

type CaseRecord = {
  id: string;
  task: TaskIdentity;           // source/split, repo/base commit, input, expected behavior
  title: string;
  modeId: string | null;
  modelId: string;
  perturbation: PerturbationEvidence | null;
  episodes: EpisodeRecord[];    // IDs, arm, trial, health, outcome, verifier, observed trace/output
  pairing: PairingEvidence | null;
  outcome: "passed" | "failed" | "unresolved";
  outcomeReason: string;
  aggregationRule: string | null;
  evidenceStatus: EvidenceStatus;
  evidenceRefs: string[];
  provenance: Provenance;
};

type ReplayStory = {
  featuredCaseId: string;
  replayCaseIds: string[];      // deterministic supplemental replay order
  beats: ReplayBeat[];         // timing/excerpts refer to evidence by stable ID
};
```

The undeclared types above are conceptual field groups to refine against the actual producer, not a demand to implement an exhaustive schema in phase one. The main P-DEMO brief owns the shared `RUN` schema; this sketch reserves results needs and uses its shared names. Agree stable IDs, explicit missing values, per-section provenance, model roles, and separation of source records from playback events now. Keep playback timing and presenter wording in `RUN.story`, separate from recorded evidence. Never mutate imported records in the browser when selecting, filtering, replaying, or exporting.

Use one checked-in fixture source for proxy results and derive story references from it. Swapping the selected imported constant must update both screens consistently. When a real source format arrives, add one explicit adapter in the frontend rather than rewriting each component to understand that raw format. Do not read directly from unrelated Python files at runtime or add backend work to the frontend task.

`RUN.identity.source` summarizes the imported evidence as `proxy`, `recorded`, or `mixed`; setting it to `recorded` cannot certify invented fixture text. Validate that the badge agrees with evidence and section provenance, and keep mixed or absent evidence visibly qualified. `RECORDED RUN` describes the source of the artifact, not causal certainty or experimental completeness. A complete artifact may report a partial experiment: snapshot completeness and scientific scope are separate fields.

## 7. Fixtures that actually exercise the design

Use clearly invented local repository/task names, synthetic outputs, and visible `EXAMPLE DATA`. Do not attach invented messages to a real model as if they were captured outputs. The model-role cards can show planned roles while the evidence explicitly says `Illustrative transcript`.

Candidate fixture stories, all illustrative:

| Case | Visible evidence | Why include it |
|---|---|---|
| Stale migration guidance leads to an obsolete import | A changed guidance file, an untouched implementation contract, a failed import assertion, and a passing control | Concrete edit-to-observation story with compact patch and verifier |
| Misleading test location leaves the actual regression unfixed | A declared-channel metadata change, visited files, final patch, and the still-failing required test | Shows a trajectory failure without relying on a final natural-language answer |
| Similar package names redirect the edit to the wrong module | Exact changed context, patch file path, and the acceptance test for the intended module | Gives the inspector useful file/path evidence |
| Perturbed run passes | Distinct actual recorded-style output and passing verifier | Prevents expected-output substitution and supports comparison |
| Control fails as well | Two failed verdicts with an explicit attribution limitation | Prevents every failure becoming a claimed induced failure |
| Missing control or truncated target trace | Available partial evidence plus unresolved reason | Exercises honest missing-data behavior |
| Rejected draft | Gate reason and absent target execution | Exercises accounting without inflating failure counts |

The eventual fixture must also contain a long title, long code lines, an unassigned mode, a missing trace, repeated trials with mixed outcomes, and more cases than fit on the first page. Counts should derive from those records. Do not invent headline totals independently for visual impact.

## 8. Import validation, export, and unresolved states

Validate stable IDs and references; reject duplicate identities and dangling featured-case IDs. Verify that model/mode references exist, pairs belong to compatible contexts, and any declared case aggregation can be explained. Do not equate `null`, zero, absent, and not reached.

Validate headline totals against the normalized units. Pass/fail/unresolved partition only the population explicitly included in that outcome summary. Preserve unreached stages, truncated traces, verifier failures, and exclusions with reasons; they must not disappear during normalization. Do not infer pair correspondence from array order or a shared task title.

If a completed artifact contains a raw failure verdict with an inconsistent verifier field, show an explicit artifact/evidence inconsistency and preserve the original recorded values. Do not rewrite its verdict, relabel it as an imported unresolved case, or silently include it as validated evidence. Validation state is a separate presentation concern; resolving the contradiction requires a corrected artifact. The browser has no verdict-editing or result-reclassification action.

Offer two local downloads once results are implemented: the original imported snapshot with provenance, and a clearly labeled filtered case export. Include run ID, schema version, scope/filter state, raw outcome, evidence status, health/reason, and source references. A copied case link includes run/case identity. Do not add writeback, reclassification, or remote sharing features during the initial read-only presentation phase.

Distinguish these visible states: no recorded cases; no cases matching filters; requested case unavailable; evidence section not provided; incompatible artifact; artifact failed to load. Show actionable reset/back/download choices when possible. A missing statistic reads `Not recorded` rather than zero, and a missing trace does not turn into fake loader activity.

## 9. Delivery order and acceptance

**During phase one, DEMO FIRST:** agree the shared run/case route contract, provenance and featured-case identity; define the fixture/story separation; preserve the first-pass latch and pinned CTA destination. The complete inspector, filters, exports, and result aggregates are phase two. Do not reduce the demo work to prematurely implement this full browser.

**First phase-two slice:** the stable results route; factual scope and counts; complete case index; selected detail; exact perturbation; paired summaries where valid; expected/observed/verifier separation; unresolved/provenance states; reliable Back/deep links; responsive and keyboard behavior.

**Second phase-two slice:** mode grouping and corroboration, expandable trace with evidence-backed jump point, full-width evidence view, local exports, and large-data pagination polish. Add charts only if real records create a question that a list or compact table cannot answer. A causal graph, model leaderboard, animated heatmap, or radar chart is not needed to make the initial findings useful.

Acceptance should exercise actual user tasks and scientific distinctions:

- Complete the first demo replay; enter results during a later replay; arrive at the first story's pinned case with matching snapshot provenance.
- Open copied failed, passed, and unresolved run/case URLs directly without a status filter; each requested case remains visible. Open a run URL with no case and confirm only the index appears. Refresh; use Back/Forward; change filters; clear search; reach a case beyond the initial page.
- Inspect expected and actual output for passed cases and confirm they remain distinct source fields.
- Compare missing-control, failed-control, truncated, unreached, mixed-trial, and genuinely paired examples; ensure none silently acquires a stronger claim.
- Trace each headline value to an explicit population and rule; confirm filtering preserves global context and reports its own subset.
- Open disclosures with a keyboard, use the case index at narrow width and zoom, and verify no horizontal page overflow. Code scrolling stays within evidence blocks.
- Replace the fixture with a differently sized valid snapshot and verify stable references, missing sections, labels, totals, selection, and export.
- Keep all changed and staged files beneath `frontend/`. This research document makes no backend change and does not request a commit outside that boundary.

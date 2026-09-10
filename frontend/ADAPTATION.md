# Adapting the extracted frontend

This dashboard was lifted verbatim from `AndreiPiterbarg/MistralAdversarial`, an unrelated vision
and driving project. `node_modules` and `.next` were removed and nothing else was touched, so
`README.md`, the package name and the root layout title all still describe the archive. This note
records what is in the tree and what it would take to point it here. It changes nothing.

## What is here

Eleven files under `src/app`, nine dashboard components totalling 1,812 lines. The routes are `/`
(a marketing landing page with Mistral branding and vision copy), `/dashboard` (a redirect),
`/dashboard/projects`, `/dashboard/projects/new` with its `test-suite`, `summary` and `fine-tuning`
children, `/dashboard/models` and `/dashboard/loading-lab`; `dashboard/layout.tsx` is a pass-through
and there are no API routes. `DashboardShell` gives a sidebar of Projects, Models and Datasets,
where Datasets links to `/dashboard/datasets`, which does not exist. Both list screens are
`DashboardListPage` over hard-coded arrays in the route files.

The wizard runs new, test-suite, summary, fine-tuning, in that order — summary comes before
fine-tuning, not after. The only state surviving a step is the project name, passed as a
`?projectName=` query parameter; every other selection is local component state discarded on
navigation. Step one offers Project name, Model, Dataset, Attack profile (object detection,
semantic segmentation, image classification) and Run budget (Quick 10 min through Extended
120 min). Step two offers four toggleable cards — Environmental stress, Sensor degradation,
Semantic edits, Document corruption — each a static list of perturbation names. Step three shows
four stat cards (Base accuracy, Base response latency, Attack degradation rate, Attack response
latency), an Attacks panel with Strongest and Weakest top-five lists, and a Scenarios panel with a
failed/passed toggle, at most twenty thumbnails and a lightbox. Step four shows "Without attacks"
and "With attacks" metric grids for original against fine-tuned, an effectiveness comparison table,
and a terminal "Use fine-tuned model" button. `/dashboard/loading-lab` previews the loader only.

Data reaches the UI through exactly two `fetch` calls, both to static files under `public/`:
`/data/frontend_data.json` (233 KB; keys `stats`, `attack_ranking`, `failed_scenarios`,
`passed_scenarios`) and `/data/comparison_frontend_data.json` (4.6 KB; keys `comparison`,
`original`, `finetuned`). Both loaders are timers, not progress: `ProcessingLoader` counts to a
fixed 5,200 ms and 5,600 ms regardless of what is happening underneath.

The stack is Next.js App Router, TypeScript in strict mode, Tailwind 3, and a shadcn/ui
configuration with exactly one vendored component, `src/components/ui/button.tsx`. `package.json`
pins `next`, `react`, `react-dom` and `eslint-config-next` to `latest`, so its declared versions
mean nothing; `package-lock.json` resolves next 16.1.6 — not 15 — react and react-dom 19.2.4,
tailwindcss 3.4.19 and typescript 5.9.3 across 448 entries, none of it reviewed.

## Where the shape fits, and where it does not

Step one fits in shape, not vocabulary. Choosing a target and a task pool is a real step here, but
Model would have to become a `TargetPin`, most of whose fields are unpinnable for Astra, and
Dataset a pinned task pool under `data/tasks/` plus held-out corpora under `data/corpora/`. Attack
profile has no counterpart and should be deleted rather than renamed.

Step two is the worst fit and should not be preserved. A menu of named perturbations is exactly the
selection from a table that `prototype/PLAN-RUN.md` says the loop is not: the adversary writes
generator and checker programs, admitted by `StaticCritic` inside a `CriticChain`. Its real
successor is a probe browser over `data/probes/` showing each probe's hypothesis, cell, provenance,
shippability and kill record: what was written, not what to run.

Step three is the closest fit. The ranked lists correspond to the atlas's `hot_cells` and its
`ranking` by importance, and the stat cards could carry excess over additive across the k+2 cells.
But the failed/passed toggle is what D10 forbids: the store also holds `unreached.jsonl` with a
stage per row and episodes whose perturbation never applied, and an unwitnessed row is unknown
rather than a zero and stays in the denominator. A binary toggle over twenty thumbnails cannot
express that ledger, and the not-reached section belongs on the same screen, not behind a tab.

Step four does not fit leg one at all. Astra cannot be LoRA'd, so repair is leg two on Qwen3-8B, and
the claim page records the post-training proof runs as withheld pending hardware. The screen omits
everything that makes a repair shippable: the non-regression suites with their equivalence
intervals, the honesty probe, `ProofResult.ships`, and the fix set's seeds, pool, recovery model and
verifier. A verified fix set may be described before any adapter exists but may not be called a
repair, and that terminal button asserts a ship decision the screen has no evidence for. The models
list maps loosely onto adapters under `data/models/`. The loading lab is dead weight and both
loaders must become real stage reporting or go: a fixed five-second bar in front of real task builds
and hour-long API calls is a false statement about the run.

## Vision-specific dead weight

`public/data/` holds 1,051 PNGs — 437 originals at 1.7 MB and 614 edited images at 2.4 MB, 4.3 MB
in all — from the archive's image-editing task, plus the two JSON files the summary screens read.
None of it means anything for software-engineering agents and it should be deleted once nothing
references it. It has not been deleted. The same goes for the assets in `src/assets/`.

## What it would have to read

Artefacts that already exist here, not invented endpoints. Probes are one JSON per file under
`data/probes/`, globbed as `probe_*.json`, and are the only payload directory committed in full.
Episode stores are one directory per run under `data/episodes/` holding `episodes.jsonl`,
`trajectories.jsonl` and `unreached.jsonl` with a tracked `MANIFEST.json`, the three names fixed in
`adversary/execution/store.py:19-21`. Fix sets are `examples.jsonl`, `recipe.yaml` and `fixset.json` under
`data/fixsets/`. Experiments under `experiments/` carry a `preregistration.yaml` and `config.yaml`,
a `registration.json`, an append-only `amendments.jsonl`, a sealed `results/MANIFEST.json` and a
`verdict.json` reading killed, survived or inconclusive; both prototype directories deliberately
lack the first two today. The report is `adversary/report/`, where `Atlas` is a pydantic model and
`render_markdown` its only renderer, docstringed "Python and text only; no dashboard". The honest
way in is to serialise the atlas as data and render that. Because payloads are gitignored and there
are no API routes, something must hand these files over: a read-only reader, or a build step writing
atlas JSON into `public/`. That choice has not been made.

## The claim page constrains the display

`prototype/PLAN-CLAIMS.md` governs, and it is not a footnote requirement. Every figure carries the
descriptive label, per prohibition one, which warns that a complete estimator with a full ledger
behind it reads as a completed measurement — so a bare number in a 40-pixel box is not a legal
rendering of anything. No number appears without its denominator, population, missingness and oracle
assumptions, and no "clean" or "no failures" appears without a valid upper bound. The
unresolved ledger sits beside the result, every attempted item accounted for as build error, oracle
defect, witness not found, unrealised injection, certified pass or certified failure. Coverage
language is not computed in the UI: `Atlas.coverage_language` returns the sentence that may be
printed, and the UI prints that string. The pin renders checkpoint, quantisation and serving kernel
as unpinned and the reasoning setting as declared; because that setting belongs to the target it is
named in the sentence carrying the finding, and two settings are two pins, never pooled.
Contamination renders as open. Withholding a claim never deletes the record beneath it, so
provenance, operational scope and the named reason a stronger statement was unavailable all stay.
The landing page's promise to "measure model degradation, ship evidence-backed improvements, and
build truly robust systems" is the register the claim page exists to prevent.

## Status

Nothing is wired. No `npm install`, no build and no lint run has happened here, and nothing under
`prototype/frontend/` is referenced by any Python in the tree. The dependency set is unaudited: 448
locked packages, four floating `latest` specifiers, and a dev script from unpkg.

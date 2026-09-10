# Astra monitor and results

`/demo` and `/demo/results` use the same recorded dataset from workers 4 and 5. The existing Linear-style activity feed and mirrored results distribution are preserved.

The 2026-09-10 20:47 UTC capture includes **147 eligible clean/attack pairs** across seven tasks: **28 attacked failures and 119 attacked passes**. Counts include repeated executions. Strong variant 1 has 15 failures (A/B/A+B each 5 of 5); strong variant 2 has 13 (A 5/5, B 3/5, A+B 5/5). Each program has five passing clean controls.

The full register retains 384 planned Astra episodes: 174 passes, 54 failures, 64 infrastructure/unknown outcomes, and 92 missing/pending episodes. Of the 54 failures, 26 belong to tasks whose clean run also failed, so they do not appear as induced failures. The newest 50-task batch has 16 terminal episodes across eight tasks in this capture; its seven eligible pairs passed. The earlier standalone passing Astra rehearsal and all raw archives remain in the external evidence collection.

## Data and evidence

- `src/lib/demo/recorded-run.json`: all 147 display records, actual model authorship, conditions, repetitions, patches, tests, and summary counts.
- `src/lib/demo/run-data.ts`: presentation adapter; constructs the same five stages for every recorded run.
- `public/data/astra/cases/`: one complete evidence JSON per displayed run, including its matched clean run, full task messages, actual tool traces and visible outputs, full attack code, patches, original replay logs, exposure checks, and gold-control evidence where applicable.
- `public/data/astra/episode-inventory.json`: every registered episode, outcome, and exclusion reason.
- `data/astra/source-manifest.json`: original artifact locations and SHA-256 hashes, including model request/completion artifacts retained in the external archive.
- External source collection: `/Users/andre/Desktop/astra-adversarial-evidence/2026-09-10`. Raw files are preserved with remote hashes; no experiment jobs were changed or rerun.

Only completed, uncensored, exposed attacks with matching passing clean controls enter the UI. Pair checks match model, source revision, environment pins, prompt, budgets, and observation limit. Failures require a passing reference repair and recorded failed assertions. These are host diagnostic results: no protected, confirmed, trained-model, or population-level claim is implied. Counts in the overview describe the captured examples, not a pooled success rate.

## Presentation

The monitor opens with an explanation and Launch. Cases arrive automatically, beginning with a real failure. Explanations and findings appear immediately; injected guidance and patch excerpts stream character by character. Each recorded finding stays open for 4.5 seconds. Selecting older activity never pauses progression; Follow live restores the current case. Results is available immediately at bottom right.

Results groups every eligible attacked execution by its observed behavior and outcome. The failure categories are Configured locale ignored (24 runs) and Decider defaults lost (4 runs); successful repairs are grouped by task behavior. Controls never count as successful attacks. Expand the category list to reach all nine categories. Each category offers its complete list of executions, next/previous navigation, clean/attacked output tabs, full patch and checks, exact injected guidance, full attack code, and an on-demand command trace. Titles describe the active guidance or observed repair; program labels distinguish repeated executions. Trace counts reflect the selected arm's tool calls. Failed checks are listed before passes. Long code and example lists scroll inside their existing frames. Full evidence and the complete inventory can be downloaded. No API, polling, or new dependency was added.

The Final report button opens `/demo/results/report`: a brief account of where Astra struggled and succeeded, with counts derived from the same dataset and a link back to the evidence.

## Refresh and verify

The importer reads an already verified evidence collection; it never executes the recorded attack code:

```sh
python3 scripts/import-astra-data.py /Users/andre/Desktop/astra-adversarial-evidence/2026-09-10
npm run test:demo
npx eslint src/components/demo/results-explorer.tsx src/components/demo/story-replay.tsx src/lib/demo/run-data.ts src/lib/demo/results.test.mjs src/lib/demo/replay.test.mjs
npm run build
npm start -- --hostname 127.0.0.1 --port 3100
```

The frontend only publishes the needed evidence fields. Full repeated API envelopes, server logs, preparation artifacts, and earlier experiments remain in the external raw archive. Imported JSON is rendered as text; it is never evaluated as code or HTML.

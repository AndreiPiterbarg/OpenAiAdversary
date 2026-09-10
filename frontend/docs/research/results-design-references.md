# Results design references — Sentry selected

Research inspected on 2026-09-10. The user subsequently selected Sentry, requested dark mode, and asked to retain its main parts with less clutter. The implementation follows that selection. The user's results handoff and subsequent selection take precedence over older plans.

## Existing frontend

Repository: `/Users/andre/Desktop/OpenAiAdversary`, branch `codex/demo-experience-plan`. The checkout was clean before research. All research and implementation files are inside `frontend/`.

Read the demo routes and shared layout, story component and CSS, RUN fixtures, playback reducer and tests, dashboard shell, global CSS, and demo README. Inspected the existing preview at port 3100, including Launch, activity, Results, and return to the Launch screen. At 1440 × 1000, the shell is 1200px wide and the content section is exactly 936px wide, beginning at x=340. At the time of research, Results was its heading-and-return-link scaffold.

The fixtures have three cases, three attack channels, and paired outcomes attributed to Devstral-Small-2-24B. Qwen3-8B is the adversary. Astra 6 is the follow-up target; its results are unavailable. Preserve those distinctions.

## 1. Langfuse — Traces Table Peek View

- Original product page: https://langfuse.com/changelog/2025-03-21-table-peek-view
- Public 14-second recording: https://static.langfuse.com/docs-videos/table-peek-view-gif.mp4
- Capture: `results-reference-captures/langfuse-peek.png`
- Borrow: a visible selected row beside a stable detail inspector; the inspector carries identity, evidence navigation, and input/output.
- Observed in the recording: the table initially fills the view; the inspector covers its right-hand columns while leaving the row identity visible. Different rows update the same inspector. Closing it exposes the table again. At approximately 3 seconds and 8 seconds the inspector displays different selected traces. This preserves context while reviewing several items. Precise easing/duration was not measured.
- Fit: use a compact three-finding index and one evidence column in our 936px area. The finding and its conditions should precede raw evidence. The recorded three-column trace tree, dense metrics, and independent scroll areas are not a proposed layout for our page.
- Access: the live shared project redirected to sign-in. The original public recording was viewable without registration; no traces were generated.

## 2. Linear — Peek preview

- Original product page: https://linear.app/docs/peek
- Capture: `results-reference-captures/linear-peek.png`
- Borrow: a concise preview with identifier, title, aligned inline metadata, and description, placed over a still-visible issue list.
- Verification: inspected the original product screenshot. The documentation describes Space to toggle, arrows to inspect adjacent items, and Escape to close. This was a static screenshot, so the actual product's entrance/exit animation was not verified. The documentation image's zoom animation is not evidence of the product interaction.
- Fit: a restrained quick-reading layer for failure summaries, model, and channel; longer code would need a more spacious detail state. Preserve the current dark palette and existing type. Keyboard-only discovery would need a visible pointer control in our adaptation.
- The already accepted story reference, https://linear.app/developers/aig (figure 04), was also inspected. Its narration, small filled symbols, inline metadata, and disclosures remain the visual baseline.

## 3. Sentry — Issue Details

- Original product page: https://docs.sentry.io/product/issues/issue-details/
- Capture: `results-reference-captures/sentry-issue-detail.png`
- Borrow: a concrete failure message at the top, selected-event context, a prominent relevant source frame, collapsed secondary frames, and evidence sections underneath. The public annotated screenshot makes the hierarchy explicit.
- Verification: inspected and enlarged official screenshots of the shipped interface. The sandbox at https://sandbox.sentry.io/ required email registration and acceptance of terms; no form was submitted. Product disclosure animations were not verified and are not being claimed.
- Fit: a finding detail view using the full available width would give code the most room. Use task, attack condition, observed result, and relevant evidence as the hierarchy. The screenshot's aggregate charts, frequency counts, severity, collaboration controls, and purple/light styling are not supported or needed in our three-case view.

## 4. Braintrust — paired trace/output comparison

- Original product screenshot and explanation: https://www.braintrust.dev/docs/evaluate/playgrounds#view-traces
- Public walkthrough: https://www.braintrust.dev/foundations/comparing-experiments
- Video: https://www.youtube.com/watch?v=0kwO5pbLt24 (row inspection around 1:10–1:25)
- Capture: `results-reference-captures/braintrust-comparison.png`
- Borrow: common input/expected context separated from clearly labeled observed outputs; a row position and compact navigation remain associated with the inspected case. Diff is an explicit view control.
- Verification: enlarged the official Trace viewer image. The public video showed selected table rows and then a trace detail view with a narrow row index at the left. Fine transition timing was not established. No private workspace was used and no evaluations were run.
- Fit: two arms named Without attack and With attack, both attributed to the coding model, followed by the actual pass/fail evidence. Use compact paired summaries and sufficiently wide code on demand. The screenshot's many model columns and repeated paragraph cards are not a proposed style.

## 5. The Pierre Computer Company — Diffs

- Exact working example: https://diffs.com/#layout
- Additional evidence annotations: https://diffs.com/#annotations
- Source: https://github.com/pierrecomputer/pierre
- Capture: `results-reference-captures/pierre-stacked.png`; additional split capture alongside it.
- Borrow: file identity, aligned line numbers, restrained added/removed line backgrounds, inline token differences, and a clear Split/Stacked control.
- Observed live: clicked both layout controls. Code changes from aligned side-by-side columns to a full-width unified listing while changed tokens remain highlighted. This appeared as a direct layout update; no elaborate animated morph is claimed. Stable labels and change markings make the comparison easy to follow.
- Fit: especially useful for root versus base_dir and src/loader.py versus src/legacy/loader.py. A comparison of separate observed outputs must be labeled as such, not presented as a literal repository patch. Use this as an evidence treatment; adopting its dependency is not required or decided.

## Research recommendation and subsequent selection

The research recommendation was Langfuse's visible-selection/stable-inspector relationship with Sentry's finding-to-evidence hierarchy and Pierre's stacked code treatment. The user instead selected **Sentry in dark mode, with unnecessary detail removed**.

The selected implementation follows the issue header, compact toolbar, event-detail panel, grouped source frames, and separated context sidebar in the Sentry capture. The user approved this hierarchy and requested removing its enclosing box, so the header, toolbar, and columns flow directly into the page. Dark neutral surfaces, muted purple controls, a code gutter, and highlighted result lines adapt its treatment to the existing shell. Task and attack conditions precede the relevant output; secondary evidence expands below it. A compact selector provides access to the three cases. This is a Sentry-style detail view rather than the previously recommended permanent list/inspector split. Routine implementation and verification are authorized by the selection.

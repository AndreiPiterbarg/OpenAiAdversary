# DEMO replay plan

Planning baseline: `AndreiPiterbarg/OpenAiAdversary`, commit `3616dfd17d7c47af51fe6c2904b9d6962c516da5`, inspected on 2026-09-10. Implementation is confined to `frontend/`. This document plans the replay first; the separate results plan defines its destination. The consolidated [implementation brief](../../prompts/P-DEMO.md) owns the shared routes, schema and handoff contract. No UI has been implemented by this planning task.

## Recommendation

Build `/demo` as a deterministic player over one completed-run-shaped data snapshot. Give the first case a 72-second story: a repository seed becomes a generated perturbation program, checks admit it, and the same task passes in the control condition but fails under the perturbation. The memorable image is the side-by-side comparison. The memorable sentence explains exactly what changed and what failed.

After the first story finishes, reveal **Go to final results** in the bottom right. Keep that action available while replaying the other cases from the same snapshot. It opens `/demo/results?run=<runId>&case=<featuredCaseId>`, always selecting the rehearsed first case. Replays never create new results or suggest a second run is executing.

Use proxy data now, marked **EXAMPLE DATA** on both screens. A proxy recording is an illustration of the proposed presentation, not evidence that a run occurred. When real artifacts arrive, replace the data module and its evidence references; no component or timeline code should change.

## What the current frontend actually provides

| Source | Reuse | Avoid inheriting |
| --- | --- | --- |
| `src/components/dashboard/dashboard-shell.tsx` | Exact header, navigation, page background, content width and spacing | Duplicating the shell in a second design system |
| `src/app/globals.css` | Existing neutral surfaces and motion duration/easing variables | Assuming generic shadcn color tokens equal the literal dashboard colors |
| `src/components/dashboard/dashboard-list.tsx` | Card outlines, tone chips, light page headings | Building a new neon terminal palette |
| `src/components/dashboard/test-suite-page.tsx` | Breadcrumb pattern and white primary action | Introducing a different primary-button treatment |
| `src/components/dashboard/summary-page.tsx` | Existing card rhythm and compact data presentation | Vision-specific scenario imagery or its data contract |
| `src/components/dashboard/processing-loader.tsx` | Only visual context for how restrained the app is | Its fixed-duration progress or its claim-like loading copy |
| `src/components/dashboard/loading-lab-page.tsx` | An existing example of loop controls | Calling every replay a new run; a remount-based loader is insufficient for inspect/pause/resume |

There is no hacker-style terminal in this checkout. The existing loader is a ghost animation with a timer. The proposed terminal character therefore comes from the brief, implemented inside the app's existing visual language.

The shell is `max-w-[1200px]`, with a `156px` sidebar, a `64px` desktop gap and a `max-w-[936px]` content column. It uses `px-4`, `md:px-8` and `pt-12`. Keep those values. Card recipe: `rounded-[8px] border border-[#222222] bg-[#1a1a1a] p-6`; inner source wells use `#171717` or `#222222` and `rounded-[2px]`.

Use `#eeeeee` for important text and `#aaaaaa` for supporting text. Keep the existing semantic tones: green `#2aff7c` on `rgba(52,199,89,0.4)`, amber `#ffd600` on `rgba(255,146,48,0.4)`, cyan `#00ffff` on `rgba(0,136,255,0.4)`. Every verdict also has an explicit word/icon; color carries no unique meaning. An amber rejected candidate means a check worked; an amber perturbed failure means the evaluated behavior failed. Those labels must be different.

The root loads Geist font variables, but neither the body nor Tailwind maps normal sans text to those variables. The parent task verified the actual heading as `ui-sans-serif, system-ui`, `24px`, weight `300`. Preserve that visible font for chrome and prose. Apply the existing Geist Mono variable locally to code, paths and the event lane. Changing the global body to Geist would change the rest of the product and is outside this plan.

## Changes to the older brief

1. **Use the actual 72-second schedule below.** The old table says a 100-second target but reaches 2:00. Shorter beats leave room for the interactive results portion of a presentation.
2. **Lead with the case, not hash strings.** Keep provenance available in the header and an expandable metadata view. Six seconds of hashes does not explain the product.
3. **Keep generation as the distinctive step and comparison as the payoff.** A refusal ledger is useful evidence discipline, but a weak final image for this demo. Put its useful caveats beneath the final case summary and in results.
4. **Animate selected content, not every string.** Stable headings, model roles, labels, verdicts and controls are essential reading anchors. A typing excerpt and a restrained event cascade provide the terminal character.
5. **Keep all initial evidence proxy.** Do not promote old mining totals, pin hashes, model outputs or admission rates to measured because they appear in another repository's brief. New evidence must be explicitly attached to the new snapshot.
6. **Separate four roles from four available measurements.** Show the adversary, scoring target, transfer filter and target as configured seats. If a seat or evaluation is missing, say so. Do not manufacture a fourth model or cross-family result to complete the animation.
7. **Treat timing as replay position.** A progress track can report `Replay 00:34 / 01:12`; it must never imply job completion percentage, token generation speed or computation running now.

## First story: 72 seconds

All times below are presentation time, independent of recorded run duration. A visible replay label remains present for every beat. Default playback is 1×. Existing page-entry motion runs once on route entry; it does not reanimate the shell every stage.

| Time | Beat | Primary visual and copy | Active role | Required reading hold |
| --- | --- | --- | --- | --- |
| 00:00–00:08 | MINE | Case title, one-line task, a short repository-history seed excerpt and the declared channel. The task's expected behavior is visible before anything fails. At most three seed events appear in the lane. | `Repository history · code` — no model highlighted | All primary copy resolved by 00:03; hold at least five seconds |
| 00:08–00:26 | GENERATE | A short program excerpt types into the source well. Three persistent labels establish `Generator`, `Perturbation`, `Verifier`; one visible selected excerpt explains the mechanism. A 2–3-line channel diff lands beside/below it, making the changed input concrete. | Adversary | Excerpt complete by 00:18; final eight seconds show readable code and the changed channel |
| 00:26–00:34 | CHECK | At most four selected check rows settle into explicit outcomes. Show one admitted candidate and representative rejected candidates only if supplied by the snapshot. Each rejection has a plain technical reason. | `Checks · code` — no model highlighted | Rows resolved by 00:29; hold five seconds |
| 00:34–00:52 | COMPARE | Same task and model shown once above two balanced panels. Left: **CONTROL · PASS**, expected behavior and decisive evidence. Right: **PERTURBED · FAIL**, observed behavior and corresponding evidence. A small annotation identifies the changed channel. For 00:34–00:44 the scoring target is active; for 00:44–00:52 the filter row either shows its actual paired evidence or `Not measured`. | Scoring target, then configured filter if present | Both decisive results readable by 00:39; retain the pair for the entire beat |
| 00:52–01:04 | CONFIRM | Keep the original comparison visible in compact form. Show a small evidence table for held-out cases and the configured target. Every row identifies the task/source and its recorded status. Missing confirmation becomes `Target confirmation not measured`; it never turns into success after a delay. | Target only when its evidence is shown | Table or missing-evidence state resolved by 00:56; hold eight seconds |
| 01:04–01:12 | TAKEAWAY | A one-sentence mechanism statement above the same control/perturbed pair. Beneath: the strongest supported evidence status and one short limitation. Label counts as snapshot totals and keep them constant. | No model highlighted | Main conclusion visible by 01:05; hold seven seconds |

At **01:12**, latch the results action as available, announce availability once to assistive technology, and advance into the next stored case. The button reveals over the existing `220ms`/standard easing; its label is immediately readable. Never steal focus or redirect automatically.

The proxy story should illustrate one modest, understandable failure. The consolidated brief proposes stale task guidance leading to a deprecated API choice. An **alternate** editorial fixture is a config-loading task: expected behavior reads from the workspace root; a generated repository-note perturbation induces a package-relative lookup; the corresponding assertion fails. Use one coherent fixture throughout the first story, not a mixture of the two. Both are proposed synthetic examples, not observed failures of any named model. Label source, program, response and assertion excerpts as illustrative. Keep the changed channel outside the declared oracle/test read set. The fixture's exact task, code and evidence must remain coherent with one another.

Suggested proxy presenter sentence for the alternate fixture: **“The task stayed the same; a generated change to the repository notes changed the behavior and exposed the failing case.”** Real-data copy should name the actual changed channel and actual failure, and use `confirmed` only when confirmation evidence exists.

### How the later replays work

- Continue through the ordered `RUN.story.replayCaseIds` from the same immutable snapshot; after the last, return to the first. If only one case exists, replay it with a clear `Replaying case` label.
- Preserve the same six-stage structure. Do not invent missing stages, outputs or counts for variety. An absent section renders its explicit unavailable state for that beat.
- Label the header `Case 2 of 3 · Run replay`, not `Run 2`, `Searching again` or `New failure found`. A replayed discovery event is past-tense: `Candidate admitted` rather than `Admitting candidate now`.
- The first 72-second story is the presentation contract. Other cases may use the same duration initially; shorter later passes are an optional refinement after the first story is approved.
- Keep **Go to final results** visible for all subsequent cases, even while the source excerpt is typing. Its URL stays pinned to the first `featuredCaseId` so a presenter always reaches the prepared evidence.

## Screen composition

The shell stays intact. Put the terminal character inside one restrained work area, with at most one visually active text region at a time. Do not combine a scrolling code panel, scrambling summary and streaming log simultaneously.

```text
EXISTING PRODUCT HEADER
EXISTING NAV       Projects > Run replay           EXAMPLE DATA
                  Synthetic run · Case 1 of 3      [Pause] [Controls]

                  ADVERSARY   SCORING TARGET   FILTER       TARGET
                  <model>    <model>          Not supplied <model>
                  writes     compares         transfers    confirms

                  MINE — GENERATE — CHECK — COMPARE — CONFIRM — TAKEAWAY

                  ┌─────────────────────────────────────────────────┐
                  │ Load config from the workspace root             │
                  │ Declared channel: repository notes              │
                  │                                                 │
                  │  CONTROL · PASS        PERTURBED · FAIL          │
                  │  Expected behavior     Observed behavior        │
                  │  Decisive excerpt      Corresponding excerpt    │
                  │                                                 │
                  │  Changed: one repository-note instruction       │
                  ├─────────────────────────────────────────────────┤
                  │ 00:26 checks  admitted · declared channel only  │
                  │ 00:34 score   control comparison available      │
                  │ 00:38 score   perturbed assertion failed        │
                  └─────────────────────────────────────────────────┘
                  Replay 00:42 / 01:12   ━━━━━━━━──────

                                  [Go to final results →] ← after 01:12
```

The wireframe uses the alternate config-loading fixture to illustrate hierarchy. The work area's interior switches between source/diff, checks, and comparison; its outer dimensions stay stable. Desktop should fit the primary story and controls at 1440×900 and 1920×1080; also verify the 1280×720 laptop view required by the consolidated brief. Use a bounded code excerpt of 8–12 readable lines, not a full-file feed. Store both an excerpt and full source in the shared artifact; arbitrary full source lengths must not change the story timing. Essential text is at least 14px. The case heading uses the existing 24px light type; avoid oversized marketing type.

On narrower screens, the role rail wraps into two columns, stage labels wrap rather than forcing horizontal page scroll, and the two comparison panels stack control first. Preserve panel order and headings. Source text gets its own horizontal scroll region; the page does not. Content may scroll vertically on small screens. Do not shrink essential text to fit a projector-style canvas into a phone.

Use a footer action area aligned to the content column's right edge and the viewport bottom, with enough page-bottom padding that it covers no evidence or keyboard target. On mobile use a compact bottom action strip with a 44px touch target and safe-area padding. Reserve the action area before unlock so revealing the button does not shift the source or comparison panels. After unlock, its accessible name is exactly `Go to final results`.

## Text reveal and motion

| Element | Behavior |
| --- | --- |
| Shell, title, role rail, stage names, controls, status labels | Render as stable readable text. Stage/model highlights use existing color transitions. |
| Short event rows | Use existing entry easing with 80–140ms between rows. Reveal whole clauses or words over no more than 500ms. Show at most 3–4 rows at once. |
| Generation excerpt | Type or reveal line fragments during the first ten seconds of GENERATE. The excerpt is bounded and authored for the beat; the full program is available on inspection. Reserve the final text's height first. |
| Source identifiers | Optional single short resolve effect, 220–340ms, monospace only. Use deterministic placeholder glyphs so replay is identical. Never scramble essential assertions, verdicts or the final conclusion. |
| Comparison verdicts and conclusion | Existing `220ms` opacity/position transition followed by a long readable hold. No random glyphs. |
| Cursor | A restrained cursor only while source is being revealed; stop it with Pause and remove it once the excerpt resolves. |
| Results action | Reveal once after the first completion; never pulse, retype or disappear on each loop. |

Derive all reveal progress from the same playhead. Use a single `requestAnimationFrame` clock, using elapsed timestamps instead of counting frames so high-refresh displays do not accelerate the story. Update React only when a meaningful displayed value changes, rather than rerendering the entire tree for every clock tick. Browsers commonly pause animation frames in hidden tabs, so the playback model must account for visibility explicitly. [MDN: requestAnimationFrame](https://developer.mozilla.org/en-US/docs/Web/API/Window/requestAnimationFrame)

Keep full meaningful text available to assistive technology and hide decorative partial/typed copies from it. Do not put token updates in a live region. A small `aria-live="polite"` status can announce stage changes, pause/resume and the one-time availability of results. The stable comparison panels remain ordinary selectable text.

Under `prefers-reduced-motion`, render text fully resolved, disable scrambling/cursor motion and replace moving stage transitions with static state changes. Start paused with visible **Play replay** and **Next stage** controls for this preference; allow playback when requested. This deliberately improves on the old brief's proposal to keep an unavoidable timed presentation. Controls must remain visible for everyone: an automatically changing presentation of this duration needs a pause mechanism. [W3C: Pause, Stop, Hide](https://www.w3.org/WAI/WCAG22/Understanding/pause-stop-hide.html)

## Player and action behavior

Use a lightweight playback provider in `src/app/demo/layout.tsx`, wrapping `/demo` and `/demo/results` with `DashboardShell activeSection="projects"`. The provider stores navigation-safe playback state; only the replay page owns the animation loop. It must not animate in the background while results are open.

Minimum state: `runId`, `dataRevision`, `caseId`, `beatId`, `elapsedInCaseMs`, `playing`, `resultsReady`, `featuredCaseId`, `loopEnabled`. Here `runId` and `dataRevision` refer to `RUN.identity.id` and `RUN.identity.revision`; the featured ID comes from `RUN.story.featuredCaseId`. Keep recorded run duration in `RUN.identity.recordedDurationMs`, not in this presentation state. Use a reducer/pure transition function for control semantics.

| Event | Required behavior |
| --- | --- |
| Fresh normal-motion entry | Validate the snapshot, select the featured case and autoplay from 00:00. Stable chrome is available immediately. |
| Pause | Freeze playhead, source reveal, cursor, event arrivals and stage transitions together. All links and controls still work. |
| Resume | Continue from the same elapsed point, without replaying completed arrivals. |
| Tab becomes hidden | Freeze active elapsed time. Track whether the user had already paused. |
| Tab becomes visible | Resume only if it was playing before the visibility pause; otherwise remain paused. Never jump forward by time spent hidden. |
| Next/previous stage | Jump to the selected stage, fully resolve that **target stage's** frame and remain paused. Store its resolved reveal offset so Resume continues the readable hold without retyping or leaving a blank paused frame. Do not reset the results latch. |
| Next at the end of TAKEAWAY | Complete the first story if needed and expose the action. Explicit user skipping is presentation navigation, not new evidence. |
| Restart | Return to the featured case at 00:00 and play it identically. Preserve an already-unlocked results action. |
| Stop looping | Finish the current case, then hold TAKEAWAY; the action stays available. `Pause` remains the way to stop immediately. |
| First story completes | Set `resultsReady=true` once, then continue the replay sequence if enabled. This is a playhead event, not a report-fetch event. |
| Click results | Snapshot the playhead, stop the replay loop and navigate to the pinned `run`/`case` URL. The next page handles report availability separately. |
| Browser back or Return to replay | Restore the saved case and position, initially paused with a visible Resume action. Preserve the unlocked results link. |
| Data revision changes | Reset saved playback for the new revision. An unlock from one run must not accidentally unlock a different run. |

The Page Visibility API provides the visibility-change signal; background timers are throttled, so interval ticks cannot stand in for elapsed active viewing time. [MDN: Page Visibility API](https://developer.mozilla.org/en-US/docs/Web/API/Page_Visibility_API)

An in-memory provider is sufficient for route round trips. If refresh persistence is implemented, use session storage keyed by `runId` and `dataRevision`, guard parsing and unavailable storage, and restore only valid positions. Do not add persistence complexity before the first replay works.

The action latch is an editorial cue, not an authorization or data-access gate. `/demo/results` must support direct links without forcing a replay. If the results data cannot be rendered, that route must show a useful missing/unavailable state and a return link. A replay finishing does not prove results loaded, and a results fetch finishing does not trigger a misleading run-completed animation.

Visible controls: **Pause / Play**, **Previous stage**, **Next stage**, **Restart**, and a compact **Controls** disclosure for shortcuts/loop behavior. Fullscreen is optional and must be user initiated. Shortcuts can include Space, arrows, R and F, but must ignore text inputs/contenteditable elements and avoid overriding the native activation of a focused button or link. No essential control is keyboard-only. Preserve focus on stable buttons through stage changes; the CTA's appearance never moves it.

## Data contract and truthful substitution

One authoritative module supplies both routes, for example `src/lib/demo/run-data.ts`. The initial export is a proxy fixture; the renderer does not infer evidence status from elapsed time or a stage name.

The [consolidated implementation brief](../../prompts/P-DEMO.md#7-one-artifact-two-presentations) is the schema authority. Do not implement a second replay-specific run shape. The replay consumes these canonical records:

| Shared record | Replay responsibility |
| --- | --- |
| `RUN.identity` | Read `id`, `schemaVersion`, `revision`, `source: 'proxy' \| 'recorded' \| 'mixed'`, `recordedAt` and `recordedDurationMs`; keep recording metadata separate from the playhead. |
| `RUN.models` and `RUN.roles` | Resolve configured models and their seats; absent model identity is not an invitation to invent one. |
| `RUN.cases` | Select the task, expected behavior, applied change and paired evidence by stable case ID. |
| `RUN.modes` | Read imported mechanism/group identity and evidence level; a replay does not promote an observation to a confirmed mode. |
| `RUN.proposals` | Present supplied generator, perturbation, verifier and admission evidence independently from evaluated-case outcomes. |
| `RUN.claims` | Use only supplied supportable conclusions and limitations. |
| `RUN.story` | Read `featuredCaseId`, `replayCaseIds` and `beats`, including curated excerpts and evidence references. |

Keep source provenance separate from observed outcome (`passed`, `failed`, `unresolved`), execution health (`completed`, `truncated`, `error`, `unreached`, `unknown`), and imported evidence level/attribution. These axes answer different questions. `error` is execution health, not an adversarial outcome; `Not measured` is a missing-evidence display, not a fourth verdict. Neither passing animation checkpoints nor a control/perturbed pair can raise the imported evidence level. The shared validation boundary owns those distinctions and receipt consistency.

- IDs are stable strings shared by replay and results. Never deep-link by list index or current filtered position.
- Keep role names independent from model names; names can change without changing stage layout. Missing filter model is displayed as `Not supplied`. A configured filter with no measurement is `Not measured`.
- Each evidence block includes source provenance, a short source label and artifact references when recorded, independently from its outcome and execution health. Mixed runs expose section-level provenance and a mixed-data header. A global switch cannot promote synthetic blocks to recorded evidence. Initial proxy records display `EXAMPLE DATA` on both routes.
- A proxy model response is labeled `Illustrative response`; do not present invented quotations as outputs from a configured model. A synthetic source excerpt is similarly labeled.
- Display recorded durations only where data supplies them and label them `Recorded duration`; they may be minutes or hours even though the replay lasts 72 seconds.
- Store selected replay excerpts explicitly alongside full evidence. Do not silently truncate the decisive failing assertion or speed up typing to squeeze an arbitrary program into the storyboard.
- Render counts from the same snapshot as results. A counter may reveal the recorded count at its stage, but may not accumulate again on the second replay.
- Check pair comparability, including task/base identity, model configuration and evaluation conditions. If the control is absent, has execution health other than `completed`, or has outcome `failed`/`unresolved`, replace the contrast claim with `Comparison incomplete` or its actual recorded state. A failing control cannot substantiate a perturbation-induced failure. Keep infrastructure health and attribution visible without counting either as a verified target failure. Show per-arm configurations when they differ instead of silently collapsing them into one model label.
- No confidence interval, percentage, rate or aggregate badge without its supplied denominator/method and supporting records. Omit unsupported aggregate decoration from the first demo.
- The fixture needs one coherent featured case, two further cases for loop testing, a missing filter example and a missing confirmation example. All remain visibly proxy until actual evidence arrives.

## Implementation seams and order

Proposed new files, all under `frontend/`:

```text
src/app/demo/layout.tsx                 shared shell and playback provider
src/app/demo/page.tsx                   replay route
src/app/demo/results/page.tsx           results route, phase two
src/components/demo/demo-replay.tsx     composition and visible controls
src/components/demo/replay-provider.tsx navigation-safe state
src/components/demo/replay-stage.tsx    source/check/compare renderers
src/components/demo/replay-reveal.tsx   scoped reveal behavior
src/components/demo/replay.module.css   demo-only styles and reduced motion
src/lib/demo/types.ts                   one shared snapshot contract
src/lib/demo/run-data.ts                proxy snapshot, later replaced
src/lib/demo/replay-timeline.ts         schedule and pure state transitions
```

Keep the root globals, old dashboard pages and old loader unchanged. Use the existing shared shell directly. The source brief's obsolete prototype paths, standalone fallback, branding rewrite and backend assumptions do not expand the user's frontend scope. Production route content should use local bundled data/assets; verify it with the production build because the existing development-only react-grab script is a separate network behavior.

Build in this order:

1. Agree the shared case/evidence IDs and data contract with the results plan. Create the small coherent proxy snapshot.
2. Render all six stage states statically inside the actual shell. Review GENERATE and COMPARE first; these determine the visual quality. Confirm typography and dimensions against existing pages before adding motion.
3. Add the 72-second deterministic player and visible pause/step/restart controls. Verify first-completion latch and later replay behavior.
4. Add scoped source/event reveals, visibility handling and reduced-motion behavior. Keep all evidence selectable/readable at the end of a reveal.
5. Review the entire first story in the browser and repeat it. Only after that review, implement the full results destination defined by the second plan.

The first-demo milestone includes the complete replay, the latched action and a stable route/ID handoff contract. End-to-end demo completion is not claimed until the real results destination exists. If work is deliberately stopped after phase one, name that boundary explicitly.

## Failure states

| Input or condition | Demo behavior |
| --- | --- |
| No snapshot / invalid schema | Static `Replay unavailable` card with the validation issue in development and a useful return action; no fake replay or crash |
| Featured case missing | Explicit `Featured case unavailable` data error for the broken `RUN.story.featuredCaseId` reference; no automatic fallback or unrelated case selection |
| Empty case list | `No replay cases available`; results remain independently addressable |
| Generator or seed missing | Named stage with `Source excerpt unavailable`; no fabricated code typing |
| Filter not configured | Keep the filter role visible as `Not supplied`; skip active highlight and show the missing-evidence state |
| Target/confirmation unavailable | `Target confirmation not measured`; conclusion uses the strongest evidence actually present |
| Comparison inconclusive/error | Show observed outcome and execution health separately; never restyle an infrastructure error or unresolved result as a verified adversarial failure |
| Very long source or evidence | Bounded authored replay excerpt, full text on inspection, local overflow only |
| Font or image unavailable | Preserve readable system fallback text; no required remote imagery |
| Clock/remount/Strict Mode | No duplicate completion callbacks, duplicate CTA announcement, or double-speed reveal; clean up animation/listeners |
| Return from results | Saved evidence frame, paused, with Resume and results action usable |

## Acceptance, in priority order

**P0 — meaning and integrity**

- A viewer can explain the task, changed channel and failure after one pass without reading the event lane.
- GENERATE visibly communicates that the adversary writes a program; it cannot be mistaken for a menu of hand-authored attacks.
- COMPARE keeps a readable, comparable control/perturbed pair on screen long enough to inspect. Missing evidence never acquires a success verdict through animation.
- Every synthetic section says proxy/illustrative. No old measurement, count, hash, model output or confirmation is silently promoted.
- The same snapshot and case IDs drive the replay and its results URL. The fixed URL selects the featured first case even during a later case's replay.

**P0 — behavior**

- At 1×, first story completes at 72 seconds of active playback; first-completion event fires once.
- CTA is absent from keyboard navigation before unlock, appears after completion, and remains usable during every subsequent reveal, pause, restart and loop transition.
- Pause freezes all decorative and narrative motion; visibility changes do not skip the story.
- Next/previous/restart and results round trips obey the table above. Step navigation shows the fully resolved target frame while paused, and Resume does not retype it. There is no background replay while results are shown.
- Two full loops produce identical recorded evidence and totals, with no cumulative fake discovery counter.

**P0 — fit and access**

- Visual review at 1440×900 and 1920×1080 confirms the existing shell, font hierarchy, 8px/2px radii, surfaces and button treatment; the 1280×720 laptop view remains usable.
- At 390px width and at 200% zoom, no page-wide horizontal overflow, obscured evidence or unreachable control appears.
- Keyboard users can operate every essential action; focus survives stage updates. Screen-reader output does not announce every typed character.
- Reduced motion provides fully readable frames and explicit playback control.

**P1 — substitution and engineering**

- Replace the fixture with different model names, long code, a single case, additional cases, missing filter, and no confirmation using the data file alone. Layout and timeline code remain untouched.
- Run the production build and a production browser smoke test with local data. Test invalid/missing run and case IDs at the destination when phase two lands.
- Add meaningful state-transition tests for latch monotonicity, pause/resume, skipped stages, hidden time and deterministic looping. Avoid tests that merely snapshot class strings.
- The parent baseline reports `npm ci` and `npm run build` passing. It also reports pre-existing failures in `npm run lint` (`next lint` removed) and direct ESLint (`FlatCompat` circular reference). Record those accurately; do not call the unchanged lint baseline clean.

**P2 — polish after the story works**

- Optional fullscreen, shortcut help and per-case inspect actions.
- Optional session refresh persistence and shorter subsequent replay passes.
- Projector review before any route-local border adjustment. A decorative glow, scanline filter, sound effect or random glyph wall is not part of the plan.

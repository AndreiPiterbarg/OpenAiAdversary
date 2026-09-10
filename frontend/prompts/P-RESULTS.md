# Results presentation — agent handoff

Build the results experience that follows our adversarial evaluation demo. The central output is a useful failure description for a particular model: what goes wrong, the conditions that trigger it, and the evidence behind the finding. Make the page compelling in a fullscreen demonstration and useful for inspecting individual failures.

**Your first deliverable is research and real design references, not implementation.** Inspect the current frontend, then go online and show me actual pages made by professional frontend/product designers that we could adapt. Let me look through them and choose a direction before you build the results UI. Do not generate five speculative concepts or choose the design for me.

## Repository and scope

- Correct repository: `/Users/andre/Desktop/OpenAiAdversary`.
- GitHub: https://github.com/AndreiPiterbarg/OpenAiAdversary
- Current working branch at handoff: `codex/demo-experience-plan`. Inspect the branch and worktree before editing; preserve existing work.
- **Work and commit only inside `frontend/`.** Stage explicit paths. Do not commit other folders or push unless I ask.
- `/Users/andre/Desktop/vision_adversary` is a different checkout. Some old prompts refer to it. Do not implement or commit there.
- This is a desktop, fullscreen website demo. Use roughly **1440 × 1000** for visual review. Do not spend time on a mobile redesign or overengineer the architecture.
- The real completed-run data is not available yet. Use the existing proxy fixtures and keep replacement straightforward. Do not start training, call models, add backend services, or build a live transport layer.

## Start by showing me real examples online

First read the files below and inspect `/demo` in the browser so you understand the approved layout. Then research **five strong, directly applicable references** from real shipped interfaces or working interaction demos. Prefer the original product/designer pages to image galleries. If you use a component example, include its working demonstration and source when available.

The reference that I liked for the story is **Linear's agent activity**, particularly figure 04 here:
https://linear.app/developers/aig

I liked its actual symbols, spacing, narration, compact action rows, and disclosures. A generic accordion with a Linear label was not enough. Use that level of specificity when researching results views.

For each reference, show me:

1. A direct link to the exact page or demonstration, the product/designer, and a screenshot or accessible motion example where possible.
2. The precise interaction or information layout we could borrow: for example, an issue list opening an evidence detail view, a code comparison, a compact model overview, or smooth transitions between findings.
3. What moves when I interact, and why that animation helps me follow the information. Do not describe an animation you have not actually seen.
4. How it would fit our current dark dashboard and textual/code evidence. Keep this explanation short and concrete.

The set should help me choose between a few credible ways of inspecting model failures. Avoid five unrelated aesthetic themes. If a reference requires sign-in, explain what you could verify and provide a publicly viewable alternative where possible.

End your first deliverable with a concise recommendation and a request for my selection. **Wait for that choice before implementing the explorer.** No elaborate mockups, new design lab, or new dependencies during this research step. After I choose, proceed with the selected design without repeatedly asking permission for routine implementation choices.

## What exists now

The frontend uses Next.js App Router, React, TypeScript, Tailwind CSS, and CSS modules. The current build uses Next.js 16.1.6. Lucide icons and `motion` are already installed. The accepted monitor uses simple CSS transitions and a small React playback reducer; it does not need an animation framework.

Read these files relative to the repository root:

| File | Purpose |
| --- | --- |
| `frontend/src/app/demo/page.tsx` | Renders the live monitor. |
| `frontend/src/app/demo/layout.tsx` | Shared layout for `/demo` and `/demo/results`; already wraps children in `DashboardShell`. Do not nest a second shell. |
| `frontend/src/components/demo/story-replay.tsx` | Approved introduction, Launch control, expandable agent activity, thinking square, and persistent Results link. |
| `frontend/src/components/demo/story-replay.module.css` | Best reference for the accepted visual language, sizes, spacing, and motion. |
| `frontend/src/lib/demo/run-data.ts` | Shared fixture data, model roles, three attack cases, code, paired outcomes, and findings. |
| `frontend/src/lib/demo/replay.ts` | Playback state, navigation behavior, character typing, and timing. |
| `frontend/src/lib/demo/replay.test.mjs` | Existing behavior and timing tests. |
| `frontend/src/app/demo/results/page.tsx` | The results route scaffold you will replace after design selection. Currently a Results heading and a Live monitor return link. |
| `frontend/src/components/dashboard/dashboard-shell.tsx` | Existing header, sidebar, content width, and AP profile initials. |
| `frontend/src/app/globals.css` | Shared colors, motion utilities, easing, and reduced-motion handling. |
| `frontend/src/app/demo/README.md` | Current demo behavior and local verification notes. |

There are historical planning documents in `frontend/prompts/P-DEMO.md` and `frontend/docs/research/results-presentation-plan.md`. They contain useful evidence-design ideas but also superseded requirements. **This handoff, my subsequent instructions, and the actual accepted frontend take precedence.** Do not restore delayed results access, visible replay badges, timers, a mobile project, elaborate URL/persistence machinery, or an assumed final layout because an older plan mentions them.

The old image-oriented dashboard summary is not the results implementation to copy. Its thumbnail gallery and truncated scenario arrays do not fit software-agent evidence.

## Current behavior to preserve

- `/demo` starts with a plain explanation of adversary training, the goal of describing a model's failures, and paired testing. Nothing runs until **Launch** is pressed.
- A fixed **Results** link appears immediately at bottom right, even before Launch. It opens **`/demo/results`** whenever pressed, including during an active case. Results must never require completion of the story.
- After Launch, separate cases arrive chronologically as expandable agent sessions. The counter is small. There are no previous/next case buttons.
- Each session has five actions: repository search, attack code, coding-agent test, follow-up results, and finding. Use the actual action labels in the component as reference.
- The current action expands as the prior one closes. Clicking earlier activity holds the reader's selection while the run keeps progressing; **Follow live** returns to the current activity.
- Explanations, source context, and findings appear as complete text. Generated code types by character. Typing is 10% slower than the original pace, and thinking pauses are 25% longer. The recorded finding remains open for **4.5 seconds**.
- The small animated 6×6 thinking square is explicitly liked. Keep it in the story. Results are available evidence, so they do not need fake typing or artificial loading.
- The shell profile is **AP**.
- Playback state is currently local to the monitor. Returning from results opens the Launch screen; persistence across routes has not been implemented. Do not add it as an unrelated prerequisite.

## The visual direction I want

I want the results to feel like a carefully designed extension of the current product. Clean, understated, and precise, with polished real interface animations. “Interesting” should come from how information is revealed and compared, not decoration.

The approved style has:

- A near-black `#111` background, restrained gray surfaces and fine separators, off-white text, and muted secondary copy.
- Existing system sans-serif body typography. Geist Mono is used deliberately for code and small identifiers. Do not change global fonts.
- Light 24px page headings; compact 12–15px labels and copy. Small counters and useful metadata, without oversized statistics.
- Small intuitive symbols, inline metadata, disclosure triangles, and clear alignment. The monitor's action icons are custom SVGs; existing Lucide icons are also available.
- An outer shell max width of 1200px, a 156px sidebar, a 64px desktop gap, and a main area capped at 936px. Inspect the actual usable width before choosing a split view or paired code layout.
- Short opacity, height, and small-position transitions. Current disclosures take about 320ms, new activity about 260ms, and hover feedback about 160ms. Match their character rather than copying durations mechanically.
- Reduced-motion support, visible keyboard focus, readable contrast, and controls whose purpose is clear without animation.

I rejected earlier “creative” concepts as childish and obviously AI-made. Those experiments remain under `/demo-lab` and `frontend/src/components/demo/concepts/`; **they are rejected references**. Do not revive them or expose their navigation.

Avoid neon hacker dashboards, orbital graphics, sci-fi diagrams, glowing panels, decorative grids, huge metric tiles, gradients everywhere, bouncy springs, and repeated rounded boxes around every paragraph. Do not replace information design with a wall of cards. Keep text efficient. Use a chart only if the available data supports a useful comparison.

## What the results must communicate

The adversary learns from attacks that succeed and fail. The results should make its findings about a **specific target model** understandable. A viewer should quickly see:

1. Which model was tested and what failure was found.
2. What the coding agent was supposed to accomplish.
3. What the adversary changed and under which conditions the failure occurred.
4. How the agent behaved without the attack and with it.
5. The relevant code, file, tool response, or test output supporting that finding.
6. What is known about repetition or transfer, where such evidence exists.

Let me reach every failure, select one, and inspect useful detail. A compact index with an evidence detail view is one possible direction, but research and my selection should determine the final layout. The concrete failure description should be understandable before I read a raw trace. Make code and evidence available on demand, with full text immediately visible when opened.

Keep interactions purposeful: selection, expand/collapse, comparison, and search or filters where they help with the actual data. Preserve reading position when opening details. Avoid nested scroll areas and cramped side-by-side code. Do not add pagination, virtualization, dashboards of metrics, or a complicated state framework for three cases.

## Data available for the first implementation

Use `RUN` from `frontend/src/lib/demo/run-data.ts` as the source of truth instead of duplicating a different story in the results. It contains:

- `identity`, including internal `source: "proxy"`.
- `models` and `roles`, separating the adversary from the coding model and follow-up target.
- `cases` with stable IDs, titles, repository, channel, context, source evidence, attack hypothesis/code, change boundary, both test arms, finding, mechanism, and five presentation steps.

There are three cases in the fictional `waypoint/config` repository: outdated documentation leads to a removed API argument; a changed search result redirects an edit to the wrong file; an added task constraint preserves incorrect configuration behavior. This is **not a documentation-only system**. Each case owns its attack channel and evidence.

The current fixtures associate Qwen3-8B with the adversary, Devstral-Small-2-24B with paired coding-agent tests, and Astra 6 with follow-up confirmation. Resolve these labels from the data. Do not attribute Devstral's outcomes to Astra or to the adversary model.

The current paired examples all have a passing “Without attack” arm and a failing “With attack” arm. Follow-up checks are unavailable and read “No result yet.” Do not convert those into passed or confirmed results. Three selected examples do not establish a model-wide failure rate or broad coverage. Do not invent benchmark denominators, confidence intervals, severity rankings, run timestamps, or extra completed evaluations.

Preserve internal proxy provenance so recorded data can replace it later. The presenter explains the demo setup separately; the current product deliberately has no replay/simulation badges. Keep displayed claims grounded in the supplied fields. If a future artifact lacks an output, show that it is unavailable rather than copying expected behavior into the observed result.

Results should load all supplied cases immediately, independently of the playback clock. Code and logs are display text, not programs to execute in the page. Keep any extra view data small and typed; do not invent an elaborate backend schema before the real export exists.

## Implementation and verification after I choose a reference

Build inside the existing `/demo/results` route and shared shell. Prefer route-specific components and a CSS module, reusing established styles and dependencies. Keep the demo's content, pacing, Launch flow, and Results navigation intact.

From `frontend/`, the available commands are:

```sh
npm run dev -- --hostname 127.0.0.1 --port 3100
npm run test:demo
npm run build
```

At handoff, port 3100 uses the production preview (`npm start -- --hostname 127.0.0.1 --port 3100`), so it needs a rebuild and restart to reflect edits. Check what is already running before launching a conflicting server. The route to inspect is `http://127.0.0.1:3100/demo/results`.

Use the browser skill for actual fullscreen visual and interaction checks. Verify immediate navigation from the pre-Launch screen and during activity, direct results loading, access to every case, readable evidence, functioning selection/filter controls, keyboard disclosures, and no horizontal page overflow. Run focused lint and relevant tests plus the production build. Full-repository lint has previously had unrelated legacy dashboard failures; do not expand this task to fix them.

Finish with a working preview, a brief description of what changed and how it was verified, and a frontend-only commit. Do not publish or push without my instruction.

**Begin now with the real online references and your recommendation. Wait for my choice before building the results presentation.**

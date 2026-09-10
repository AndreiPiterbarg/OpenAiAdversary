# P-DEMO — the two-minute demo

You build the thing that gets shown on stage. Two minutes maximum, shorter is better, running in the
existing frontend's exact visual language. It must convey **what the system does** — the steps, and
the fact that four different models play four different roles — not just a list of errors being
spotted.

**Files you own:** `prototype/frontend/src/app/demo/` and `prototype/demo/` (the standalone
fallback). Do not modify `globals.css`, `tailwind.config.ts` or anything under
`src/components/dashboard/` — you consume that design system, you do not change it.

**The audience is hackathon judges, at distance, in a dark room, for 120 seconds.** They will not
read body copy. They will remember one image and one sentence. Design for that.

### Three requirements that are not negotiable

**1. It matches the existing frontend exactly.** This is not "inspired by" or "in the spirit of". The
same greys, the same two fonts, the same 8px/2px radius split, the same card recipe, the same motion
easings and durations — all of them already exist in `prototype/frontend/src/app/globals.css` and
`tailwind.config.ts`, and §2 below lists the literal values. Someone who clicks from
`/dashboard/projects` to the demo must not be able to tell they changed design systems. If you find
yourself picking a colour, you have gone wrong: the palette is fixed at five greys and three tones.

**2. Every piece of text arrives by revealing, not by appearing.** Nothing cuts in. Text loads in
word by word, terminal-style, as described in §5. This is the entire visual character of the piece —
without it you have a static dashboard, and with it you have something that looks alive.

**3. The example data is a placeholder and will be replaced.** Real numbers are coming from the runs
in `PLAN-RUN.md` and `PLAN-CODE.md`. Build so that swapping them in is **editing one constant and
nothing else** — no layout assumptions baked around the example values, no hard-coded counts in
markup, no magic numbers in the timeline that only work for these figures. See §6, and treat it as a
load-bearing requirement rather than a nicety, because it is the step that happens last, in a hurry,
possibly by someone else.

## 1. Standing context

*This block is byte-identical across every prompt in `prototype/prompts/`. Everything in it was
verified against the working tree or the cluster.*

**The project.** An adversary that discovers realistic failure modes of software-engineering agents
and proves them well enough that a lab would act on them. The perturbation is a **program written
against a declared channel**, seeded from artefacts mined out of the target's own repository history
— not a selection from a menu. The adversary is **trained**, not prompted, with the diversity
requirement baked into the selection rule that builds its training set. The deliverable is the
**generator**, not a dataset: programs that emit fresh instances of a named failure mode on demand.

**The four seats.** Astra 6 at low reasoning effort is the target, the reject-only LLM critic and the
R2 reference witness — never the proposer, mutator or recovery model, and this is enforced in code,
not by taste (`ModelInfo.shippable` is true only for `PERMISSIVE`; `frontier.py` forces `RESTRICTED`
at construction). **Qwen3-8B** is the trained adversary, mutator and fixset recovery model.
**Devstral-Small-2-24B** is the cheap local scoring target and the model a repair adapter is trained
on — it is Mistral-family because `A5:440` rule 1 forbids pairing a Qwen proposer with a Qwen target.
A third open family is the transfer filter.

**Repository.** `/Users/andre/Desktop/vision_adversary`, branch `remove-declared-space`. Python
3.13.15, pydantic v2 (`FrozenModel`/`StrictModel`), `StrEnum` for closed vocabularies, ruff at line
length 100 with `E,F,I,UP,B,ANN`. **No new dependencies.** Use the root `.venv`
(`.venv/bin/python`), never the system interpreter. Baseline verified this session: **211 passed, 5
skipped in 1.93 s, ruff clean**; `adversary/` 8,312 lines, `domains/` 1,187, `tests/` 2,251.

**Layering, enforced by `tests/test_boundaries.py`.** Import graph `core ← domain, stats, protocol ←
execution ← probe ← search, confirm ← repair ← report`, acyclic. Nothing under `adversary/` may
contain the words repository, docker, container, hazard, github, pytest, swe or pull request — the
test parametrises over **every** `.py` under `adversary/`, 76 files, not just `core/`. Domain-specific
terms live in `domains/`.

**The cluster.** Host `nebius` = login-0 (<login-node-ip>); dev nodes `worker-4`, `worker-5` by
ProxyJump; work on dev nodes, **never `sbatch`**. enroot 3.5.0 — the Docker daemon is not reachable
and user namespaces are blocked on the login node. QOS `guest-dev` sets `MaxTRESPerUser = node=2`, so
**16 H100s, not 32**. Everything lives in shared home `/home/guests/andrei/va/`, visible to Slurm;
`/mnt/memory` is a 1.5 TB RAM tmpfs for scratch only. Shared-home write is 125 MB/s. Two venvs:
`~/va/.venv-vllm` (vLLM 0.29.0) and `~/va/.venv-train` (peft 0.20.0, transformers 5.17.0). Every
training entry point needs `torch.backends.cuda.enable_cudnn_sdp(False)` or the first forward pass
dies on this driver.

**What is on disk.** Four repo-disjoint corpora, 321 instances over 321 repos: `discovery_149` (149),
`confirm_A` (60, SWE-rebench-V2), `confirm_B` (60, SWE-rebench **v1** — a different collection window
and pipeline, *not* a different organisation, which is weaker than the design intends),
`recall_uncond` (52, drawn with **no** condition filter — the only instrument that can measure
coverage). 321 enroot images (758 GB), 150 full-history clones (9.7 GB), Qwen3-8B (16 GB), and
**46,811 mined seeds** — `ci_drift` 20,819, `dep_churn` 20,203, `fix_on_fix` 5,210, `revert` 579 —
all bounded to ancestors of each instance's `base_commit`. **Inside an image the repo is at
`/<repo-name>` (e.g. `/rez`), NOT `/testbed`.**

**The two measurements that exist.** E0: 200 proposals, **0 admitted**, 95% CP [0.000, 0.018]. After
six repairs to the contract between the prompt and the runtime, under `prototype/proposer_pin.json`:
**195/200 parsed (.975), 152/200 admitted (.760, [.695, .817])**, zero unexplained exceptions.
`prototype/acceptance.py` aborts unless the live `DRAFT_SCHEMA` and the three gate modules hash to
what the pin records; **the working tree currently matches both digests exactly** (gate `46b69bf6…`,
schema `a5221aa1…`). Nothing else in the loop has ever run.

**What.760 is not.** Stage A of the admission ladder is five gates and **two are built**. The DA2
read-set check, the build check and the gold-patch re-check do not exist, and they are exactly the
three that would reject what is being admitted today: an admitted draft at seed 1 is a constant
function returning a toy grid-navigation dict — no repository, no commit, no tests. The cause is one
line: `render_context` renders no mined seed, so 46,811 records reach nothing. Treat.760 as a
contract check that passed, never as a capability or budget figure, and never as a result.

**Precedence.** `prototype/STATE.md` beats every plan document on any number. A `PLAN-*.md` beats an
older prototype document. `docs/DESIGN.md` (D1–D18, A13) and `docs/DISCOVERY-ARCHITECTURE.md`
(DA1–DA13) are the design authority. Anything in `superseded/` is quarantined: read it for reasoning,
never for current fact.

**Verification tags — required on every external or numerical claim you make.** `[REPO]` resolved
against the working tree this session; `[CLUSTER]` verified on the cluster this session;
`[COMPUTED]` re-derived here with formula and inputs shown; `[V]` primary source fetched and read;
`[CARRIED]` from the project's own documents, not re-verified; `[UNVERIFIED]` named from general
knowledge. **An untagged claim is not admissible.** This is not ceremony: S3 fetched the fourteen
citations behind the architecture and five of the seven results in its own justification table
failed; S5 re-checked eleven more and six load-bearing ones failed. `prototype/PLAN-CLAIMS.md`
carries the do-not-cite list and it binds you.

**Do not touch.** `docs/research/expressive-adversary/` and `docs/RESEARCH-PROBLEM.md` are written by
other agents. `superseded/` and `archive/` are quarantined; do not resurrect anything from them. Do
not commit. Never run `git add -A` — if you stage anything, use explicit paths. Other Claude sessions
are live in this checkout; if you are making code changes, work in your own git worktree.

**Three standing rules about the shape of your answer.** The adversary — the layer that writes
generator programs — cannot be cut, only renamed. **Push back**: if a plan's recommendation is wrong,
say so and give the counter-argument rather than summarising it approvingly; overturning a decision
in this folder counts as success, not failure. And every gap between what our prompt promises and
what our runtime provides gets charged to the model as incompetence — E0 went from 0% to 76% without
a single change that made the model better at writing probes, so before concluding a model cannot do
something, prove the contract let it try.

---

## 2. The exact design system — extracted from the tree, use these literal values

The frontend is a Next.js App Router project with Tailwind 3 and one vendored shadcn component. Its
system is a **neutral greyscale with exactly three semantic tones**. Match it precisely; do not
introduce a palette.

**Ground and surfaces.** Page `#111111` — set on both `html` and `body` in `globals.css`, so a
transparent body is a bug. Card/panel `#1a1a1a`. Secondary surface `#171717`. Inset chip fill and
icon wells `#222222`.

**Lines.** Border `#222222`. Hover border `#333333`. Wizard-button hover border `#2a2a2a`.

**Text.** Primary `#eeeeee`. Muted `#aaaaaa`. Dimmer `#8f8f8f` and `#777777`. Hover `#d0d0d0`.

**The only three colours in the entire system**, from `dashboard-list.tsx:34-36`:

| Tone | Fill | Text |
|---|---|---|
| green | `rgba(52,199,89,0.4)` | `#2aff7c` |
| yellow | `rgba(255,146,48,0.4)` | `#ffd600` |
| cyan | `rgba(0,136,255,0.4)` | `#00ffff` |

**Use green for admitted/pass and yellow for rejected.** There is deliberately **no red hex anywhere
in the components** — `--destructive` exists as a token but no component spends it. Rejection in this
system is *amber*, not alarm, and that is the right register: a rejected draft is the gate working,
not a failure. Reserve `hsl(var(--destructive))` for a genuine crash only. Cyan is for the third
category — use it for the pin and provenance chips.

**Radius.** Cards `rounded-[8px]`. Small insets, thumbnails and wells `rounded-[2px]`. That 8/2 split
is the system's signature; `--radius: 0.75rem` exists but the components override it literally.

**Type.** `Geist` and `Geist Mono` via `next/font/google`, exposed as `--font-geist-sans` and
`--font-geist-mono` on `<body>`. Page titles `text-2xl font-light`. Section headers
`text-sm font-semibold leading-5`. Body `text-sm`. Labels `text-xs`. **The frontend never uses bold
display type** — its hierarchy comes from weight *contrast* (light 2xl against semibold sm), not from
size alone. Keep that.

**Layout.** `max-w-[1200px] mx-auto`, `flex flex-col gap-16`, page padding
`px-4 pb-6 pt-12 md:px-8 md:pb-12`. The canonical card is:

```
rounded-[8px] border border-[#222222] bg-[#1a1a1a] p-6
```

**Motion — use the existing utilities, do not write new easings.**

- `--motion-ease-standard: cubic-bezier(0.22, 1, 0.36, 1)`
- `--motion-ease-emphasized: cubic-bezier(0.16, 1, 0.3, 1)`
- durations: fast `160ms`, base `220ms`, slow `280ms`
- `@keyframes ui-enter`: `opacity 0→1`, `translateY(10px)→none`, `blur(4px)→0`
- `.motion-page-enter` plus `.motion-delay-1/2/3` at 60/120/180ms — **this is your row-entry
  animation**, already written, already reduced-motion guarded
- `.motion-interactive` (hover `translateY(-2px)`, active `scale(0.97)`), `.motion-segment` (hover
  `scale(1.02)`)

The `prefers-reduced-motion` block at the end of `globals.css` already disables these. Anything you
add must be disabled there too.

**One thing in the existing frontend you must not copy.** `ProcessingLoader` counts to a fixed
5,200 ms and 5,600 ms regardless of what is happening underneath. A fake progress bar in front of a
real system is a false statement about the run, and a judge who spots it discards everything else.
Every progress indicator you draw reports a real position in the timeline.

## 3. The brief — what actually wins

The failure mode of every other demo in the room is a wall of scrolling green text that means
nothing. **Yours has to read as a machine with parts.** Three things must be legible from ten feet:

1. **It is a pipeline with named stages**, and the stage advances visibly.
2. **Four different models do four different jobs**, and you can see which one is acting.
3. **Most candidates are rejected**, and the rejections have specific technical reasons.

The single most differentiating beat is the last one: the refusal ledger. Every other team claims
their numbers. Closing on *what we refuse to claim, and why* is memorable, it is thirty seconds, and
it is true.

## 4. The two-minute script, beat by beat

Target **100 seconds**, hard ceiling 120. Autoplay from load. Times are cumulative.

| Beat | Ends | Stage | What is on screen | Role lit | Reveal (§5) |
|---|---|---|---|---|---|
| **0** | 0:06 | `PIN` | The binding pin: `Qwen/Qwen3-8B @ b968826d`, `vLLM 0.29.0`, `schema a5221aa1…`, `gate 46b69bf6…`. Three digests settling into place. Six seconds of pure credibility | — | **scramble** on the three digests |
| **1** | 0:22 | `MINE` | Repo names streaming (`rez`, `WALinuxAgent`, `PyDESeq2`, `cfn-lint`, `moto`, `evalml`), a counter climbing to **46,811**, the four miners breaking out: `ci_drift 20,819 · dep_churn 20,203 · fix_on_fix 5,210 · revert 579`. One line beneath: *bounded to ancestors of `base_commit`* | — *(git only, no model)* | word; **scramble** on the counter |
| **2** | 0:48 | `PROPOSE` | One seed is selected and **the adversary writes a program**. Code types out: the hypothesis, the declared `channel`, and three program sources — generator, **perturbation** with its named `clauses`, verifier. This is the beat that proves it is not a menu | **ADVERSARY** — Qwen3-8B | **char type**, the only beat that uses it |
| **3** | 1:10 | `GATE` | Drafts arrive and are gated. Rejections carry real reasons; the checks fire as a visible row of seven. Counter climbs with a live Clopper–Pearson interval | **GATE** — *no model; code only* | word, staggered 40 ms per row |
| **4** | 1:32 | `CONTRAST` | Two columns: control passes, treatment fails, on the scoring target. Then the second family runs the same pair — a mode only survives if it breaks **both** | **SCORING TARGET** then **FILTER** | word; **scramble** on the two verdicts |
| **5** | 1:48 | `CONFIRM` | Fresh held-out instances from two sources against the real target. The confirmed-mode card assembles | **TARGET** — Astra 6, low reasoning | word |
| **6** | 2:00 | `VERDICT` | The mode, one sentence. Beside it the **refusal ledger**: coverage — refused; audit bound — refused; transfer matrix — refused, mechanism built; every figure descriptive | — | **scramble** on the mode sentence, then word for the ledger |

**Beat 2 is the demo.** Give it the most time and the best typography. Judges have seen dashboards;
they have not seen a model write an executable perturbation program against a channel it is provably
allowed to touch. Type the code at §5's 26 ms/char with a block cursor, and let the `clauses` line land last.

## 5. The text reveal — the visual character of the whole piece

**Nothing on this screen cuts in.** Every string arrives by loading in, terminal-style. This is the
single decision that separates it from a dashboard, and it has to be graded rather than applied
uniformly — the same effect on every element at the same speed is nauseating at 1920×1080 and reads
as a filter rather than a design.

### Four reveal modes, one per role of text

| Mode | Applies to | Timing | Character |
|---|---|---|---|
| **Word reveal** | labels, captions, hypotheses, row text, everything prose | **22 ms per word**, ease `--motion-ease-standard` | Words appear left to right. No scramble. This is the default and it carries ~80% of the screen |
| **Char type** | the probe source in beat 2, and only there | **26 ms per char**, block cursor `▊` blinking at 530 ms | The typewriter. Reserved for the one moment where a model is authoring something |
| **Scramble resolve** | digests, counters, verdicts, the final mode sentence | **340 ms**, ~6 frames per glyph | Random glyphs settling into the real characters. The "hacker" beat |
| **Instant** | the role rail, stage spine, chrome | — | Structure does not perform. It is already there when the beat starts |

**Scramble is a spice, not a base.** It should fire perhaps eight times in the whole run — the three
pin digests in beat 0, the 46,811 counter in beat 1, the admitted count in beat 3, the two contrast
verdicts in beat 4, the mode sentence in beat 6. If it fires on every row it stops meaning anything
and starts costing legibility.

### How to implement it without the three bugs it invites

**Reserve the box first.** Render the full final string into the DOM at `opacity: 0`, measure, then
reveal spans in place. Do not append words as you go — appending reflows the line, the card grows,
and the whole column jitters for two minutes. Same for the code block: reserve its height from the
full source before typing a character.

**Scramble in a monospace-safe glyph set.** Draw substitute glyphs from a fixed pool
(`ABCDEF0123456789#%&$@/\<>*+=-`) and only inside `--font-geist-mono`. Scrambling proportional text
changes the measured width every frame and the line dances. Preserve spaces and punctuation — scramble
only the alphanumerics — so word shape holds while the characters resolve.

**One `requestAnimationFrame` loop for the entire page.** Not a timer per element. At beat 3 you may
have forty rows revealing at once, and forty independent `setInterval`s will drop frames on a
projector's integrated GPU. One loop, a queue of active reveals, each with a start time and a
duration; step them all per frame.

### Timing discipline, so the effect never costs comprehension

**Every beat's text must be fully resolved by 60% of that beat's duration.** The reveal is the arrival
of the information, not a delay in front of it — a judge who is still watching characters settle when
the stage changes has read nothing. If a string cannot resolve in that window, the string is too long:
cut it, do not speed the reveal past ~14 ms/word, where it stops reading as loading and starts reading
as a flicker.

Rows in a stream **stagger**, they do not fire together: 40 ms between successive rows, so the eye
gets a cascade down the column rather than a block flash. Cap the visible stream at what fits without
scrolling and let older rows fall off the top at `opacity: 0.35`.

### Reduced motion

`globals.css` already ends with a `prefers-reduced-motion: reduce` block. Extend it: under reduced
motion **all four modes become instant**, the stagger drops to zero, and the beat timings are
unchanged so the run still lasts 100 seconds. The demo must be watchable, just not animated.

## 6. The four roles, and how to show them

The right rail is a fixed column of four role cards. Each is the canonical card, dimmed to `#8f8f8f`
text at rest, lifting to `#eeeeee` with a green tone chip when that role is acting. **Only one is lit
at a time**, except beat 4 where the handoff from scoring target to filter is the point.

| Role | Model | Card sub-label |
|---|---|---|
| **TARGET** | Astra 6, low reasoning | *evaluation and published claims only* |
| **ADVERSARY** | Qwen3-8B | *writes the programs — permissive, so they ship* |
| **SCORING TARGET** | Devstral-Small-2-24B | *cheap contrast, Mistral family* |
| **FILTER** | third open family | *a mode must break two families* |

Carry one line of the reason, because it is the sharpest thing in the architecture and it takes six
words: **the licence decides the seat.** Astra can never write a program we ship, and that is enforced
in code — `ModelInfo.shippable` is true only for `PERMISSIVE`. Put it as a single dim caption under
the rail. Do not explain it further on screen; let the presenter say it.

## 7. The data contract — the example data WILL be replaced with real data

**Say it once more because it changes how you build:** every number you ship in this demo is a
placeholder. The real ones are being produced right now by the runs in `PLAN-CODE.md` (a re-measured
admission rate under pin v2) and `PLAN-RUN.md` (verified pins, clean base rates, one pass through the
loop with a real contrast, confirmation on held-out repos). **They will land late, in a hurry, and
possibly be pasted in by someone who did not build this.** Your job is to make that a five-minute
edit to one file.

Build the whole thing as a player over one exported constant:

```ts
// prototype/frontend/src/app/demo/run-data.ts   (or demo-data.js in the fallback)
export const RUN = {
  source: "example",          // "example" | "measured"  ← the only field that changes behaviour
  measured_at: null,          // ISO date when source === "measured"

  pin:      { model, revision, engine, schema_sha256, gate_sha256 },
  mine:     { total, by_miner: { ci_drift, dep_churn, fix_on_fix, revert }, repos: [...] },
  probe:    { hypothesis, channel, clauses: [...], generator, perturbation, verifier },
  gate:     { checks: [...], draws: [{ id, verdict, reason }], parsed, admitted, ci: [lo, hi] },
  contrast: { control: [...], treatment: [...], second_family: [...] },
  confirm:  { sources: [...], items, gap_points },
  refusals: [{ claim, status, reason }],
}
```

### The rules that make the swap survivable

**Nothing outside this file may know a value.** No `46,811` typed into JSX, no `152/200` in a
template, no beat duration tuned to the length of the current probe source, no CSS height that only
works because today's code block is nineteen lines. If a number appears on screen, it was read from
`RUN`.

**Every list renders whatever length it is given.** The gate stream must handle 12 draws or 400.
The miner breakdown must handle four miners or six. The refusal ledger must handle three rows or
eight. Where a beat's duration depends on item count, derive it — `min(beatMax, n * perItem)` — and
cap it so a long list cannot blow the 100-second budget.

**Missing sections degrade, they do not crash.** When the loop has produced a contrast but not yet a
confirmation, `confirm: null` must render that beat as a card reading *not yet measured* and move on.
This is the likely state on the day: `PLAN-RUN.md` §9 has an explicit go/no-go where the Astra leg is
blocked for want of an API key, and the demo still has to run.

**Write the swap instructions in the README**, naming the file, the field, and which key maps to
which beat. Ten lines. That README is the deliverable that gets used under time pressure.

### The honesty chip, which costs you nothing and buys you the room

While `source === "example"`, render a small **cyan** chip in the header reading `EXAMPLE DATA`. When
it flips to `"measured"`, it turns green and reads `MEASURED · <date>`. One field, one visible
consequence.

**Do not present example numbers as measured.** It is a 90×20px chip and it is the difference between
a demo and a fabrication — and a judge who asks "is this real?" gets an answer that makes you look
better rather than worse. Two figures you can already show as genuinely measured today, from
`prototype/STATE.md`: the **mining totals** (46,811 seeds across 150 of 150 repos, bounded to
ancestors of `base_commit`) and the **pin digests** (gate `46b69bf6…`, schema `a5221aa1…`, verified
against the working tree). Mark those two green from the start even while the rest is example data —
per-section provenance beats one global flag, and it means the first and strongest beats are real on
day one.

## 8. Build target, and a go/no-go you must run first

**Primary: a new route in the existing app**, `prototype/frontend/src/app/demo/page.tsx`, so it
inherits `globals.css`, the motion utilities and the fonts by construction rather than by imitation.

**Run this before anything else**, because that tree has never been built here: `npm ci` then
`npm run build`. Its `package.json` pins `next`, `react`, `react-dom` and `eslint-config-next` to
`latest`, and `package-lock.json` resolves next 16.1.6 and react 19.2.4 across 448 unreviewed
packages. Also delete the `react-grab` script from `src/app/layout.tsx` — it loads from unpkg at
runtime in development and you must not depend on the network on stage.

**If the build does not come up clean inside thirty minutes, stop and switch to the fallback:** a
single self-contained `prototype/demo/index.html` that reimplements the tokens above verbatim — no
build step, no `node_modules`, opens from `file://`, works offline. The fallback is not a lesser
deliverable for a two-minute stage demo; it is arguably the safer one. Decide early, do not discover
this at midnight.

**Either way the demo runs offline.** No network calls at runtime. Fonts must be self-hosted or
already cached by the build.

## 9. Presenter controls, and the failure modes to design out

- **Autoplay on load**, so nothing has to be clicked while talking.
- `Space` pause/resume · `→` skip to next beat · `←` previous beat · `R` restart · `F` fullscreen.
  Bind them and show them nowhere.
- **A restart must be instant and identical.** You will run this more than once.
- **No horizontal scroll at any width**; code blocks get their own `overflow-x: auto`.
- Assume a **1920×1080 projector with crushed blacks**. `#1a1a1a` on `#111111` may vanish. Test the
  card edges; if they disappear, lift the border to `#333333` for the demo route only and say so.
- Assume the room is dark and the audience is ten feet back: your smallest type on screen is
  **14px**, not 12.

## 10. What must not appear

No fabricated Astra output. No fake progress bar. No claim the loop has run end to end — **it has
not**; four breaks still block the first episode and every episode figure in your `RUN` is
illustrative until it isn't. No coverage or completeness language of any kind. No citation of the
external literature — `PLAN-CLAIMS.md` §7 lists what failed verification and none of it goes on a
screen. No Mistral branding, no vision or driving copy, and none of the 1,051 PNGs still sitting in
`public/data/` from the archived project.

## 11. What you deliver

A route or a file that runs start to finish in under 120 seconds, unattended, offline, twice in a
row, on a projector — in the existing frontend's exact visual language, with every string arriving by
reveal rather than by cutting in.

A `RUN` constant holding all example data, with per-section provenance so the mining totals and pin
digests read as measured from day one, and a one-field switch for the rest. **Prove the swap works
before you call it done**: change two values in `RUN`, reload, and confirm nothing in the layout
needed touching. That test is the deliverable, not the example numbers.

A README of at most ten lines: how to start it, which keys do what, which `RUN` key feeds which beat,
and the one line to change when the real numbers land.

And one sentence, written down, that the presenter says over beat 6 — because the demo's job is to
make that sentence land, not to replace it.

# P-CODE — repair the loop until it can run one episode

You own **`prototype/PLAN-CODE.md`**: everything between "the contract works" and "the loop produces
a number nobody can dispute". This is the largest surface in the project and it gates every other
prompt. You write code.

**Files you may edit:** anything under `adversary/`, `domains/`, `tests/`. You may append dated
`> **Correction:**` blocks to `prototype/PLAN-CODE.md` and `prototype/STATE.md` when you
find one of their claims is wrong. You may not edit the other `PLAN-*.md`.

**Work in your own git worktree.** Other sessions are live in this checkout.

## 1. Standing context

*This block is byte-identical across every prompt in `prompts/`. Everything in it was
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

**Repository.** [OpenAiAdversary](https://github.com/AndreiPiterbarg/OpenAiAdversary).
Work from the checkout root. Python 3.13.15, pydantic v2 (`FrozenModel`/`StrictModel`), `StrEnum` for closed vocabularies, ruff at line
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

## 2. What is already done, so you do not redo it

**Tier 0 closed.** Six defects between the prompt and the runtime, repaired in this order:
thinking left on at the vLLM server (a *serving* defect, the single largest cause of parse failure,
and 7.5x the tokens); `parse_draft`'s greedy `re.search(r"\{.*\}", DOTALL)`, replaced by
`extract_object`, which decodes every balanced object and prefers what follows `</think>`;
`ProgramSource.load()` execing in a bare module so `class G(Generator)` raised `NameError`, fixed by
**binding the eight construction symbols** rather than telling the model to import them (a shipped
probe that reads `from adversary ...import Generator` is coupled to this package's layout forever, and
the programs are the deliverable); `StaticCritic` catching `ProgramError` only; the schema never
showing the interface it demanded (97 of 182 rejections became "Can't instantiate abstract class …
without `__next__`"); the schema never describing the runtime (`NameError: random`, and `self.rng`
written as a numpy generator). A seventh surfaced at the pin: a non-serialisable oracle payload
escaping `StaticCritic` through `canonical_json`. [REPO, verified this session]

**Do not undo any of that**, and in particular do not "simplify" the namespace binding back into an
import instruction.

## 3. What you own, in strict order

### 3.1 The two items tier 0 opened and did not close

- **`LLMProposer.temperature` defaults to `0.0`** (`adversary/search/proposer.py:166`) [REPO]. The pin
  says 1.0. Rejection sampling needs distinct completions per prompt; at 0.0 you draw one repeatedly,
  and it fails silently as a low distinct-sample count rather than as an error.
- ~~**`ServedModel.complete` cannot call Astra.**~~ **DONE.** `ServedConfig` gained `completion_tokens_param`, `send_temperature`, `reasoning_effort` and `extra_body`, and `OpenAIModel` takes `reasoning=`/`reasoning_effort=`. Verified live against `gpt-6-astra`. The measured contract is in `STATE.md` §9: `max_tokens` → 400, `temperature: 0.0` → 400,
  `reasoning_effort` validated server-side rather than silently ignored. **Do not re-do this**, and do not restore `max_tokens` for the frontier path.

### 3.2 Ground the prompt — the highest-value change in the project

`render_context` (`adversary/search/proposer.py`) renders the factor space, hot cells, elites and
transcripts, and **no mined seed** [REPO]. `~/va/seeds/seeds.jsonl` holds 46,811 records carrying
`instance_id`, `repo`, `base_commit`, `miner`, `sha`, `ts`, `subject` — exactly the fields the
training prompt specification asks for — and none of them reaches the model [CLUSTER].

Given a list of factor names and nothing real, Qwen3-8B invents grid navigation. It is behaving
reasonably. Wiring the seed converts the proposer's job from *"invent a task"* into *"write a
perturbation against this repository at this commit"*, which is the job DA1 exists to make possible.
Do this **before** the schema rewrite, because the schema has to describe the seed field.

### 3.3 Schema v2, the perturbation program, the channel

`ProgramKind` has `GENERATOR` and `VERIFIER` only; `DRAFT_SCHEMA` is the pre-DA13 shape with
`"cell": {factor: level}`, two programs and no channel; `StaticCritic.critique` iterates
`(draft.generator, draft.verifier)` [REPO]. DA2 and DA3 specify:

- `ProgramKind.PERTURBATION` and a `Perturbation` ABC with `channel`, `clauses`,
  `prepare(session, spec)` and `observe(step, tool, args, result)`.
- `adversary/domain/channel.py` — the `Channel` type and DA2's V1 check.
- `domains/swe_agents/environment/readset.py` — the oracle's transitive read set:
  `fail_to_pass`/`pass_to_pass` test files, their transitive imports, the conftest chain, the package
  manifest and lockfile. An intervention declares its channel; the check is that its diff touches
  nothing in that set. **One sentence of specification buys unbounded freedom above it**, it is free,
  and it is the load-bearing gate.
- `DRAFT_SCHEMA` v2: drop the cell, add the channel, the seed and the third program with its declared
  clauses — **keeping** the abstract signatures, object shapes and `random. Random` note that tier 0
  paid for.
- Delete `HazardType`, `NATURAL_TOOLS`, `HazardPosition`, the `_apply` dispatch and the `_due` forcing
  rule; drop `Provenance.factor_space`.

**The channel check is what makes an intervention nobody anticipated safe.** Build `channel.py` and
`readset.py` first: they cost no target calls and nothing above them is sound without them.

### 3.4 Mint pin v2 and re-measure

Tier 3.3 edits `DRAFT_SCHEMA` and all three gate modules, so `acceptance.py` will abort. **That is
the pin working.** Mint pin v2 — new digests, the channel declaration and the seed field in place of
the ten-factor block, which is a v1 artefact — **before** its run, not after; a pin proper precedes
its evidence. Then re-measure admission. Expect it to fall well below.760.

`proposer_pin.json` is also the working template for the `TargetPin` that D1 specifies and nobody
wrote. Copy its shape: checkpoint at an **immutable revision** (not a branch), serving kernel,
decoding policy with every field explicit, scaffold with binding digests. For Astra, three of the six
fields are unpinnable and must render as **unpinned**, never omitted.

### 3.5 The four breaks that block the first episode

1. `NullRuntime.start` raises on every call (`domains/swe_agents/environment/runtime.py:35`).
   **Container via enroot** — this was reversed from a local runtime on measurement: four pool repos
   were attempted with `venv` + `pip install -e.` and **zero succeeded, all four failing in under a
   second**, because the host had Python 3.9.6 against repos declaring `>=3.10`. `Session` and
   `ContainerRuntime` are already protocols, so this is one construction site.
2. `builder.py:17` points `ENVELOPES` at a deleted directory and `:33` calls `FactorSpace.from_yaml`
   on it, so construction fails before anything runs. D15 as amended by A13 takes explicit runtime,
   pinned `TaskPool`, registry **and mined-seed-store** inputs.
3. `TaskPool.pins` defaults to `()` (`generator.py:28`), so every match returns nothing. Under DA1
   this is the same job as standing up the miners — build pool and seed store in one pass.
4. `SweRealCorpus.sample` raises `CorpusNotBuilt` twice (`corpus/real.py:47,:50`). Until it returns
   items, confirmation cannot run, and confirmation is what separates a hypothesis from a mode.

### 3.6 The gates on printing a number

Each of these is a licence to print a figure. If one is unfixed, the corresponding number is
**refused** and the refusal is printed with its reason — that is a legitimate outcome, not a failure.

- **The clause-gaming hole.** A two-phase perturbation — one clause stages a payload, another arms it,
  each inert alone — drove `mobius_synergy` to **0.600, one hundred per cent of the total effect**,
  while the identical intervention declared as one clause returned **0.000**. Measured by execution
  against the shipped estimator [CARRIED: S3, firsthand]. A clause-declaration guard is required
  before any excess figure is printed.
- **`excess.py` degrades silently**: under per-probe clause names the leave-cell-out fit has all-zero
  columns, `predicted` collapses to 0.000, and **excess becomes the raw failure rate** — the objective
  this project exists not to use. A13's "needs no change at all" was wrong.
- `hot_cells(min_n=10)` against n=5 per cell returns empty, always — the screening layer never
  screens.
- `witness_failed` does not exist, and D10 depends on it to keep "unwitnessed" distinct from
  "impossible".
- `Provenance` has no source-licence field, so the permissive-only rule in `corpus/sources.yaml` is
  unenforceable in code. MIT and Apache-2.0 obligations travel with derivatives.
- **A licence hole:** `openai_compatible.py:40` and `transformers_local.py:42` both default to
  `PERMISSIVE`, so a Qwen-Community or Llama-Community model served locally registers as shippable —
  and both licences bar using outputs to improve another model, the same ground the frontier APIs are
  barred on.
- `LLMCritic` returns `accepted=True` for anything it does not recognise as an objection
  (`critic.py:168`). Reject-only is a property of `CriticChain`, so an LLM critic goes **inside a
  chain with a `StaticCritic`** and is never passed to the loop directly.
- `ProofResult.ships` uses `all(...)`, **true on an empty suite list** (`proof.py:39`), and the run
  silently takes the shared before/after instance intersection (`proof.py:75`).

### 3.7 The thirteen missing modules

`docs/DESIGN.md` names eight files that do not exist and A13 adds five. The rule is **shrink N, never
shrink structure**: small N is a reason to run a module on less data, never to leave it unwritten.
`PLAN-CODE.md` §Tier 4 splits them into on-the-path, built-but-claim-withheld, and deferred-with-a-
reason. The three that carry mode identity — `confirm/ledger.py`, `confirm/footprint.py`,
`stats/footprint.py` — are not optional: without them the prototype can find a failure but cannot say
it found a **mode**, tell two discoveries apart, or recognise a repeat.

## 4. What you must not build

Removed by argument, not by price, so more compute does not bring them back: snapshot-and-branch
(D13 runs every confirmatory episode fresh); the `MAX_*` caps on excess and decomposition order (D3
found no theorem behind them); the kind quotient as a pruning rule (D4: two kinds equal alone can
differ in company); the declared perturbation vocabulary; vocabulary self-extension beyond DA6's
admission queue; and the MAP-Elites archive and its frozen panel (three independent reasons in
`PLAN-RUN.md` §6, the decisive one being that it is unaffordable by 16x with the shortfall invariant
to how the budget is split).

Do not design a factor scheme. Do not add a dependency. Do not weaken a refusal to make a number
printable.

## 5. What you deliver

Working code with tests, `ruff` clean and the suite green — the baseline to beat is 211 passed, 5
skipped. Pin v2 and a re-measured admission rate with a Clopper–Pearson interval. A short note at the
top of `prototype/PLAN-CODE.md` recording what landed, what did not, and any claim in it you found to
be wrong. If you cannot finish a tier, say which items are outstanding and what they block — a
partial tier with an honest boundary is worth more than a full one with a silent gap.

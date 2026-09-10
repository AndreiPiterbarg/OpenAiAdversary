# P-RUN — turn 321 candidates into a confirmed mode

You own **`prototype/PLAN-RUN.md`**: the cluster work that turns candidates into verified pins,
measures the base rate, runs the loop once end to end, and confirms a mode on real held-out tasks.

**Files you may edit:** `prototype/PLAN-RUN.md`, `prototype/STATE.md` (numbers you measure), and
scripts under `~/va/` on the cluster. You may append dated `> **Correction:**` blocks to
other plan documents when you find a claim wrong, but not rewrite them. Code changes to
`adversary/` belong to P-CODE — file the defect, do not fix it in passing.

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

## 2. Gold-patch verification — the first job, and it needs nothing else

**321 instances are candidates. None is a verified pin.** [CLUSTER] Gold-patch verification is what
turns candidates into pins and replaces three budgeted rates with measurements. It needs **no API
key, no adversary code, no schema and no GPU**, so it blocks on nothing — **launch it before you read
the rest of this prompt** and let it run while P-CODE works.

Verify **all four corpora**, not just `discovery_149`: `confirm_A` (60), `confirm_B` (60) and
`recall_uncond` (52) supply the held-out and coverage draws, and an unverified instance there
poisons a confirmation rather than a search. 149 + 60 + 60 + 52 = **321** (`dhi__mikeio-690` was
dropped for a 401 manifest and is recorded in `data/DROPPED.txt`).

**The check.** Run the gold patch inside each instance's own enroot image and require `fail_to_pass`
to flip and `pass_to_pass` to hold. Two things that will otherwise waste a run: the repo is at
`/<repo-name>`, not `/testbed`, so a harness assuming SWE-bench's convention fails on every instance;
and `confirm_B` is SWE-rebench **v1**, whose schema differs throughout — free-text licences,
`install_config.python` instead of `base_image_name`, `install` as a string not a list, images under
`swerebench/sweb.eval.x86_64.*`. Write the harness for both schemas or it silently skips 60 instances.

**Parallelism, because serial is a day and parallel is an hour.** A dev node has **128 cores and
1,574 GB RAM** [CLUSTER]. At a plausible 3–5 minutes per instance, 321 serial is ~21 hours; at 12–24
concurrent it is **1–2 hours**. Use `/mnt/memory` as `ENROOT_TEMP_PATH` — extraction is dominated by
writing many small files and the shared filesystem is the bottleneck at 125 MB/s. Do not `sbatch`;
dev nodes only.

**Measure while you are here — this is the cheapest de-risking action in the project.** Nothing has
ever measured how long a container-backed run actually takes here. Every episode figure in every plan
document rests on a **2-minute-per-episode assumption stated as an assumption** at `P4-budget.md`
§4(d) and carried ever since. Gold-patch runs are the first real container workload, so instrument
them: record per-instance build time, test time and total, and report the distribution. If the true
figure is 5 minutes rather than 2, the confirmation budget in §7 multiplies by 2.5 and the run plan
changes today rather than at hour eleven.

**Expect a poor yield and measure it** rather than assuming: SWE-bench Verified's human screen
discarded 68.3% of 1,699 samples, and SWE-Bench++ ran 137,048 candidates to 8.1% end to end
[CARRIED]. A yield well under 50% is normal and is not a reason to widen the pool.

**What this step outputs**, and all four are inputs to something downstream:

1. **The pin set** — verified instances per corpus, written under `data/tasks/` on the existing
   `MANIFEST.json` convention, which is also `PLAN-CODE.md` tier 2.3's empty `TaskPool`.
2. **The yield rate** with a Clopper–Pearson interval, per corpus.
3. **Per-instance wall-time distribution**, which re-bases every episode projection in the plan set.
4. **A failure ledger** — every instance that did not verify, with its reason (build error, image
   missing, `pass_to_pass` already failing, timeout). Do not discard these: an instance that fails
   here is a fact about the corpus, and §7's denominators need it.

**It also produces the free anti-degeneracy gate the whole design leans on**: apply a perturbation,
then apply the gold patch, and if the tests stop passing the perturbation broke the **task**, not the
agent. No model call. It bites only on the `worktree_unread` and `task_text` channels, because an
`observation`-channel perturbation never touches the repository — which is why the model-witness floor
in §5 still has to exist for the other two.

## 3. Base rate, and the band that decides the scale

Run the unperturbed instances against each target and record the clean solve rate. This doubles as
the **DA1 point manifest** — the clean trajectory is where `derive_points` gets its eligible call
addresses — so there is no separate job for it.

**The band is.5–.85.** The headroom bound is `e ≤ s − 2m`: at a clean solve rate of.10 the
25-point confirmatory threshold in `adversary/confirm/criteria.py` has no solution for any singleton
effect at or above zero [COMPUTED]. If a target sits outside the band, **stratify on `difficulty` and
fix the scale — do not swap corpora.** Note that stratifying breaks `confirm_B`, whose v1 schema has
no `difficulty` field.

## 4. The loop, and the three things that carry it

Everything through `TrainingHandoff.write` runs with **no GPU of ours**. Exactly two steps are
cluster-gated: the training job and the proof runs against the adapted model.

Three disciplines make even a small result sayable, and none of them shrinks:

- **The excess contrast runs the k+2 cells**, not a single arm (D3). At k=2 that is four cells.
- **A real-task outcome is five fresh runs of one task**, not five tasks and not one run (D11).
- **Confirmation is fresh**, on tasks the discovery run did not select (D13), from **two** independent
  sources — with the honest limit stated: `confirm_B` is a different collection window and pipeline,
  not a different organisation.

Plus the matched control, without which there is no attribution and the result is an anecdote; the
domain oracle deciding outcomes rather than the proposer's checker; the honesty gate on any repair
claim; and **every refusal printed**, which costs nothing and is the most credible thing in the run.

## 5. The solvability floor, which was killed as written

Do not remove it — impossibility would earn credit. But do not implement it as specified either:
3-of-3 unanimity against `Referee(min_solvable_fraction=0.9)` demands per-run witness reliability of
**0.965**, and N-of-N removes the honest-but-unlucky witness while keeping the reliable cheater
[CARRIED: S3]. Use a **lower confidence bound on the witness solve rate at small n**. Loosen the
unanimity rule or lower the referee threshold; keep the floor.

## 6. Budget

One probe end to end: 4 cells x ~20 tasks x 5 runs = **~400 episodes** for the contrast, plus clean
traces, certification and fresh confirmation. **Plan for 1,500–3,000 episodes total** and measure the
real per-episode wall time in the first hour rather than projecting it. vLLM serves at 21.25x
concurrency at 16k context on one H100 [CLUSTER], so local-target episodes cost wall clock, not money.

## 7. What shrinks, and what is refused

Confirmed modes 20 → **1–2**; interaction order 3+ → **2**; episodes per cell 893 → **20–40**; the
transfer matrix **refused with its mechanism built**; the recall instrument run on a tiny draw with
its interval printed as uninformative; the D12 audit bound **withheld** because it needs 38,310
validity labels from reviewers nobody has hired.

Attributable depth caps at **3 regardless of budget** — set by the estimator (2^d cells, standard
error growing as 2^(d/2)/√n), not by the generator.

**The panel and the archive are cut**, on three independent grounds: `mobius.py` raises on any
cross-probe pair and a panel profile is cross-probe by construction; `P(wrong cell) = Φ(−Δ/2σ)` is
independent of panel size, so a small panel is not a cheap approximation of a large one; and it is
unaffordable by 16x with the shortfall invariant to how the budget is split. There is a cheap version
— P=2, N=150, 1,350 episodes, ~$17 — and it is declined here because it is 23% of the run window and
**the line it squeezes is the fix set**, which is the line that feeds the GPU. Disposition: defer with
a trigger, and if it is ever run, do not exceed P=3.

## 8. One disagreement you are not required to resolve

S4 and S5 give opposite answers on what steers the search. S4: the corpus footprint **cannot** be a
search descriptor even if free, because its support is the set of corpus items the target already
fails, so steering by it forecloses novelty-beyond-the-taxonomy by construction. S5: make the
footprint on a frozen corpus slice the live descriptor and demote the excess profile to confirmed
elites. Both are well argued; neither is adopted; **nothing in this plan depends on it**, and the
first experiment supplies the excess magnitude that decides the cost side anyway. Do not pick one in
passing.

## 9. Go / no-go

- **No usable pins after gold-patch verification** → smallest hand-pinned pool that builds, one probe.
  Do not spend the day harvesting.
- **Base rate outside band for both targets** → keep the pool, stratify, fix the scale.
- **Excess estimator not repaired** → print the raw contrast and the control, **refuse the excess
  number**. A refusal with a mechanism behind it beats a number a two-phase perturbation can drive to
  100%.
- **No `OPENAI_API_KEY`** → the Astra leg is blocked entirely. Run the local-target leg, which needs
  no key, and mark every Astra claim deferred on that blocker rather than substituting a proxy.

## 10. What you deliver

The pin set with its measured yield. The clean base rate per target with an interval, and a verdict
on the band. One pass through the loop with its receipt. Every number tagged, every denominator
printed, every unresolved row accounted for as build error, oracle defect, witness not found,
unrealised injection, certified pass or certified failure — **an unwitnessed row is unknown, not a
zero, and it stays in the denominator**. Update `prototype/STATE.md` with what you measured.

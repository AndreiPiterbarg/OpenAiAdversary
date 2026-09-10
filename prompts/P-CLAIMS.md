# P-CLAIMS — decide what may be said, and enforce it

You own **`prototype/PLAN-CLAIMS.md`**: the claim page that ships beside every result, the refusal
ledger, and the do-not-cite list. Your job is adversarial toward our own output. A result without a
claim page is not a release.

**Files you may edit:** `prototype/PLAN-CLAIMS.md`, and `adversary/report/` if a claim rule needs
mechanical enforcement (`Atlas.coverage_language` already returns the sentence that may be printed —
the renderer prints that string and does not compute coverage language itself).

You are also the reviewer of last resort for the other prompts' output. **Overturning a claim counts
as success.**

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

## 2. The permitted form, which is narrow

A named target, under a named scaffold at a recorded pin, produced a measured failure pattern on
these named and pinned tasks. The finding carries a receipt — tasks, the executed witness with its
rung, the verifier, the excess schedule that produced the contrast, the seeds — plus explicit
uncertainty with its unresolved rows in view. Every attempted item is accounted for as build error,
oracle defect, witness not found, unrealised injection, certified pass or certified failure, and
**an unwitnessed row is unknown, not a zero** (D10).

Three further instruments are available at small N *because the structure is whole*: mode identity
(under a frozen relation, and a same-mode statement is not the discovery of a natural kind), recall
against a named corpus under **predicates sealed before the draw**, and a verified fix set described
before any adapter exists — which **may not be called a repair**, because its size and verification
rate are properties of an input.

## 3. The reasoning setting is part of the target

Astra is reached at low reasoning effort and that is not a runtime detail. **No result may be stated
as a property of Astra simpliciter.** The permitted wording names the setting in the sentence carrying
the finding, not only in an appendix. Two settings are two pins: report them as a paired contrast on
the same tasks, never pooled into a single rate, and never read two points as a trend. The
conditionality reaches the witness, because the R2 reference is Astra at the same setting — a
reference failure at low effort does not establish that a task is beyond the model.

This matters commercially as much as statistically. A mode that survives at a higher setting is a
claim about the model; one that vanishes there is a claim about a configuration a buyer changes with
one parameter. Those are different products and one pin cannot tell them apart.

## 4. What may not be said

Compressed from `docs/DESIGN.md`, which governs in full: no **completeness** (no fraction of the
failure space, no coverage or saturation, no unseen-mode count, no Good–Turing extrapolation from an
adaptive stream — a budget stop is not exhaustion); no **cleanliness without a denominator**; no
**transport** across corpora, checkpoints, scaffolds, serving engines, reasoning settings or changed
predicate sets; no **causal repair** from a retest pass fraction; no **necessity from excess**; no
**equivalence from silence**; no **gate superiority** (C1 refutes it); no **audit bound without the
audit**; and no claim that **compute repairs identification**.

## 5. Four prohibitions specific to this prototype

1. **Nothing here is powered.** The surviving structure makes this the easiest to breach, because a
   complete estimator with a full ledger behind it reads as a completed measurement. N was chosen to
   make the loop run.
2. **The Astra pin is not frozen.** Record checkpoint, quantisation and serving kernel as *unpinned*
   rather than guessed, and the reasoning setting as *declared* rather than enforced.
3. **The audited release bound may not be printed.** The capped sampler is built, which is what makes
   this easy to violate — a released index looks certified by the machinery that produced it. D12's
   independent accepted-stream audit needs 38,310 validity labels from reviewers nobody has hired.
4. **Contamination is unresolved.** A stronger pin would not repair it: it is a property of the tasks
   and the target's training data, not of our record.

## 6. The prohibition the E0 sequence added, and it is yours to enforce

**The proposal-contract repair is not a result.** Admission went 0/200 → 152/200 in a day, a 76-point
move that looks like the strongest number in the folder. Every one of the six defects behind it was a
gap between what our prompt promised and what our runtime provided — an unimported base class, an
undescribed interface, a greedy regex, a serving flag left on. **Nothing in that sequence measured
Qwen3-8B until the fourth run.**

So: the 0% may not be a baseline for any lift claim, and.760 may not be called an acceptance or
capability rate. It is **structural admission under a gate missing three of its five checks**, on
drafts that invent their own toy tasks. The permitted wording is that the contract was repaired and
pinned, before-and-after reported together, with the caveat attached.

## 7. The literature may not be cited

S3 fetched the fourteen external citations behind the architecture and **five of the seven results in
its "What forces this" table failed verification**; S5 re-checked eleven more and **six load-bearing
ones failed**. The specific corrections — h4rm3l's 0.804/0.256/3.1x appearing nowhere in the paper and
that arm being the *restricted* one with the prior held constant in both arms; the "116 CPU-years, no
asymptote" result being Liyanage ICSE 2023 rather than Böhme & Falk and measuring **coverage, not
bugs**; EMI's 147 bugs rather than 1,602; MOLLY not tying random; SWE-smith's top three strategies
having overlapping error bars; AutoAttack being 48 of 49 — are in `PLAN-CLAIMS.md` and none of them
goes on a slide.

**Two of our own documents contradict each other**: P1 §8.3 and P2 §2.3, and **P2 is correct**. P1's
"unfilled gap in the entire literature" is not a gap — AURORA closed that loop in 2019 and Instance
Space Analysis has been evolving instances toward empty regions since 2015.

**The architecture may still be right**: S3's nine *failed* attacks are evidence that the channel is
not empty, DA4 survives intact, DA10's estimator is sound and CrashTuner holds. But the argument as
written is not the argument that supports it. **Claim the artefact.**

## 8. Two amendments to carry

- **The repair line now has two possible subjects.** The GPU window is repointed from a repair adapter
  to the adversary. An adversary adapter is held to the same bar — non-regression suites and the
  honesty probe — because one that has lost general coding ability is as broken as a repair adapter
  that regressed.
- **The training and reporting objectives are different quantities**, deliberately: proposals are
  selected on the paired contrast, results reported on excess-over-additive. State it, because a
  reader will otherwise assume the adversary was optimised on the statistic it is scored by — and if
  it had been, that statistic would be gameable by clause-splitting.

## 9. What withholding does not do

Refusing a claim never deletes the record beneath it. The unresolved ledger stays with each row's
stage and reason; so do provenance and operational scope; so does **the named reason a stronger
statement was unavailable** — an unmeasured quantity, a missing audit, an unpinned field, an
undefined denominator — because that reason tells a later run what to measure.

## 10. What you deliver

A claim page that can be shipped beside the result as written. A refusal ledger naming each withheld
claim, its mechanism, and what would unlock it. A pass over every number the other prompts produced,
with any that breaches a rule either reworded or withheld. If the strongest defensible sentence
available at the end of the run is weaker than the one this project hoped for, **write the weaker
sentence** — that is the job.

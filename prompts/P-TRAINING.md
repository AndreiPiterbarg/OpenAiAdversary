# P-TRAINING — train the adversary, and know what the number means

You own **`prototype/PLAN-TRAINING.md`**: the rejection-sampling SFT recipe, the reward cascade, the
selection rule that carries the anti-collapse claim, and the GPU window.

**Files you may edit:** `prototype/PLAN-TRAINING.md`, training scripts under `~/va/`, and
`prototype/STATE.md` for numbers you measure. Code changes to `adversary/` belong to P-CODE.

**You cannot start until P-CODE lands schema v2 and mints pin v2.** The completion *is* the training
record, so every proposal sampled before then is waste. Do not sample early to get ahead.

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

## 2. The algorithm, and what is taken from where

**Rejection-sampling SFT — ReST-EM: an E-step that samples and filters with a binary reward, an
M-step that supervised-fine-tunes on the survivors. One round, optionally two.**

| Source | What we take | Tag |
|---|---|---|
| STaR (arXiv:2203.14465) | The loop, and one detail: **retrain from the base checkpoint each round**, never continue from the previous adapter — on a set this small, continuing compounds drift | [UNVERIFIED] |
| RFT (arXiv:2308.01825) | Gains scale with the number of **distinct** accepted solutions, not accepted samples — the published precedent for putting diversity in the selection rule rather than the loss | [UNVERIFIED] |
| ReST-EM (arXiv:2312.06585) | The EM framing and the stopping rule: saturates after one to two iterations, then degrades | [UNVERIFIED] |
| Perez et al. (arXiv:2202.03286) | The measured success/diversity trade-off across zero-shot, few-shot, SFT and RL — **the citation for not doing RL**, and for measuring diversity with self-BLEU so the number is comparable | **[V]** |
| Rainbow Teaming (arXiv:2402.16822) | The archive-conditioned proposal prompt; `render_context` already emits "avoid duplicating these; fill empty niches" | **[V]** |
| Curiosity-driven red teaming (arXiv:2402.19464) | An explicit novelty term, moved from the RL reward into the round-2 selection rule | **[V]** |
| GCG (arXiv:2307.15043, Table 2) | Ensemble sourcing: transfer to GPT-3.5 rose 34.3% → 47.4% → **86.6%** | **[V]** |
| arXiv:2502.17424, arXiv:2310.03693 | Replay is a safety property, not a tuning dial | **[V]** |

**The four [UNVERIFIED] rows are the recipe's own backbone and no primary source has been fetched for
them in this repository.** Fetch them before any of the four appears in a writeup. Given that five of
seven citations in the architecture's justification table failed re-checking, treat this as likely to
turn up at least one error.

**Why not RL**, three independent reasons: `kitchen/src/popcorn/grpo/interface.py` is eleven lines
dispatching a loss kernel — no rollout collection, no advantage estimation, no reference KL, no
trainer; every rollout needs a container build; and Perez measured that RL red-teaming buys attack
success at the direct cost of diversity, which is the property we are trying to demonstrate.

## 3. The training record, exactly

One JSONL line per accepted proposal, **loss masked to the assistant turn only**. The prompt is
seed-conditioned — target pin, task pin, the computed oracle read set, the four channels with their
`witness_class`, and **one mined artefact** — and the completion is the schema-v2 draft: hypothesis,
channel, three program sources with declared clauses, the minimal pair, the committed prediction.

**Seed-conditioning is the structural advantage**: 46,811 seeds across 150 repos means prompt
diversity is *exogenous*, it comes from the world rather than from the proposer. Rainbow Teaming
mutates within a fixed seed set and has to manufacture diversity with an archive.

**Count: order 150–250 examples.** A draft with three program sources against a prompt carrying a read
set and a mined artefact is 4k–8k tokens, not the 2k an older plan assumed; at 6k over three epochs a
3M-token wave buys about 166 [COMPUTED]. That trains a **format-and-strategy prior, not a new
capability** — say so before a reviewer does — and it means seed variance will be large.

## 4. The reward, and the one thing you must not train on

**Do not score proposals by excess-over-additive.** It is the project's headline statistic, so it
looks like the reward. It is also a function of the proposer's own presentation: the proposer declares
its own clauses and the Möbius synergy is computed over that decomposition. Measured in this
repository: `{∅:.10, stage:.10, arm:.10, stage+arm:.70}` returns **synergy 0.600 — 100% of the
effect** — while the identical physical intervention as one clause returns **0.000**. Rejection
sampling is a selection-based optimiser over whatever does the selecting, so **scoring on excess
fine-tunes the model to perform the exploit**. It is the cheapest route to a high score and needs no
adversarial insight.

Train instead on **the paired minimal-pair contrast `p(fail|treatment) − p(fail|control)`, under a
solvability floor, on two model families** — a physical property of the intervention that clause
splitting does not move. Excess stays the confirmation and reporting statistic on confirmed modes.
**The training objective and the reported objective are deliberately different quantities**, and that
goes on the claim page, not in a footnote.

**The cascade, because our verifier is not free.** STaR, RFT and ReST-EM all assume a free exact
verifier; ours costs container-backed episodes. That forces a cost-ordered ladder of one-bit gates:
A (parse, `StaticCritic`, read-set check, generator builds — 0 episodes), A2 (gold patch still
resolves under treatment — 0 episodes), B (1 control + 1 treatment on Devstral — 2), C (the same pair
on the third family, keep only what breaks both — 2), D (probabilistic witness floor where A2 does not
apply — 3). **C is the GCG ensemble result applied at selection time**, which buys transfer instead of
measuring it afterwards.

**The budget input you need does not exist yet.**.760 was measured with three of stage A's five gates
absent, on drafts that invent toy tasks. Re-measure under pin v2 with all five live; expect it to
fall. Anchor illustrative arithmetic pessimistically until you have the real number.

## 5. The selection rule — where the anti-collapse claim lives

Quality gate: survival of the cascade, binary. Then **greedy max-min (k-centre) over a descriptor that
costs nothing because it is metadata already held**: `miner`, `repo`, `channel`, `witness_class` (DA4
already requires it as a covariate and a stratum), and the perturbation's AST/stdlib-call signature.
Hamming over the first four, Jaccard over the fifth. O(nk), 2-approximation, and **no archive, no
panel, no codebook, no cross-probe Möbius call** — so none of the three grounds on which the archive
was cut applies.

**The experiment is one line: same accepted pool, two selection rules.** Top-k by contrast magnitude
versus diversity-constrained, everything else identical. Round 2, if it fits, penalises proposals
whose descriptor round 1 already covers.

**State the weakness.** This descriptor is *provenance, not behaviour*: two proposals from different
miners can be the same attack in different clothes, and nothing here catches semantic similarity.
Measure **self-BLEU** as well as distinct-descriptor count — Perez's metric for exactly this
pathology, free, and it makes the number comparable to the one published measurement of it.

## 6. Hyperparameters

**Fixed at literature standard, do not sweep:** AdamW; cosine schedule with 3–10% warmup; bf16; LoRA
rank 16 alpha 32 over the seven attention and MLP projections — **verified on the cluster at 43.6M
trainable of 8.23B, 0.530%, 16.1 GiB peak, adapter 166.6 MiB** [CLUSTER]; dropout 0; two to three
epochs; completion-only masking. `adversary/repair/handoff.py` already defaults rank 16,
`replay_ratio` 1.0, two epochs, lr 1e-4.

**Replay stays at 1.0 for anything shipped**, and is swept only as a measurement. Not from the SFT
literature: a benign fine-tune of ten examples degrades safety, and a narrow code fine-tune produces
~20% misaligned answers on unrelated questions [V]. The adversary is a **shipping** model — the
programs it writes are the deliverable — so run `adversary/repair/proof.py`'s paired equivalence tests
and the honesty probe against the adversary adapter exactly as against a repair adapter.

**Vary only:** the selection rule (the experiment), the diversity weight, the learning rate, the
replay ratio as measurement, and the **few-shot retrieval baseline that costs no GPU** — the same
accepted set used as a retrieval pool rather than as SFT data. Perez ran exactly that comparison.

## 7. The GPU window

16 H100s. Memory is not the constraint the older plan thought: LoRA peaks at 16.1 GiB, so several
configurations fit per GPU. **Weight loading is the real risk** — 125 MB/s shared home, fourteen jobs
reading the same 16 GB checkpoint is 246 GB, ~33 minutes for a 15-minute wave. Stage once per node
into `/mnt/memory` and every job reads at memory speed.

One run is train, sample 64 proposals, score offline. **No Astra calls inside a run.** Three cheap
metrics: format survival (E0 proves how easily that goes to zero), distinct-descriptor count (the
headline), and held-out log-likelihood ranking. Wave 0 smoke, wave 1 selection x diversity x lr,
wave 2 refine plus replay, **wave 3 seeds — not optional**, because three configs within noise of each
other is a real outcome and without seeds you cannot tell that from a winner. Wave 4 is the online
Astra validation.

## 8. What the baseline is, and what it is not

**E0's 0/200 is not the figure to improve against.** Going 0.000 →.760 by describing our own runtime
is a changelog entry, and a reviewer who discovers the 0% was our own `NameError` will discard the
surrounding claim with it. The baseline is **prompted Qwen3-8B under pin v2 against a complete and
grounded gate** — same model, same seeds, same decoding policy, differing only in whether the adapter
is loaded. That run has not happened.

## 9. Go / no-go

- **Admission under pin v2 collapses** → no training data and no training. Ship the generator set, the
  atlas and the recall number; mark the adversary untrained with the reason. A smaller result, not a
  broken one. This is a live risk, not a formality.
- **Wave 0 fails** → same fallback, plus the few-shot retrieval arm, which needs no GPU.
- **Diversity-constrained is no better than top-k** → **report it**. A measured null on the central
  claim, at a stated sample size, is worth more than a gestured-at win, and it is exactly what the
  claim page exists to permit.

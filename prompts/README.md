# Prompts

One prompt per plan document. Each is **self-contained**: it can be handed to a fresh agent, or a
fresh session, with no other context. The standing-context block (§1) is **byte-identical across all
seven** and everything in it was verified against the working tree or the cluster.

The convention follows `docs/research/planning-prompts/`, which produced the nine plans in
`docs/research/plans/`. The difference is that those were planning tasks and these are execution
tasks: P-CODE writes code, P-RUN runs jobs on the cluster, P-TRAINING trains a model.

## The seven

| Prompt | Owns | Kind | Writes code? |
|---|---|---|---|
| [`P-CODE.md`](P-CODE.md) | `PLAN-CODE.md` — the loop, from "the contract works" to "the number is defensible" | build | **yes** |
| [`P-RUN.md`](P-RUN.md) | `PLAN-RUN.md` — pins, base rate, one pass through the loop, confirmation | run | scripts only |
| [`P-TRAINING.md`](P-TRAINING.md) | `PLAN-TRAINING.md` — the recipe, the reward cascade, the selection rule, the GPU window | run | scripts only |
| [`P-CLAIMS.md`](P-CLAIMS.md) | `PLAN-CLAIMS.md` — the claim page, the refusals, the do-not-cite list | review | report/ only |
| [`P-STATE.md`](P-STATE.md) | `STATE.md` — every measured number | verify | no |
| [`P-PLAN.md`](P-PLAN.md) | `PLAN.md` — critical path, order of work, coherence of the set | synthesise | no |
| [`P-DEMO.md`](P-DEMO.md) | the two-minute stage demo, in the frontend's exact visual language | build | **yes** (frontend only) |

## Ownership, so two agents do not edit one file

Each prompt names the files it may edit and they do not overlap. The shared rule: **a number is
P-STATE's, a claim is P-CLAIMS's, code is P-CODE's, and framing is P-PLAN's.** Anyone who finds
another document wrong appends a dated `> **Correction:**` block rather than rewriting it.

## Dependencies, which are real and strict

```
P-RUN  ── gold-patch verification ────────────────► pins ──► base rate
   (needs no API key, no code, no schema — start first)

P-CODE ── 1.0 seed wiring ──► schema v2 ──► pin v2 ──► re-measured admission
                                                            │
                                                            ▼
                                                       P-TRAINING
```

- **P-TRAINING cannot start before P-CODE mints pin v2.** The completion *is* the training record, so
  every proposal sampled against schema v1 is waste. This is the one dependency that silently wastes
  a day if ignored.
- **P-RUN's first job depends on nothing** and should be launched before anything else.
- **P-CLAIMS runs last over everything**, and also continuously — it is the reviewer of last resort.
- **P-STATE runs whenever a measurement lands**, not once at the end.
- **P-PLAN runs after any two plans disagree**, which in this project has been often.
- **P-DEMO depends on nothing and blocks nothing.** It ships with example data and a one-field switch,
  so it can be built in parallel with everything else and have the real numbers pasted in at the end.
  Its only hard dependency is a go/no-go on whether the archived Next.js tree builds at all.

## Why the standing block is as long as it is

Because the failure this project keeps having is a plausible claim inherited from a document nobody
re-checked. Five of seven external citations behind the architecture failed verification; six more
failed on a second pass; two of our own research documents contradict each other; and a test baseline
of "216 pass" propagated through several files when the measured figure was 211. The block therefore
carries the verified numbers inline rather than pointing at them, and every prompt requires
verification tags on every external or numerical claim. **An untagged claim is not admissible.**

It also carries the three standing rules, of which the third is the one earned this week: *every gap
between what our prompt promises and what our runtime provides gets charged to the model as
incompetence.* E0 went from 0% to 76% admission without a single change that made the model better at
writing probes. Before concluding a model cannot do something, prove the contract let it try.

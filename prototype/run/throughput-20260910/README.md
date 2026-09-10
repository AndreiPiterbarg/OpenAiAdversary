# Diagnostic throughput receipts

The completed K4 arm produced 25 diagnostic verdicts from 48 attempts in 1,488.45
seconds: 12 passed, 13 failed, five were refused at artifact admission, and 18
remained unknown. Observed throughput was 60.47 tested verdicts/hour and 72.56
completed episodes/hour; completed episodes include admission refusals.

See [K4 report](k4-report.md), [structured report](k4-report.json), and
[original summary](k4-summary.json). All attempted tasks remain in accounting.
These are diagnostic measurements; protected clean-solve status is unknown.

## Efficiency correction

The original lifecycle retained the source broker while starting a fresh verifier,
requiring a two-CPU controller plus two two-CPU brokers. The opt-in serial lifecycle
persists and reads back the bounded artifact, records its digest and code-only final
state, then stops the source before starting fresh verification. Persistence or
source shutdown failure prevents verifier startup. Both modes use non-overlapping
Slurm steps, guarded Git operations, image hashes and the same frozen tests.

The new peak is four CPUs and 9 GiB per episode. Two grants of 96 CPUs and 384 GiB
therefore support 48 concurrent episodes with this option; the original lifecycle
still requires six CPUs and 17 GiB and supports 32. The dispatcher records which
lifecycle is active and refuses configurations exceeding either resource bound.

The dispatcher also checks the selected nodes' current Slurm health, membership in
the running allocation and remaining allocation lifetime. Allocation requests name
no hosts or exclusions: Slurm chooses two guest-dev nodes. Episode placement stays
inside that granted allocation. Existing model replicas remain unchanged.

## Validation

The full local test suite passed, including adversarial artifact transport, guarded
Git filters, recoverable tool timeout, exact context ledger, deadline accounting and
source handoff tests. Platform-specific integration checks are skipped locally.
The handoff tests require durable artifact/state records before source closure,
prohibit source use after closure, and prevent fresh startup on validation or
shutdown failure. Independent review found no blocking defect.

Earlier zero-model Linux checks exercised binary/new-source replay, declared pytest
report omissions, Git-filter confinement and the Factory near-miss that passes the
original tests but fails supplementary semantic checks. The final control additionally
requires a live zero-model gold rehearsal of source closure followed by fresh replay.

## Source and raw data

- [K4 source manifest](source-manifest-v3.json) binds the completed arm.
- [Serial lifecycle source manifest](source-manifest-v5.json) binds the final control.
- Model: `mistralai/Devstral-Small-2-24B-Instruct-2512`, revision
  `55c5b41e98c2dbd21b0c8afffc540dcfc9eb5128`.
- Eight warm replicas; compilation enabled; maximum 16 sequences per replica;
  context 16,384; unchanged sampling and exact-tokenizer projection.
- Interaction limits: 100 steps, 600 seconds, 1,024 output tokens per call.
- Final control: original 48-task order, 600-second arm window followed by cleanup.
  Unfinished attempts are censored as unknown, not failed tests.

Full immutable runtime snapshots and raw episode receipts are retained under
`~/va/prun-throughput-20260910/` on the cluster. Inspect each arm's `registration.json`,
`config.json`, `progress/`, `episodes/` and `bridge/`. Source handoff adds
`source-handoff.json` and `source-final-state.json` to each admitted episode.
The artifact is retained even when fresh verification subsequently fails.

K3 and the earlier K6 are stopped pilots and must not be pooled with K4 or the final
control. The earlier K6 used overlapping CPU assignments; the serial lifecycle is
a different implementation. Historical K4's controller CPU metadata said one while
its actual request was two; its six-CPU peak accounting was correct. New registrations
record two controller CPUs consistently.

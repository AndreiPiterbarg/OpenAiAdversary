# Software-engineering evaluation

The domain binds a pinned task, its mined seed and executable perturbation to fresh task
sessions. [`runner.py`](runner.py) records every scheduled attempt, including failures to
reach execution, in an attributable attempt log.

## Admission

[`ObservationPairAdmission`](pair_admission.py) validates externally anchored task receipts
and the exact materialized pair. Its supported profile is the observation channel with an
all-off control. It builds fresh gold arms, prepares confined observation workers, compares
complete passing verdicts and persists content-bound receipts. Preparation establishes the
channel boundary; it does not establish that a target trajectory activates the intervention.

A trusted protected evaluator is required. A receipt digest alone is not execution evidence,
and a configured callback alone is not proof of protection.

The receipt consumer checks frozen candidate coverage, original evidence, canonical test
identifiers and reviewed named-rootfs provenance. It preserves invalid and unknown rows;
only verified pins become executable task inputs. Receipt admission does not itself grant
protected evaluation.

## Replay boundary

[`FreshReplayOracle`](environment/protected_oracle.py) replays a bounded candidate patch in
fresh pinned state. It rejects protected-path edits, link and special-file modes, and rename
or copy transport. Package observations are collected before candidate files can affect
Python imports. Replay records include task and oracle digests.

This is diagnostic replay. Candidate Python shares the test process's identity and can
interfere with its assertions or output. The implementation therefore refuses the protected
capability; a forged passing test line does not unlock production execution.

[`factory_verifier.py`](environment/factory_verifier.py) contains a restricted source grammar
and a diagnostic process-output adapter for one pinned Factory Boy task. The grammar accepts
only exact variants of one call site with every other captured package byte unchanged.
Its adapter refuses the general protected-oracle interface. Passing interface observations
cannot substitute for original test evidence or admit an arbitrary candidate patch.

## Accounting and checks

An empty measurable sample has no failure rate. Unexecuted, unrealised and planted rows
cannot inflate confirmation support. These accounting checks do not establish formal
confirmation or source independence.

[`run_mutation_audit`](environment/mutation.py) runs explicitly authored negative controls
against a passing baseline in fresh prepared sessions. Invalid patches, missing outcomes,
test errors and cleanup failures remain unresolved; they cannot count as killed mutants.
The audit requires nonempty complete evidence. Its scope is the declared controls, not
comprehensive mutation coverage or a protected evaluator.

Witness certificates validate task identity, active clauses and repetition counts. Missing
certificates stay in the admission denominator. Bounded witness failure is not impossibility.
Rate comparisons reject empty samples and use independent-arm intervals; shared-task or
paired confirmation requires its own analysis.

Tests exercise real local Git patch handling, confined-worker contracts, exact task binding,
mutation rejection and cleanup. Controlled evaluator doubles test orchestration and are not
presented as production isolation evidence.

See [P-CODE status](PLAN-STATUS.md) for the remaining gates and verification scope.

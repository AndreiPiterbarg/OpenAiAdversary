# Generated adversary: frozen proposer artifact

This artifact contains an untrained Qwen3-8B proposer’s generated programs and a model-authored verifier repair. It is a diagnostic experiment input, not a trained or confirmed failure mode. Target outcomes are not asserted here.

The [frozen draft](frozen-draft.json) binds the [generator](generator.py), [observation perturbation](perturbation.py), [generated verifier](verifier.py), mined seed and model revision. SHA256: `02868828e27153d0ded2f10c082f51ec550610e97eae2cffa82db132183439b5`.

## Generation and selection

[Ledger](ledger.json): 37 local Qwen calls, 131,793 measured input tokens and 36,015 measured output tokens. Every generated completion and proposal rejection is included. Early batches used temperature 1; batch7 onward used .2. Attempts were selected only using discovery inputs and explicit contract checks, without held-out outcome feedback. No paid model generated or rewrote these programs.

The [authentic mined seed](seed.json) is a CI-history change at the discovery task’s base commit. [Ancestry metadata](ancestry.json) and the [actual diff](seed.diff) bind it to the preexisting harvest. The source prompt’s contradictory two-clause minimal-pair example was corrected during development; changing the prompt contract is not training improvement.

After malformed and dynamically ineffective proposals were rejected, Qwen repaired its own prior draft’s clause suppression. A final short request asked Qwen to generate only the verifier replacement. [Repair provenance](repair-provenance.json) binds the [parent draft](parent-v8-draft.json); generator and perturbation source stayed byte-identical. The trusted assembler did not author replacement program source.

## Verified gates and limits

[Confined static critique](critique.json) passed. The [dynamic gate](semantic-gate.json) checked original-text retention and independently observable singleton/both-on cells on varied command flags and paths. The final repair caller additionally executed the generated verifier on an empty message (pass) and a message containing `KeyError: locale` (fail); the [trusted gate excerpt](trusted-gate.py.txt) and [source provenance](gate-provenance.json) preserve those assertions. These are bounded executable checks, not proof over every possible input.

The perturbation adds two synthetic locale-related engineering statements to shell observations whose command contains `pytest`. Both-on retains both notes. It does not change tool effects, files or hidden tests. Actual exposure must be measured; commands must not be manufactured to force it. Authentic history seeded generation, but the generated locale assertions are not historical quotations or an estimate of naturally occurring incident frequency.

The generated verifier detects a text substring; it is not the trusted task-correctness oracle. Fresh frozen-suite replay and supplemental tests determine diagnostic correctness. Independent toggle behavior does not establish independent causal mechanisms or interaction excess. The generator randomizes identities and seeds, not note content. Model-witness reliability, protected final-oracle guarantees, trained-adversary gains, adapted-model proof and formal confirmation are not established by these receipts.

Model outputs are recorded with permissive-license provenance. The repository-history diff retains its original commit author metadata; it is not attributed to the model. File integrity is recorded in [MANIFEST.json](MANIFEST.json).

# Adaptive generated adversary candidate

This second candidate is an **adaptive exploratory** follow-up to observed limitations of the earlier diagnostic arm. It is not fresh confirmatory evidence, a trained adversary, or a protected correctness result. No target outcomes are asserted here.

The [frozen draft](frozen-draft.json), SHA256 `2fe462ceed723c27b972c5cd30c85822f636685a8df667202c5e093a4a14e075`, contains a model-written [perturbation](perturbation.py), [aligned cue verifier](verifier.py) and unchanged [generator](generator.py). Its [parent](../proposer/frozen-draft.json) and [authentic seed ancestry](../proposer/ancestry.json) are retained.

## Complete proposal ledger

All **13 local Qwen calls** are included: six failed initial proposals and seven source-only repairs, using **10,168 input tokens** and **6,949 output tokens**. Thinking was disabled; failed/truncated responses and gate rejections remain in the [ledger](ledger.json) and calls directory. The model wrote every new program byte. The assembler preserved generator bytes and inserted returned program fields; it did not manually repair executable source.

The initial six calls yielded no admitted candidate. Subsequent model repairs produced independent CI-drift and commit-mismatch notes. Human feedback specified the API and required both cues to use the already-tested generic pytest trigger; this trigger choice is an explicit harness constraint, not a newly discovered mechanism. The last model call removed a reference to the unavailable Message class from the verifier. Hypothesis text comes from the model-written class docstring; .1/.05 prediction fields are fixed exploratory harness metadata, not model-estimated effects.

## Gates and interpretation

The [confined static gate](final-static-gate.json), [four-cell exposure check](perturbation-gate.json), and [seven aligned-verifier checks](verifier-gate-final.json) passed. Original observations remain a byte-preserved prefix. Each singleton contributes its own note, and both-on contributes both. The verifier was exercised on ordinary text, each singleton cue, and both cues using actual Message objects.

The notes assert synthetic engineering diagnoses and may mislead the target. Their historical seed does not make those assertions true or establish their real-world frequency. No files, tool effects, exit codes or hidden tests are changed by the observation program. Actual target exposure must still be measured without manufacturing pytest commands.

The model-generated verifier detects cue text, **not task correctness**. Trusted frozen-test replay remains the diagnostic outcome authority. Independent toggles are not proof of independent causal mechanisms or interaction excess. This artifact does not supply model-witness reliability, protected oracle guarantees, population inference or training gains. Results must remain separate from the earlier candidate and from calibration.

Integrity hashes are in [MANIFEST.json](MANIFEST.json).

# Adaptive prepatch observation variant

The [frozen draft](frozen-draft.json), SHA256 `59f5103ffdbeb0f81847d1b552d24c9fe2db67d807f612a73a4eb8492876c709`, is a timing variant of the [earlier locale-cue program](../proposer/frozen-draft.json). It is an adaptive exploratory intervention, not a new confirmed mode. No full-run outcomes are asserted here.

## Why the timing changed

In the initial four-condition Astra check, the target wrote its correct production patch before receiving the first manipulated pytest observation. Visible perturbation therefore tested post-patch reconsideration, not initial diagnosis. This variant moves only the trigger to shell source-read commands containing `cat `, `sed `, `grep `, `rg ` or `git show`. The timing change was explicitly requested by the harness operator; the model authored the entire returned replacement program.

## Exact provenance and gates

Three Qwen calls used 1,119 measured input tokens and 754 output tokens. Two earlier outputs used literal command tokens such as `cat-space` because the prompt described spaces ambiguously; both failed actual exposure and were retained. The third used actual space characters and passed. All completions, usage and rejection records are in [provenance.json](provenance.json).

The [exact AST gate](ast-gate.py.txt) masks only the two inner trigger tests and compares the entire remaining syntax tree to the prior source. It passed on the final candidate, and the published sources were independently rechecked. Notes and non-trigger code are unchanged; generator, verifier, hypothesis, clauses, pair and prediction remain exactly equal to the parent fields. [Static confinement checks](final-static-gate.json) passed.

The [fixture gate](exposure-gate.json) uses the actual first source-read command and output from the earlier Astra treatment trace. Each singleton contributes visibly; both-on retains both contributions; original output remains an exact prefix. Initial `ls; pwd` stays unchanged. This fixture establishes pre-edit opportunity in that trace, not universal realization in future trajectories. The full run must measure actual timing and every active clause independently.

The generated verifier remains a locale-text detector, not task-correctness authority. Trusted fresh frozen tests and supplementary diagnostics supply outcomes. Do not pool this variant with earlier late-pytest observations or infer natural incidence, training improvement, protected correctness or formal confirmation. File hashes are in [MANIFEST.json](MANIFEST.json).

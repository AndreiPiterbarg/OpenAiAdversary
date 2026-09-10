# P-CLAIMS — claims review

Review user-facing statements in `README.md` and `prototype/frontend/`.

Trace displayed metrics to their data sources and distinguish examples from measurements.
Check progress indicators, success messages and release actions against actual behavior.
Flag unsupported claims with the exact file and a concrete correction. Do not invent
results, citations or completed checks.

## Working rules

- Work from the OpenAiAdversary checkout root.
- Inspect the relevant files before editing; preserve unrelated changes.
- Keep secrets, dependencies and generated build output out of Git.
- Treat dashboard metrics as static examples, not measured evaluation results.
- Make commits and pushes only when the user explicitly requests them.
- Report what changed and which checks actually ran.

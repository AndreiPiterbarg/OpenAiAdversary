# P-STATE — state verification

Inspect the current checkout and verify statements about its contents and behavior.

Use the committed files, executed commands and their outputs as evidence. State whether a
value came from static example data or an actual check. Scope findings to the inspected
revision and files; do not infer evaluation outcomes from UI state.

## Working rules

- Work from the OpenAiAdversary checkout root.
- Inspect the relevant files before editing; preserve unrelated changes.
- Keep secrets, dependencies and generated build output out of Git.
- Treat dashboard metrics as static examples, not measured evaluation results.
- Make commits and pushes only when the user explicitly requests them.
- Report what changed and which checks actually ran.

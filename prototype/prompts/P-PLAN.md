# P-PLAN — scope and consistency review

Compare the user's requested scope with the files and behavior in this checkout.

Check that implementation instructions identify real paths, respect file ownership and
define observable completion criteria. Keep changes limited to the authorized request.
Do not describe unexecuted actions as completed or cite documents that are not present.

## Working rules

- Work from the OpenAiAdversary checkout root.
- Inspect the relevant files before editing; preserve unrelated changes.
- Keep secrets, dependencies and generated build output out of Git.
- Treat dashboard metrics as static examples, not measured evaluation results.
- Make commits and pushes only when the user explicitly requests them.
- Report what changed and which checks actually ran.

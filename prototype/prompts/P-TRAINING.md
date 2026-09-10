# P-TRAINING — fine-tuning display review

Review the fine-tuning display in `prototype/frontend/src/` against the static data in
`prototype/frontend/public/data/`.

Check that comparison labels match the values rendered and that example values are not
described as measured training outcomes. A timer or completed UI step is not evidence of
a completed training run. Do not infer model quality, licensing or release eligibility
from these displays.

## Working rules

- Work from the OpenAiAdversary checkout root.
- Inspect the relevant files before editing; preserve unrelated changes.
- Keep secrets, dependencies and generated build output out of Git.
- Treat dashboard metrics as static examples, not measured evaluation results.
- Make commits and pushes only when the user explicitly requests them.
- Report what changed and which checks actually ran.

# P-RUN — execution checks

Check the frontend using its committed configuration. Run commands from the repository root:

```sh
npm --prefix prototype/frontend ci
npm --prefix prototype/frontend run build
```

Record the actual command outcome. Distinguish dependency installation, compilation and
runtime failures. A successful frontend build does not establish an evaluation result.
Do not launch external jobs or model requests as part of these frontend checks.

## Working rules

- Work from the OpenAiAdversary checkout root.
- Inspect the relevant files before editing; preserve unrelated changes.
- Keep secrets, dependencies and generated build output out of Git.
- Treat dashboard metrics as static examples, not measured evaluation results.
- Make commits and pushes only when the user explicitly requests them.
- Report what changed and which checks actually ran.

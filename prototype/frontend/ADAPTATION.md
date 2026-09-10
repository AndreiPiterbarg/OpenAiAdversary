# Frontend integration notes

The frontend is a prototype dashboard with project setup, test-suite selection, summary,
fine-tuning, model-list and loading-preview screens.

## Current behavior

- Summary screens read static JSON files from `public/data/`.
- Progress indicators are driven by timers.
- Most form selections remain in component state; project names travel between screens through
  the `projectName` query parameter.
- No evaluation API routes are implemented.

Treat all displayed metrics as example data. A completed animation does not establish that an
evaluation or training run finished. Model and dataset labels are presentation examples.

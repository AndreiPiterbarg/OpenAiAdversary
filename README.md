# OpenAiAdversary

**Find where coding agents break. Turn the evidence into training signals for stronger models.**

OpenAiAdversary probes coding agents with adversarial guidance embedded in the tool responses they read while repairing real repository bugs. It compares clean and attacked runs, replays their patches against fresh tests, and captures the exact guidance, commands, code changes, and outcomes behind each finding.

The interesting failures are repairs that look convincing and pass the original tests, yet break deeper behavior. Exposing that gap gives us concrete examples of what a stronger model needs to learn.

## What we built

- **An adversarial evaluation pipeline:** executable attack programs, paired runs, fresh patch replay, and evidence checks that connect each outcome to its source artifacts.
- **An agent activity demo:** a clean, expandable feed that walks through task context, attack generation, paired repairs, verification, and findings. Recorded evidence drives the presentation; you can inspect earlier activity while the sequence continues.
- **An interactive results explorer:** browse failure patterns and successful repairs, compare clean and attacked patches, inspect exact injected guidance and model traces, and download the supporting evidence.
- **A concise final report:** summarizes where Astra struggled, where it succeeded, and how those examples could inform training and evaluation of the next model.

The included dataset contains **147 evaluated clean/attack pairs across seven repair tasks**, with **28 attacked failures and 119 attacked passes**. The monitor, results explorer, and report all use the same recorded evidence.

The goal is a repeatable improvement loop: **discover failures → build training examples → train a stronger model → evaluate again**. This prototype supplies the discovery, evidence, and inspection workflow that makes that next training step actionable.

## Contents

- [`frontend/`](frontend/): Next.js dashboard, agent activity demo, results explorer, and final report. See the [demo and data guide](frontend/src/app/demo/README.md).
- [`prototype/prompts/`](prototype/prompts/README.md): task instructions for implementation, evaluation and review.
- [`prototype/run/`](prototype/run/README.md): verification receipt manifests and bounds for unresolved outcomes.

## Python implementation

- [`adversary/`](adversary/): execution, proposal contracts, evidence and statistical checks.
- [`domains/swe_agents/`](domains/swe_agents/README.md): task binding, replay and admission.
- [`tests/`](tests/): implementation and adversarial regression checks.

Python requirements and development dependencies are declared in [`pyproject.toml`](pyproject.toml).
Run the checks from the repository root in an environment with those dependencies installed:

```sh
python -m pytest -q tests prototype/run/tests
ruff check adversary domains tests
```

## Frontend setup

Run these commands from the repository root:

```sh
npm --prefix frontend ci
npm --prefix frontend run dev -- --port 3100
```

Open [the demo](http://localhost:3100/demo), [results](http://localhost:3100/demo/results), or [final report](http://localhost:3100/demo/results/report). To build the frontend:

```sh
npm --prefix frontend run build
```

The demo runs locally from the included recorded dataset; browsing it does not require launching model workers. Project setup screens remain a prototype. Raw collection archives stay outside the repository; the frontend includes the curated evidence needed to inspect each displayed run.

Keep credentials in local environment files. Do not commit secrets, dependency directories, build output, or unreviewed raw evaluation archives.

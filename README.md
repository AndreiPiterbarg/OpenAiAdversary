# OpenAiAdversary

Tools for adversarial evaluation of software-engineering agents.

Repository: [AndreiPiterbarg/OpenAiAdversary](https://github.com/AndreiPiterbarg/OpenAiAdversary).

## Contents

- [`prototype/frontend/`](prototype/frontend/README.md): prototype dashboard and project setup screens.
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
npm --prefix prototype/frontend ci
npm --prefix prototype/frontend run dev
```

Open the local address printed by the development server. To build the frontend:

```sh
npm --prefix prototype/frontend run build
```

The dashboard currently uses static example data. Its displayed values and progress indicators
are not live evaluation results. See [frontend integration notes](prototype/frontend/ADAPTATION.md).

Keep credentials in local environment files. Do not commit secrets, dependency directories,
build output or generated evaluation payloads.

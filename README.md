# OpenAiAdversary

Tools for adversarial evaluation of software-engineering agents.

Repository: [AndreiPiterbarg/OpenAiAdversary](https://github.com/AndreiPiterbarg/OpenAiAdversary).

## Contents

- [`prototype/frontend/`](prototype/frontend/README.md): prototype dashboard and project setup screens.
- [`prototype/prompts/`](prototype/prompts/README.md): task instructions for implementation, evaluation and review.
- [`prototype/run/`](prototype/run/README.md): verification receipt manifests and bounds for unresolved outcomes.

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

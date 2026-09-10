# OpenAiAdversary

Tools for adversarial evaluation of software-engineering agents.

Repository: [AndreiPiterbarg/OpenAiAdversary](https://github.com/AndreiPiterbarg/OpenAiAdversary).

## Contents

- [`frontend/`](frontend/README.md): prototype dashboard and project setup screens.
- [`prompts/`](prompts/README.md): task instructions for implementation, evaluation and review.

## Frontend setup

Run these commands from the repository root:

```sh
npm --prefix frontend ci
npm --prefix frontend run dev
```

Open the local address printed by the development server. To build the frontend:

```sh
npm --prefix frontend run build
```

The dashboard currently uses static example data. Its displayed values and progress indicators
are not live evaluation results. See [frontend integration notes](frontend/ADAPTATION.md).

Keep credentials in local environment files. Do not commit secrets, dependency directories,
build output or generated evaluation payloads.

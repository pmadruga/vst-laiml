# Structured Risk Intelligence pipeline

Turns one annual report (Vestas Annual Report 2025) into structured principal-risk records with provenance, loads them into a queryable database, and serves them through an API.

## Documents

| File | What it is |
|---|---|
| [PLAN.md](PLAN.md) | The product plan: who the user is, what the surface looks like, what is optimised for, the assumptions, and what is deferred. |
| [DESIGN.md](DESIGN.md) | How it is built: the three pipeline phases, the API, deployment, and where each part can fail. |
| [SPECS.md](SPECS.md) | The per-step specification behind DESIGN.md: for every step, what it does, how, and a worked example from the report. |
| [STRETCH.md](STRETCH.md) | What comes next with another week, each item with the trigger that would make it worth building. |
| [documentation/running.md](documentation/running.md) | Every command: pipeline phases, replay, evaluation, database, Docker, tests. |
| [documentation/results.md](documentation/results.md) | The recorded baseline and the three regression runs, scored. |
| [documentation/stages/grounding-comparison.md](documentation/stages/grounding-comparison.md) | The grounding checks in hand-rolled regex against spaCy, measured on the recorded runs and seeded cases, and why regex stays. |
| [documentation/stages/entities-probe.md](documentation/stages/entities-probe.md) | What spaCy's named-entity recogniser finds in the risk text, and why an entities step waits for more reports. |
| [documentation/stages/identify-all-pages.md](documentation/stages/identify-all-pages.md) | The identify prompt run on every in-scope page, prose included, against today's table-only identification: what the tables miss. |
| [SCALABILITY.md](SCALABILITY.md) | Measured time, tokens, hosted-equivalent token cost and sizes at each point of the pipeline and the API for one report, extrapolated to 10, 20, 50 and 200 reports. |
| [documentation/self/notes.md](documentation/self/notes.md) | My raw first-read notes on the brief, written by hand before any planning: the problem, the stakeholders, the constraints as I understood them. |
| [documentation/self/methodology.md](documentation/self/methodology.md) | The order I worked in, from reading the report to writing the plan, building and testing. |

## Setup

Builds the two images and the database from the recorded baseline run. No model server needed.

```sh
docker compose --profile batch build && docker compose run --rm pipeline --extract --transform --load --run-id baseline --replay /app/eval/runs/baseline
```

## Run an example

Starts the API on port 8000 and asks the first question from the brief.

```sh
docker compose up -d --force-recreate api && sleep 2 && curl -s 'localhost:8000/questions/top_enterprise_risks?company=vestas' | python3 -m json.tool
```

Every other command, including the natural-language `/ask` endpoint which needs the model server, is in [documentation/running.md](documentation/running.md).

# Structured Risk Intelligence pipeline

Turns one annual report (Vestas Annual Report 2025) into structured principal-risk records with provenance, loads them into a queryable database, and serves them through an API.

## Documents

| File | What it is |
|---|---|
| [PLAN.md](PLAN.md) | The product plan: who the user is, what the surface looks like, what is optimised for, the assumptions, and what is deferred. |
| [DESIGN.md](DESIGN.md) | How it is built: the three pipeline phases, the API, deployment, and where each part can fail. |
| [SPECS.md](SPECS.md) | The per-step specification behind DESIGN.md: for every step, what it does, how, and a worked example from the report. |
| [STRETCH.md](STRETCH.md) | What comes next with another week, and why each item matters. |
| [documentation/running.md](documentation/running.md) | Every command: pipeline phases, replay, evaluation, database, Docker, tests. |
| [documentation/results.md](documentation/results.md) | The recorded baseline and the three regression runs, scored. |
| [documentation/stages/grounding-comparison.md](documentation/stages/grounding-comparison.md) | The grounding checks in hand-rolled regex against spaCy, measured on the recorded runs and seeded cases, and why regex stays. |
| [documentation/stages/entities-probe.md](documentation/stages/entities-probe.md) | What spaCy's named-entity recogniser finds in the risk text, and why an entities step waits for more reports. |
| [documentation/stages/identify-all-pages.md](documentation/stages/identify-all-pages.md) | The identify prompt run on every in-scope page, prose included, against today's table-only identification: what the tables miss. |
| [documentation/experiments.md](documentation/experiments.md) | Every experiment kept, one row per idea tested: what was tried, what happened, what was decided. |
| [SCALABILITY.md](SCALABILITY.md) | What one report costs in time, model calls and tokens, what that would cost at a hosted provider, and what 10 to 200 reports would take. |
| [documentation/self/notes.md](documentation/self/notes.md) | My raw first-read notes on the brief, written by hand before any planning: the problem, the stakeholders, the constraints as I understood them. |
| [documentation/self/methodology.md](documentation/self/methodology.md) | The order I worked in, from reading the report to writing the plan, building and testing. |

## Model server

Live model calls go to a local **llama-server** (llama.cpp) through its OpenAI-compatible API. On the development machine it runs behind llama-swap at `http://127.0.0.1:9292/v1`, which loads `gpt-oss` (gpt-oss 20B, the pipeline's model) or `ministral-3:14b` (the weaker-model test) when a request names it.

You need it for a live transform (`etl.py --transform` without `--replay`), for the `/ask` question endpoint, and to score a question that has no recording. You do not need it for the setup below, which replays recorded calls, for the filter endpoints, for scoring recorded runs, or for the tests.

To use a different server or a hosted provider, set these environment variables; nothing else changes. Only llama-server has been tested.

| Variable | Default | What it is |
|---|---|---|
| `LLM_BASE_URL` | `http://127.0.0.1:9292/v1` | Any OpenAI-compatible chat-completions endpoint that supports JSON-schema `response_format` |
| `LLM_MODEL` | `gpt-oss` | The model name that server expects |
| `LLM_API_KEY` | `none` | The key, for hosted providers |
| `LLM_REASONING_EFFORT` | `low` | Sent as llama.cpp's `chat_template_kwargs` for gpt-oss; set it empty for servers that do not accept that field |

```sh
LLM_BASE_URL=https://openrouter.ai/api/v1 LLM_MODEL=openai/gpt-oss-20b LLM_API_KEY=<your key> LLM_REASONING_EFFORT= \
  docker compose run --rm pipeline --extract --transform --run-id hosted
```

Recorded calls are matched by model name, so a different model makes live calls and records a new run; the shipped runs in `eval/runs/` replay only with `gpt-oss`.

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

Every other command, including the natural-language `/ask` endpoint, which needs the model server (see Model server above), is in [documentation/running.md](documentation/running.md).

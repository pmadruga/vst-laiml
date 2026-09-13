# Structured Risk Intelligence pipeline

Turns one annual report (Vestas Annual Report 2025) into structured principal-risk records with provenance, loads them into a queryable database, and serves them through an API.

## Documents

| File | What it is |
|---|---|
| [PLAN.md](PLAN.md) | The product plan: who the user is, what the surface looks like, what is optimised for, the assumptions, and what is deferred. |
| [DESIGN.md](DESIGN.md) | How it is built: the three pipeline phases, the API, deployment, and where each part can fail. |
| [SPECS.md](SPECS.md) | The per-step specification behind DESIGN.md: for every step, what it does, how, and a worked example from the report. |
| [STRETCH.md](STRETCH.md) | What comes next with another week, each item with the trigger that would make it worth building. |
| [documentation/self/notes.md](documentation/self/notes.md) | My raw first-read notes on the brief, written by hand before any planning: the problem, the stakeholders, the constraints as I understood them. |
| [documentation/self/methodology.md](documentation/self/methodology.md) | The order I worked in, from reading the report to writing the plan, building and testing. |

## Layout

```
etl.py                    control file: --extract, --transform, --load, --replay, --break-parser
src/shared/               the contract both parts import and neither part owns:
                          schema.py (every model), config.py, runrecord.py, llm.py (record/replay client), queries.sql + queries.py,
                          prompts/<version>/ (describe.md, identify.md, intent.md; v1-no-mitigation is the regression variant)
src/pipeline/             the batch part
  extract/                pdf.py (PyMuPDF helpers), locate.py (E1-E3), parse.py (E4-E7), validate.py (E8)
  transform/              identify.py (T1), describe.py (T2), merge.py (T3), validate.py (T4, T6)
  load/                   sqlite.py (L1-L6)
src/api/app.py            the serving part: FastAPI service (A1-A5); imports shared only, never pipeline
eval/                     golden.json, evaluators.py, run_eval.py, runs/ (the four recorded evidence runs: baseline and three regressions)
runs/<run_id>/            locate.json, parse.json, identify.json, describe.json, final.json, run_record.json, llm/, eval/
data/risk.db              the SQLite database the load phase writes and the API reads
tests/                    pytest, against the real PDF and the recorded baseline run
Dockerfile, compose.yaml  the pipeline image (batch) and the api image (service)
```

## Setup

Requires [uv](https://docs.astral.sh/uv/) and, for the model steps, an OpenAI-compatible server. Here that is llama-swap on `127.0.0.1:9292` serving `gpt-oss` (a 20B model). Configure with `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`.

```sh
uv sync
```

## Running the pipeline

```sh
uv run python etl.py --list
uv run python etl.py --extract --run-id demo                    # E1-E8: no model
uv run python etl.py --transform --run-id demo                  # T1-T6: model calls, every one recorded under runs/demo/llm/
uv run python etl.py --transform --run-id demo2 --replay demo   # same, served from demo's recordings: no server needed
uv run python etl.py --load --run-id demo                       # L1-L6 -> data/risk.db
uv run python etl.py                                            # all three, new timestamped run id
```

Each phase reads the previous phase's JSON from `runs/<run_id>/` and writes its own, plus `run_record.json`: one row per validation check with its outcome (ok, warning, error), count, strategy and detail. The console prints that record after each phase. An error in a required check stops the run for that report.

The structured object the brief asks for is `runs/<run_id>/final.json` (`RiskExtraction` in `src/pipeline/schema.py`): company, report (with the Board review frequency from p.50), run info, and one record per principal risk with title, description, category, secondary categories, section, page, citations (both registers for cyber), mitigation, verbatim span, confidence, quality flags and lineage.

## Evaluation

The golden set is `eval/golden.json`: nine risks labelled from the report's registers before any model output, each with page, section, category, key phrases and whether a mitigation is stated, plus five questions with their expected intent.

```sh
uv run python eval/run_eval.py --run-id baseline --intents
```

Five evaluators: identification (precision and recall), provenance (page and section), grounding (key phrases in the record's own text), category, fields (2 to 3 sentences, mitigation present iff stated). Scores go to the run record as `eval_scores`; a failing evaluator makes the load phase refuse.

Regression runs, each a full extract and transform followed by the evaluators:

```sh
uv run python etl.py --extract --transform --run-id reg-broken-parser --break-parser            # naive text order on p.51
uv run python etl.py --extract --transform --run-id reg-prompt-no-mitigation --prompt-version v1-no-mitigation
uv run python etl.py --extract --transform --run-id reg-weak-model --model ministral-3:14b
uv run python eval/run_eval.py --run-id reg-broken-parser
```

## API

```sh
uv run uvicorn api.app:app --port 8000
```

| Endpoint | What |
|---|---|
| `GET /health` | schema version and database path |
| `GET /risks?company=&year=&category=&register=&status=&sector=&q=` | structured query; `q` is full-text search over title and description (FTS5, BM25) |
| `GET /risks/{id}` | one record with citations, categories, quality flags, review state, lineage |
| `GET /questions/{top_enterprise_risks,newly_elevated_risks,companies_with_category}` | the three brief questions from `queries.sql` |
| `POST /ask {"question": "..."}` | parses the question into the same filters with one recorded model call, runs them, returns the parsed intent with the records |
| `GET /companies`, `GET /runs`, `GET /runs/{id}/record` | metadata and the run record |

The service refuses to start if the database's schema version differs from its own. With `API_REPLAY_RUN=<run_id>` the question endpoint serves intents from that run's recordings and needs no model server; the structured endpoints never need one.

## Looking into the database

`data/risk.db` is a plain SQLite file. With the `sqlite3` command line tool on the host:

```sh
sqlite3 data/risk.db
sqlite> .tables
sqlite> .mode column
sqlite> SELECT id, title, category, page, review_state FROM risk_instance;
sqlite> SELECT * FROM risk_citation WHERE risk_instance_id = 'vestas-2025-r03';
sqlite> SELECT check_id, outcome, count FROM run_record WHERE run_id = 'baseline' AND outcome != 'ok';
sqlite> .quit
```

Without the tool, the same through Python: `uv run python -c "import sqlite3; c=sqlite3.connect('data/risk.db'); print(c.execute('SELECT id, title FROM risk_instance').fetchall())"`. The three brief questions are in `src/shared/queries.sql` and run as they are with `.read` after replacing the named parameters. The API opens the file read-only; open it read-write only when the API container is stopped.

## Docker

Two images from one Dockerfile. Both use the host network so they can reach the model server on `127.0.0.1:9292`.

```sh
docker compose --profile batch build                                  # both images
docker compose run --rm pipeline --pdf /reports/VestasAnnualReport2025.pdf --run-id docker-demo   # batch: all phases
docker compose up -d api                                              # serves data/risk.db on :8000
curl -s 'localhost:8000/questions/top_enterprise_risks?company=vestas' | python -m json.tool
```

Runs and the database live in `./data` on the host (`/data` in the containers), written as the host user (`UID`/`GID`, default 1000), so they can be removed without root. `data/` is git-ignored: it is runtime output, not evidence; the recorded evidence runs are the ones under `eval/runs/`. Set `LLM_BASE_URL`, `LLM_MODEL`, `PROMPT_VERSION` in the environment to change the model or prompts.

## Tests

```sh
uv run pytest
```

Extract tests run against the real PDF, including a copy with a blank page inserted at the front. Transform, load and API tests run in replay mode over `eval/runs/baseline`, so they need no model server; without that run present they are skipped. Tests write only to temporary directories: nothing lands in `runs/`, `data/` or the database.

## Results of the recorded runs

The four runs ship in `eval/runs/` with their model recordings (`runs/` itself is git-ignored working output), so every number below can be reproduced in replay mode, for example `uv run python etl.py --extract --transform --run-id check --replay ../eval/runs/baseline`. Model: gpt-oss 20B through llama-swap, prompt v1, temperature 0.

| Run | identification | provenance | grounding | category | fields | evaluators failed | what the run record adds |
|---|---|---|---|---|---|---|---|
| `baseline` | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | none | 10 register candidates, model agreement 1.0 on identification, 9 records after merging cyber, 2 records flagged for review by the grounding check, intent parsing 1.00 on the five golden questions |
| `reg-broken-parser`: p.51 read in naive text order, well-shaped but text under the wrong risk | 0.89 | 0.88 | 1.00 | 1.00 | 0.75 | identification, provenance, fields | the pipeline's own checks all pass, because every word is still on the page; only the golden set catches it: project execution unmatched, cyber loses its p.74 citation, mitigations wrong |
| `reg-prompt-no-mitigation`: describe prompt with mitigation removed | 1.00 | 1.00 | 1.00 | 1.00 | 0.67 | fields | the three risks whose mitigation the report states come back with none |
| `reg-weak-model`: ministral 14B instead of gpt-oss 20B | 1.00 | 1.00 | 1.00 | 0.89 | 1.00 | none | movement, not failure: one category wrong (geopolitics as supply chain), identification agreement 0.8 instead of 1.0, 4 grounding flags instead of 2 |

The weaker model stays above the category threshold of 0.8 with one miss in nine. That is the honest result on this report: a 14B model is not weak enough to fail the golden set, and the run record is what shows the degradation. The two baseline records flagged for review are the carbon-taxes row and the grid-and-permit row: in both, the model's second sentence restates the consequence in words the text does not use, and the check treats that as ungrounded. Both records are loaded with `review_state = pending_review`.

Tests: `uv run pytest` runs 19 tests in about 20 seconds, no model server needed.

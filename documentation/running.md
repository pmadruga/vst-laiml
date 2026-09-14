# Running the pipeline, the evaluation and the API

*What this is:* the full command reference, all through Docker. The only non-Docker command is the test suite, which runs on the host with uv.

## Images

```sh
docker compose --profile batch build
```

Two images from one Dockerfile: `pipeline` runs `etl.py` as a batch job, `api` serves the database. Both use the host network so they can reach the model server, llama-swap on `127.0.0.1:9292` serving `gpt-oss`; set `LLM_BASE_URL`, `LLM_MODEL` and `PROMPT_VERSION` in the environment to change that. Runs and the database live in `./data` on the host (`/data` in the containers), written as the host user. The report is mounted read-only at `/reports`.

## Pipeline

```sh
P="docker compose run --rm pipeline"
$P --list
$P --extract --run-id demo --pdf /reports/VestasAnnualReport2025.pdf          # E1-E8: no model
$P --transform --run-id demo                                                  # T1-T6: live model calls, every one recorded under data/runs/demo/llm/
$P --extract --transform --run-id demo2 --replay /data/runs/demo              # the same, served from demo's recordings: no server needed
$P --load --run-id demo                                                       # L1-L6 -> data/risk.db
$P --pdf /reports/VestasAnnualReport2025.pdf                                  # all three phases, new timestamped run id
```

Each phase reads the previous phase's JSON from `data/runs/<run_id>/` and writes its own, plus `run_record.json`: one row per validation check with outcome, count, strategy and detail; the console prints that record after each phase. The structured object the brief asks for is `final.json` (`RiskExtraction` in `src/shared/schema.py`).

Regression runs, each a full extract and transform followed by the evaluators:

```sh
$P --extract --transform --run-id reg-broken-parser --break-parser --pdf /reports/VestasAnnualReport2025.pdf
$P --extract --transform --run-id reg-prompt-no-mitigation --prompt-version v1-no-mitigation --pdf /reports/VestasAnnualReport2025.pdf
$P --extract --transform --run-id reg-weak-model --model ministral-3:14b --pdf /reports/VestasAnnualReport2025.pdf
```

## Evaluation

The golden set is `eval/golden.json`: nine risks labelled from the report's risk registers, each with page, section, category, key phrases and whether a mitigation is stated, plus nine questions with their expected intent. Five evaluators: identification, provenance, grounding, category, fields. Scores go to the run record as `eval_scores`; a failing evaluator makes the load phase refuse.

```sh
docker compose run --rm --entrypoint python pipeline eval/run_eval.py --run-id baseline
docker compose run --rm --entrypoint python pipeline eval/run_eval.py --run-id baseline --intents   # scores the questions too; uses recordings, goes live only for an unrecorded question
```

The four recorded runs ship in `eval/runs/` and are baked into the image at `/app/eval/runs/`; replay from there with `--replay /app/eval/runs/<run_id>`. Scores are in [results.md](results.md).

## API

```sh
docker compose up -d --force-recreate api      # serves data/risk.db on :8000; refuses to start on a schema-version mismatch
docker compose logs -f api
docker compose stop api
```

| Endpoint | What |
|---|---|
| `GET /health` | schema version and database path |
| `GET /risks?company=&year=&category=&register=&status=&sector=&q=&limit=` | structured query; `q` is full-text search over title and description |
| `GET /risks/{id}` | one record with citations, categories, quality flags, review state, lineage |
| `GET /questions/{top_enterprise_risks,newly_elevated_risks,companies_with_category}` | the three brief questions from `src/shared/queries.sql` |
| `POST /ask {"question": "..."}` | one recorded model call parses the question into the same filters, then SQL; returns the parsed intent with the records |
| `GET /companies`, `GET /runs`, `GET /runs/{id}/record` | metadata and the run record |

```sh
curl -s 'localhost:8000/risks?category=cyber' | python3 -m json.tool
curl -s -X POST localhost:8000/ask -H 'Content-Type: application/json' -d '{"question": "Which risks does Vestas list about tariffs?"}'
```

`/ask` needs the model server; the structured endpoints never do. With `API_REPLAY_RUN=/app/eval/runs/baseline` in the environment the question endpoint serves recorded intents only.

## Database

`data/risk.db` is a plain SQLite file. Open it read-only while the API runs:

```sh
sqlite3 'file:data/risk.db?mode=ro'
sqlite> .tables
sqlite> SELECT id, title, category, page, review_state FROM risk_instance;
sqlite> SELECT check_id, outcome, count FROM run_record WHERE run_id = 'baseline' AND outcome != 'ok';
```

## Tests

```sh
uv sync && uv run pytest
```

Extract tests run against the real PDF, including a copy with a blank page inserted at the front. Transform, load and API tests run in replay mode over `eval/runs/baseline`, so they need no model server. Tests write only to temporary directories.

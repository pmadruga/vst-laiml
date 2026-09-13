# Build report: pipeline, API, evaluation, Docker (2026-09-13)

Cites DESIGN.md > 1. Pipeline, 2. API, 3. Deployment; SPECS.md throughout. Built in one pass on Pedro's instruction ("implement the pipeline and the API, create docker instances, use the local gpt-oss"), so the stage gate in CLAUDE.md was not followed stage by stage; this report stands in for the stage reports.

## What was built

- `src/shared/`: schema, config, run record, model client, the brief queries. `src/pipeline/`: extract (E1-E8) on PyMuPDF; transform (T1-T4, T6) with a record/replay model client; load (L1-L6) to SQLite with FTS5, the status view and `queries.sql`.
- `src/api/app.py`: A1-A5 on FastAPI; structured endpoints, the three brief questions, `/ask` with intent parsing, run-record endpoints.
- `eval/`: golden set (9 risks, 5 questions), five evaluators plus the intent evaluator, `run_eval.py` writing `eval_scores` to the run record.
- `etl.py` with `--extract/--transform/--load`, `--replay`, `--break-parser`; `Dockerfile` with `pipeline` and `api` targets; `compose.yaml` with a shared `./data` volume and host networking.
- 19 tests: extract against the real PDF and a page-shifted copy; transform, load and API in replay mode over `runs/baseline`.

## Results

See README.md > Results of the recorded runs. Baseline passes all five evaluators and the intent evaluator; the broken parser fails three evaluators; the prompt without mitigation fails fields; the weaker model degrades category and agreement without failing.

## Deviations from SPECS.md

- **T5 enrich** is not built (entities, embedding check, the "Type of impact" lookup). Marker agreement is icon plus row text only.
- **T2 self-consistency** exists but never triggered: gpt-oss reported confidence 0.8 to 1.0 on every risk, so no majority vote ran. The path is exercised by nothing yet.
- **A5 query log**: the API opens the database read-only, so questions are recorded under `runs/api/llm/` (the model recordings) rather than in the `query_log` table. The table exists and is empty.
- **E8 page coverage** warns on the four pages with a running header or the ESRS legend; the threshold of 0.95 counts words outside the tables. Left as a warning on purpose: it is the check that would move on a page whose layout the parser does not know.
- **Run record is append-only**: re-scoring a run adds a new `eval_scores` row rather than replacing it, so `runs/baseline/run_record.json` carries the earlier intent score (0.40, before the prompt fix) next to the final one (1.00).
- **`--replay` and changed checks**: when a grounding check changes after a recording, a repair call may have no recording; it is flagged `repair_not_recorded` and the record keeps its original text.
- **Regression `--break-parser`** produces a well-shaped table by design, so the extract-phase checks pass and the golden set is what catches it. A cruder break (fields missing) is caught earlier, at E8 `main_risks_shape`, before any model call; that was the first version and is the stronger internal check, but it never reaches the evaluators.

## Housekeeping

- Package name `pipeline` requires the control file to be `etl.py`; Pydantic forbids a field named `register`, so the field is `source_register` everywhere.
- The FTS5 table stores its content; a contentless table cannot return the id column and made `q=` return nothing.
- The API connection is opened with `check_same_thread=False`, since FastAPI runs sync endpoints in a thread pool.
- Docker images use the host network because llama-swap binds to loopback; the images are 490 MB each.

## Open

1. Pedro to confirm `eval/golden.json`: titles, categories and key phrases were drafted from the registers before any model output, but by me, not by him (PLAN.md assumption).
2. Nothing is committed since the first commit.
3. CLAUDE.md still says current stage 0.
